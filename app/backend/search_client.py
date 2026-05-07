from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException
from requests_aws4auth import AWS4Auth

from app.backend.aws_auth import get_frozen_credentials
from app.backend.config import get_aws_region
from app.backend.knowledge_index_schema import INDEX_SCHEMA_VERSION, VECTOR_FIELD, get_embedding_dimensions_override
from app.backend.query_references import extract_query_reference, resolve_section_overview_rule
from app.backend.risk_headings import extract_risk_heading_reference, question_references_risk_heading
from app.backend.llm_client import LLMClientError, generate_chat_completion, generate_embedding

logger = logging.getLogger(__name__)

LEXICAL_CANDIDATE_MULTIPLIER = 3
VECTOR_CANDIDATE_MULTIPLIER = 3
MIN_VECTOR_DIMENSIONS = 8
WEAK_LEXICAL_SCORE_THRESHOLD = 3.0
MIN_REWRITE_WORDS = 3
MAX_REWRITE_WORDS = 18
EXECUTIVE_QUERY_HINTS = (
    "executive officer",
    "executive officers",
    "leadership",
    "directors",
    "board of directors",
    "chief executive officer",
)
RISK_HEADING_HINTS = (
    "risk factor",
    "risk factors",
    "risks related to",
    "could harm our business",
    "could adversely affect our business",
    "may adversely affect our business",
    "loss of key senior management personnel",
)

@dataclass(frozen=True)
class RetrievalProfile:
    intent: str
    lexical_weight: float
    vector_weight: float
    vector_mode: str

RETRIEVAL_PROFILES: dict[str, RetrievalProfile] = {
    "heading_lookup": RetrievalProfile(intent="heading_lookup", lexical_weight=1.0, vector_weight=0.0, vector_mode="disabled"),
    "numeric_table": RetrievalProfile(intent="numeric_table", lexical_weight=1.0, vector_weight=0.0, vector_mode="disabled"),
    "entity_lookup": RetrievalProfile(intent="entity_lookup", lexical_weight=0.9, vector_weight=0.1, vector_mode="weak_lexical_fallback"),
    "section_overview": RetrievalProfile(intent="section_overview", lexical_weight=0.8, vector_weight=0.2, vector_mode="always"),
    "narrative_explainer": RetrievalProfile(intent="narrative_explainer", lexical_weight=0.65, vector_weight=0.35, vector_mode="always"),
    "general_lookup": RetrievalProfile(intent="general_lookup", lexical_weight=0.55, vector_weight=0.45, vector_mode="always"),
}


def _looks_like_risk_heading(question: str) -> bool:
    normalized = _normalize_question_text(question)
    if not normalized:
        return False
    if question_references_risk_heading(normalized):
        return True
    if any(hint in normalized for hint in RISK_HEADING_HINTS):
        return True
    return normalized.startswith("risks related to ")
NUMERIC_QUERY_HINTS = (
    "net sales",
    "operating income",
    "selected consolidated financial data",
    "2019",
    "2018",
)
ITEM_1_HINTS = ("business", "focus on", "customers", "amazon web services", "consumers", "sellers")
ITEM_2_HINTS = ("properties", "facilities", "operate", "headquarters", "offices", "fulfillment centers", "data centers")
ITEM_3_HINTS = ("legal proceedings", "litigation", "lawsuit", "claims")
ITEM_5_HINTS = (
    "item 5",
    "market for the registrant's common stock",
    "market for the registrant’s common stock",
    "common stock",
    "shareholder matters",
    "shareholders of record",
    "issuer purchases of equity securities",
    "market information",
    "holders",
    "stock symbol",
    "nasdaq",
    "amzn",
)
ITEM_7A_HINTS = ("market risk", "item 7a", "interest rate risk", "foreign exchange risk", "foreign currency risk", "equity investment risk")
ITEM_8_HINTS = ("item 8", "financial statements", "supplementary data", "balance sheets", "cash flows", "stockholders", "statements of operations")
EXPLICIT_ITEM_ROUTING_RULES = (
    {
        "item": "Item 1A. Risk Factors",
        "hints": (
            "item 1a",
            "item 1a risk factors",
            "risk factors described in item 1a",
            "summarize the risk factors described in item 1a",
            "risk factors in item 1a",
        ),
        "expansion": "Item 1A Risk Factors major themes business impacts uncertainty could harm our business",
        "boosts": (
            {"term": {"item.keyword": {"value": "Item 1A. Risk Factors", "boost": 30}}},
            {"term": {"section.keyword": {"value": "Item 1A. Risk Factors", "boost": 30}}},
        ),
        "intent": "heading_lookup",
    },
    {
        "item": "Item 1. Business",
        "hints": ("item 1", "item 1 business"),
        "expansion": "Item 1 Business General Consumers Sellers developers enterprises customer-centric focus selection price convenience",
        "boosts": (
            {"term": {"item.keyword": {"value": "Item 1. Business", "boost": 25}}},
            {"term": {"subsection.keyword": {"value": "General", "boost": 12}}},
            {"term": {"subsection.keyword": {"value": "Consumers", "boost": 16}}},
        ),
        "intent": "narrative_explainer",
    },
    {
        "item": "Item 2. Properties",
        "hints": ("item 2", "item 2 properties"),
        "expansion": "Item 2 Properties facilities headquarters offices fulfillment centers",
        "boosts": (
            {"term": {"item.keyword": {"value": "Item 2. Properties", "boost": 24}}},
        ),
        "intent": "narrative_explainer",
    },
    {
        "item": "Item 3. Legal Proceedings",
        "hints": ("item 3", "item 3 legal proceedings"),
        "expansion": "Item 3 Legal Proceedings legal proceedings claims litigation contingencies",
        "boosts": (
            {"term": {"item.keyword": {"value": "Item 3. Legal Proceedings", "boost": 28}}},
        ),
        "intent": "narrative_explainer",
    },
    {
        "item": "Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
        "hints": (
            "item 5",
            "item 5 market for the registrant's common stock",
            "item 5 market for the registrant’s common stock",
            "market for the registrant's common stock",
            "market for the registrant’s common stock",
            "issuer purchases of equity securities",
            "shareholder matters",
        ),
        "expansion": "Item 5 Market for the Registrant's Common Stock Related Shareholder Matters Issuer Purchases of Equity Securities market information holders Nasdaq AMZN",
        "boosts": (
            {
                "term": {
                    "item.keyword": {
                        "value": "Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
                        "boost": 28,
                    }
                }
            },
        ),
        "intent": "narrative_explainer",
    },
    {
        "item": "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        "hints": ("item 7a", "item 7a market risk", "quantitative and qualitative disclosures about market risk"),
        "expansion": "Item 7A Quantitative and Qualitative Disclosures About Market Risk",
        "boosts": (),
        "intent": "narrative_explainer",
    },
    {
        "item": "Item 8. Financial Statements and Supplementary Data",
        "hints": ("item 8", "item 8 financial statements", "financial statements and supplementary data"),
        "expansion": "Item 8 Financial Statements and Supplementary Data",
        "boosts": (),
        "intent": "narrative_explainer",
    },
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    content: str
    source_path: str
    source_uri: str
    score: float
    lexical_score: float = 0.0
    vector_score: float = 0.0
    part: str | None = None
    item: str | None = None
    subsection: str | None = None
    subsubsection: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    filing_type: str | None = None
    fiscal_year: str | None = None
    company_name: str | None = None
    content_type: str | None = None
    table_name: str | None = None
    metric: str | None = None
    year: str | None = None
    value_raw: str | None = None
    value_normalized: float | None = None
    unit: str | None = None
    entity_name: str | None = None
    entity_role: str | None = None
    embedding: list[float] | None = None


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.removeprefix("https://").removeprefix("http://")


def _build_client() -> OpenSearch:
    region = get_aws_region()
    endpoint = os.getenv("OPENSEARCH_COLLECTION_ENDPOINT")
    if not region or not endpoint:
        raise ValueError("OpenSearch configuration is incomplete.")

    credentials = get_frozen_credentials(region_name=region)
    if credentials is None:
        raise ValueError("AWS credentials are not available for OpenSearch access.")

    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "aoss",
        session_token=credentials.token,
    )

    return OpenSearch(
        hosts=[{"host": _normalize_endpoint(endpoint), "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )


def _normalize_embedding(values: object) -> list[float] | None:
    if not isinstance(values, list) or len(values) < MIN_VECTOR_DIMENSIONS:
        return None
    normalized: list[float] = []
    for value in values:
        try:
            normalized.append(float(value))
        except (TypeError, ValueError):
            return None
    return normalized


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _build_doc_filter() -> list[dict[str, object]]:
    return [
        {"term": {"index_version": INDEX_SCHEMA_VERSION}},
    ]


def _normalize_question_text(question: str) -> str:
    return re.sub(r"\s+", " ", question.casefold()).strip(" ?.\n\t")


def rewrite_search_query(question: str) -> str | None:
    normalized = _normalize_question_text(question)
    if not normalized:
        return None

    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite the user's retrieval query into one short search query for a 10-K index. "
                "Preserve explicit item numbers, years, metrics, and exact risk heading cues. "
                "Do not answer the question. Return only the rewritten query."
            ),
        },
        {
            "role": "user",
            "content": (
                "Rewrite this for retrieval against a filing index. Keep it concise and keyword-rich.\n\n"
                f"Question: {question}"
            ),
        },
    ]
    try:
        rewritten = generate_chat_completion(messages)
    except (ValueError, LLMClientError):
        return None

    cleaned = re.sub(r"\s+", " ", rewritten).strip().strip("\"'")
    if not cleaned:
        return None
    word_count = len(cleaned.split())
    if word_count < MIN_REWRITE_WORDS or word_count > MAX_REWRITE_WORDS:
        return None
    if _normalize_question_text(cleaned) == normalized:
        return None
    return cleaned


def _explicit_item_rule(question: str) -> dict[str, object] | None:
    normalized = _normalize_question_text(question)
    for rule in EXPLICIT_ITEM_ROUTING_RULES:
        item_text = _normalize_question_text(str(rule["item"]))
        hints = tuple(str(hint).casefold() for hint in rule["hints"])
        if normalized == item_text or any(hint in normalized for hint in hints):
            return rule
    return None


def _explicit_item_rule_for_item(item: str) -> dict[str, object] | None:
    for rule in EXPLICIT_ITEM_ROUTING_RULES:
        if str(rule["item"]) == item:
            return rule
    return None


def _resolved_item_rule(question: str) -> dict[str, object] | None:
    section_overview_rule = resolve_section_overview_rule(question)
    if section_overview_rule is not None:
        return _explicit_item_rule_for_item(section_overview_rule.item)
    return _explicit_item_rule(question)


def _classify_query_intent(question: str) -> str:
    normalized = question.casefold()
    section_overview_rule = resolve_section_overview_rule(question)
    explicit_item = _explicit_item_rule(question)
    if any(hint in normalized for hint in NUMERIC_QUERY_HINTS):
        return "numeric_table"
    if normalized.startswith("who is ") or normalized.startswith("who are "):
        return "entity_lookup"
    if any(hint in normalized for hint in EXECUTIVE_QUERY_HINTS):
        return "entity_lookup"
    if section_overview_rule is not None:
        return "section_overview"
    if explicit_item is not None and str(explicit_item["item"]) == "Item 1A. Risk Factors":
        if any(keyword in normalized for keyword in ("summarize", "summary", "overview", "major themes", "structured", "explain")):
            return "narrative_explainer"
    if explicit_item is not None:
        return str(explicit_item["intent"])
    if _looks_like_risk_heading(question) or (len(question.split()) >= 8 and question[:1].isupper()):
        return "heading_lookup"
    if any(hint in normalized for hint in ITEM_1_HINTS + ITEM_2_HINTS + ITEM_3_HINTS + ITEM_5_HINTS + ITEM_7A_HINTS + ITEM_8_HINTS):
        return "narrative_explainer"
    if "management" in normalized or "results of operations" in normalized or "liquidity" in normalized:
        return "narrative_explainer"
    return "general_lookup"

def _get_retrieval_profile(question: str, intent: str | None = None) -> RetrievalProfile:
    resolved_intent = intent or _classify_query_intent(question)
    return RETRIEVAL_PROFILES.get(resolved_intent, RETRIEVAL_PROFILES["general_lookup"])


def _expand_query(question: str, intent: str) -> str:
    normalized = question.casefold()
    routing_rule = _resolved_item_rule(question)
    reference_text = extract_query_reference(question) or question
    if intent == "entity_lookup":
        return f"{question} Information About Our Executive Officers Executive Officers and Directors Board of Directors leadership"
    if intent == "heading_lookup":
        heading_text = extract_risk_heading_reference(question) or question
        return f"{heading_text} Item 1A Risk Factors subsection heading"
    if intent == "numeric_table":
        return f"{question} Selected Consolidated Financial Data table"
    if intent == "section_overview" and routing_rule is not None:
        return f"{reference_text} {routing_rule['expansion']} section overview major themes subsection summary"
    if routing_rule is not None:
        return f"{question} {routing_rule['expansion']}"
    if any(hint in normalized for hint in ITEM_1_HINTS):
        return f"{question} Item 1 Business General Consumers Sellers developers enterprises customer-centric focus selection price convenience"
    if any(hint in normalized for hint in ITEM_2_HINTS):
        return f"{question} Item 2 Properties facilities headquarters offices fulfillment centers"
    if any(hint in normalized for hint in ITEM_3_HINTS):
        return f"{question} Item 3 Legal Proceedings legal proceedings claims litigation contingencies"
    if any(hint in normalized for hint in ITEM_5_HINTS):
        return (
            f"{question} Item 5 Market for the Registrant's Common Stock Related Shareholder Matters "
            "Issuer Purchases of Equity Securities market information holders Nasdaq AMZN"
        )
    if any(hint in normalized for hint in ITEM_7A_HINTS):
        return f"{question} Item 7A Quantitative and Qualitative Disclosures About Market Risk"
    if any(hint in normalized for hint in ITEM_8_HINTS):
        return f"{question} Item 8 Financial Statements and Supplementary Data"
    return question


def _fields_for_intent(intent: str, phrase: bool = False) -> list[str]:
    base_fields = [
        "title^4",
        "section^8",
        "item^4",
        "subsection^8",
        "subsubsection^9",
        "table_name^8",
        "metric^6",
        "year^5",
        "content^4",
        "entity_name^6",
        "entity_role^4",
        "content_type^3",
    ]
    if phrase:
        base_fields = [
            "title^8",
            "section^12",
            "item^8",
            "subsection^12",
            "subsubsection^14",
            "table_name^12",
            "metric^10",
            "year^8",
            "content^6",
            "entity_name^10",
            "entity_role^6",
            "content_type^4",
        ]
    if intent == "numeric_table":
        return [field.replace("metric^6", "metric^12").replace("table_name^8", "table_name^12").replace("year^5", "year^10") for field in base_fields]
    if intent == "entity_lookup":
        return [field.replace("entity_name^6", "entity_name^14").replace("entity_role^4", "entity_role^10").replace("subsection^8", "subsection^10") for field in base_fields]
    if intent == "heading_lookup":
        return [field.replace("subsection^8", "subsection^16").replace("subsubsection^9", "subsubsection^18").replace("section^8", "section^10") for field in base_fields]
    if intent == "section_overview":
        return [
            field.replace("section^8", "section^14")
            .replace("section^12", "section^18")
            .replace("item^4", "item^14")
            .replace("item^8", "item^18")
            .replace("subsection^8", "subsection^11")
            .replace("subsection^12", "subsection^15")
            .replace("subsubsection^9", "subsubsection^12")
            .replace("subsubsection^14", "subsubsection^16")
            for field in base_fields
        ]
    if intent == "narrative_explainer":
        return [field.replace("item^4", "item^10").replace("subsection^8", "subsection^12").replace("subsubsection^9", "subsubsection^14") for field in base_fields]
    return base_fields


def _build_lexical_query(question: str, top_k: int, intent: str | None = None) -> dict[str, object]:
    resolved_intent = intent or _classify_query_intent(question)
    expanded_question = _expand_query(question, resolved_intent)
    normalized = question.casefold()
    routing_rule = _resolved_item_rule(question)
    section_overview_rule = resolve_section_overview_rule(question)
    reference_text = extract_query_reference(question) or question
    should = [
        {
            "multi_match": {
                "query": expanded_question,
                "fields": _fields_for_intent(resolved_intent),
                "type": "best_fields",
                "operator": "or",
            }
        },
        {
            "multi_match": {
                "query": expanded_question,
                "fields": _fields_for_intent(resolved_intent, phrase=True),
                "type": "phrase",
                "slop": 1,
            }
        },
    ]
    if resolved_intent == "heading_lookup":
        heading_text = extract_risk_heading_reference(question) or question
        should.append({"term": {"item.keyword": {"value": "Item 1A. Risk Factors", "boost": 30}}})
        should.append({"term": {"section.keyword": {"value": "Item 1A. Risk Factors", "boost": 30}}})
        should.append({"term": {"subsection.keyword": {"value": heading_text, "boost": 60}}})
        should.append({"match_phrase": {"subsection": {"query": heading_text, "boost": 45}}})
        should.append({"match_phrase": {"content": {"query": heading_text, "boost": 12}}})
    if resolved_intent == "section_overview" and routing_rule is not None and section_overview_rule is not None:
        should.extend(routing_rule["boosts"])
        should.append({"term": {"item.keyword": {"value": str(routing_rule["item"]), "boost": 35}}})
        should.append({"term": {"section.keyword": {"value": str(routing_rule["item"]), "boost": 35}}})
        should.append({"match_phrase": {"item": {"query": str(routing_rule["item"]), "boost": 28}}})
        should.append({"match_phrase": {"section": {"query": str(routing_rule["item"]), "boost": 28}}})
        should.append({"match_phrase": {"content": {"query": reference_text, "boost": 8}}})
    elif routing_rule is not None:
        should.extend(routing_rule["boosts"])
    if resolved_intent == "narrative_explainer":
        if any(hint in normalized for hint in ITEM_1_HINTS) and not any(hint in normalized for hint in ITEM_2_HINTS):
            should.append({"term": {"item.keyword": {"value": "Item 1. Business", "boost": 25}}})
            should.append({"term": {"subsection.keyword": {"value": "General", "boost": 12}}})
            should.append({"term": {"subsection.keyword": {"value": "Consumers", "boost": 16}}})
        if routing_rule is None and any(hint in normalized for hint in ITEM_3_HINTS):
            should.append({"term": {"item.keyword": {"value": "Item 3. Legal Proceedings", "boost": 28}}})
        if routing_rule is None and any(hint in normalized for hint in ITEM_2_HINTS):
            should.append({"term": {"item.keyword": {"value": "Item 2. Properties", "boost": 24}}})
    return {
        "size": max(top_k * LEXICAL_CANDIDATE_MULTIPLIER, top_k),
        "query": {
            "bool": {
                "filter": _build_doc_filter(),
                "should": should,
                "minimum_should_match": 1,
            }
        },
        "_source": True,
    }


def _build_vector_query(question_embedding: list[float], top_k: int, question: str, intent: str) -> dict[str, object]:
    candidate_count = max(top_k * VECTOR_CANDIDATE_MULTIPLIER, top_k)
    filters = list(_build_doc_filter())
    routing_rule = _resolved_item_rule(question)
    if intent in {"narrative_explainer", "section_overview"} and routing_rule is not None:
        filters.append({"term": {"item.keyword": str(routing_rule["item"])}})
    return {
        "size": candidate_count,
        "query": {
            "knn": {
                VECTOR_FIELD: {
                    "vector": question_embedding,
                    "k": candidate_count,
                    "filter": {
                        "bool": {
                            "filter": filters,
                        }
                    },
                }
            }
        },
        "_source": True,
    }


def _normalize_hit(hit: dict[str, object], lexical_score: float = 0.0, vector_score: float = 0.0) -> RetrievedChunk | None:
    source = hit.get("_source", {}) if isinstance(hit, dict) else {}
    if not isinstance(source, dict):
        return None
    content = source.get("content", "")
    if not isinstance(content, str) or not content.strip():
        return None
    return RetrievedChunk(
        chunk_id=source.get("chunk_id", hit.get("_id", "")),
        doc_id=source.get("doc_id", ""),
        title=source.get("title", "Untitled"),
        section=source.get("section", ""),
        content=content,
        source_path=source.get("source_path", ""),
        source_uri=source.get("source_uri", ""),
        score=float(lexical_score or vector_score or hit.get("_score", 0.0)),
        lexical_score=float(lexical_score),
        vector_score=float(vector_score),
        part=source.get("part"),
        item=source.get("item"),
        subsection=source.get("subsection"),
        subsubsection=source.get("subsubsection"),
        page_start=source.get("page_start"),
        page_end=source.get("page_end"),
        filing_type=source.get("filing_type"),
        fiscal_year=source.get("fiscal_year"),
        company_name=source.get("company_name"),
        content_type=source.get("content_type"),
        table_name=source.get("table_name"),
        metric=source.get("metric"),
        year=source.get("year"),
        value_raw=source.get("value_raw"),
        value_normalized=source.get("value_normalized"),
        unit=source.get("unit"),
        entity_name=source.get("entity_name"),
        entity_role=source.get("entity_role"),
        embedding=_normalize_embedding(source.get(VECTOR_FIELD)),
    )


def _run_lexical_search(client: OpenSearch, index_name: str, question: str, top_k: int, intent: str | None = None) -> list[RetrievedChunk]:
    response = client.search(index=index_name, body=_build_lexical_query(question, top_k, intent=intent))
    hits = response.get("hits", {}).get("hits", [])
    chunks: list[RetrievedChunk] = []
    for hit in hits:
        normalized = _normalize_hit(hit, lexical_score=float(hit.get("_score", 0.0)))
        if normalized is not None:
            chunks.append(normalized)
    return chunks


def _best_item_match(chunks: list[RetrievedChunk], expected_item: str) -> bool:
    return any(chunk.item == expected_item for chunk in chunks)


def _has_heading_subsection_overlap(question: str, chunks: list[RetrievedChunk]) -> bool:
    normalized = _normalize_question_text(extract_risk_heading_reference(question) or question)
    question_tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for chunk in chunks:
        subsection = (chunk.subsection or "").casefold()
        if not subsection:
            continue
        if subsection in normalized or normalized in subsection:
            return True
        subsection_tokens = set(re.findall(r"[a-z0-9]+", subsection))
        if len(question_tokens & subsection_tokens) >= 4:
            return True
    return False


def _should_retry_with_rewrite(question: str, chunks: list[RetrievedChunk], intent: str | None = None) -> bool:
    if not chunks:
        return True
    resolved_intent = intent or _classify_query_intent(question)
    routing_rule = _resolved_item_rule(question)
    top_score = max(chunk.score for chunk in chunks)
    if top_score < 0.2:
        return True
    if resolved_intent == "heading_lookup":
        if not _best_item_match(chunks, "Item 1A. Risk Factors"):
            return True
        if not _has_heading_subsection_overlap(question, chunks[:4]):
            return True
    if resolved_intent == "section_overview":
        if routing_rule is not None and not _best_item_match(chunks[:6], str(routing_rule["item"])):
            return True
    if resolved_intent == "narrative_explainer":
        if routing_rule is not None and not _best_item_match(chunks[:4], str(routing_rule["item"])):
            return True
    return False

def _extract_entity_reference(question: str) -> str | None:
    normalized = _normalize_question_text(question)
    if normalized.startswith("who is "):
        return normalized.removeprefix("who is ").strip()
    if normalized.startswith("who are "):
        return normalized.removeprefix("who are ").strip()
    return None

def _has_strong_entity_match(question: str, chunks: list[RetrievedChunk]) -> bool:
    entity_reference = _extract_entity_reference(question)
    normalized_question = _normalize_question_text(question)
    for chunk in chunks[:3]:
        if chunk.content_type not in {"profile_row", "profile_bio"}:
            continue
        if normalized_question.startswith("who are "):
            return True
        if entity_reference is None:
            return True
        entity_name = _normalize_question_text(chunk.entity_name or "")
        if entity_name and (entity_name == entity_reference or entity_reference in entity_name or entity_name in entity_reference):
            return True
    return False

def _should_run_vector_search(question: str, lexical_chunks: list[RetrievedChunk], profile: RetrievalProfile) -> bool:
    if profile.vector_weight <= 0 or profile.vector_mode == "disabled":
        return False
    if profile.vector_mode == "weak_lexical_fallback":
        if not lexical_chunks:
            return True
        if profile.intent == "entity_lookup" and _has_strong_entity_match(question, lexical_chunks):
            return False
        return max(chunk.lexical_score for chunk in lexical_chunks) < WEAK_LEXICAL_SCORE_THRESHOLD
    return True


def _search_with_query_variants(client: OpenSearch, index_name: str, question: str, top_k: int) -> list[RetrievedChunk]:
    profile = _get_retrieval_profile(question)
    lexical_chunks = _run_lexical_search(client, index_name, question, top_k, intent=profile.intent)
    vector_chunks = _run_vector_search(client, index_name, question, top_k, profile, lexical_chunks)
    merged = _merge_candidates(lexical_chunks, vector_chunks, top_k, profile)
    if not _should_retry_with_rewrite(question, merged, intent=profile.intent):
        return merged

    rewritten = rewrite_search_query(question)
    if not rewritten:
        return merged

    rewritten_lexical_chunks = _run_lexical_search(client, index_name, rewritten, top_k, intent=profile.intent)
    rewritten_vector_chunks = _run_vector_search(client, index_name, rewritten, top_k, profile, rewritten_lexical_chunks)
    return _merge_candidates(
        lexical_chunks + rewritten_lexical_chunks,
        vector_chunks + rewritten_vector_chunks,
        top_k,
        profile,
    )


def _run_vector_search(
    client: OpenSearch,
    index_name: str,
    question: str,
    top_k: int,
    profile: RetrievalProfile,
    lexical_chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not _should_run_vector_search(question, lexical_chunks, profile):
        return []
    try:
        question_embedding = generate_embedding(question)
    except (ValueError, LLMClientError):
        logger.warning("Vector retrieval disabled for question because embedding generation failed.")
        return []
    if len(question_embedding) < MIN_VECTOR_DIMENSIONS:
        logger.warning("Vector retrieval disabled because query embedding dimension %s is too small.", len(question_embedding))
        return []
    configured_dimensions = get_embedding_dimensions_override()
    if configured_dimensions is not None and len(question_embedding) != configured_dimensions:
        logger.warning(
            "Vector retrieval disabled because query embedding dimension %s does not match configured dimension %s.",
            len(question_embedding),
            configured_dimensions,
        )
        return []

    try:
        response = client.search(index=index_name, body=_build_vector_query(question_embedding, top_k, question, profile.intent))
    except OpenSearchException as exc:
        logger.warning("Vector retrieval failed; falling back to lexical-only search. %s", exc)
        return []

    chunks: list[RetrievedChunk] = []
    hits = response.get("hits", {}).get("hits", [])
    for hit in hits:
        normalized = _normalize_hit(hit, vector_score=float(hit.get("_score", 0.0)))
        if normalized is None:
            continue
        normalized.score = normalized.vector_score
        chunks.append(normalized)
    return chunks[: max(top_k * VECTOR_CANDIDATE_MULTIPLIER, top_k)]


def _normalize_scores(chunks: list[RetrievedChunk], attr_name: str) -> dict[str, float]:
    if not chunks:
        return {}
    values = [getattr(chunk, attr_name) for chunk in chunks]
    minimum = min(values)
    maximum = max(values)
    if maximum <= minimum:
        return {chunk.chunk_id: (1.0 if maximum > 0 else 0.0) for chunk in chunks}
    return {
        chunk.chunk_id: (getattr(chunk, attr_name) - minimum) / (maximum - minimum)
        for chunk in chunks
    }


def _merge_candidates(
    lexical_chunks: list[RetrievedChunk],
    vector_chunks: list[RetrievedChunk],
    top_k: int,
    profile: RetrievalProfile | None = None,
) -> list[RetrievedChunk]:
    resolved_profile = profile or RETRIEVAL_PROFILES["general_lookup"]
    merged: dict[str, RetrievedChunk] = {}
    for chunk in lexical_chunks + vector_chunks:
        existing = merged.get(chunk.chunk_id)
        if existing is None:
            merged[chunk.chunk_id] = chunk
            continue
        existing.lexical_score = max(existing.lexical_score, chunk.lexical_score)
        existing.vector_score = max(existing.vector_score, chunk.vector_score)
        if existing.embedding is None and chunk.embedding is not None:
            existing.embedding = chunk.embedding

    merged_chunks = list(merged.values())
    lexical_norm = _normalize_scores(merged_chunks, "lexical_score")
    vector_norm = _normalize_scores(merged_chunks, "vector_score")

    for chunk in merged_chunks:
        chunk.score = (
            lexical_norm.get(chunk.chunk_id, 0.0) * resolved_profile.lexical_weight
            + vector_norm.get(chunk.chunk_id, 0.0) * resolved_profile.vector_weight
        )

    return sorted(
        merged_chunks,
        key=lambda chunk: (chunk.score, chunk.lexical_score, chunk.vector_score),
        reverse=True,
    )[: max(top_k * 2, top_k)]


def search_chunks(question: str, top_k: int = 4) -> list[RetrievedChunk]:
    index_name = os.getenv("OPENSEARCH_INDEX_NAME")
    if not index_name:
        raise ValueError("OPENSEARCH_INDEX_NAME is not configured.")

    client = _build_client()
    try:
        merged_chunks = _search_with_query_variants(client, index_name, question, top_k)
    except OpenSearchException as exc:
        raise RuntimeError("OpenSearch search failed.") from exc

    return merged_chunks
