from __future__ import annotations

import math
import re
import os
from dataclasses import dataclass

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException
from requests_aws4auth import AWS4Auth

from app.backend.aws_auth import get_frozen_credentials
from app.backend.config import get_aws_region
from app.backend.llm_client import LLMClientError, generate_embedding

TARGET_DOC_ID = "amazon_10k_2019"
TARGET_INDEX_VERSION = "v2_parser_foundation"
VECTOR_FIELD = "embedding"
LEXICAL_CANDIDATE_MULTIPLIER = 3
VECTOR_CANDIDATE_MULTIPLIER = 3
MIN_VECTOR_DIMENSIONS = 8
LEXICAL_WEIGHT = 0.8
VECTOR_WEIGHT = 0.2
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
    "could harm our business",
    "loss of key senior management personnel",
)
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
        {"term": {"doc_id.keyword": TARGET_DOC_ID}},
        {"term": {"index_version": TARGET_INDEX_VERSION}},
    ]


def _normalize_question_text(question: str) -> str:
    return re.sub(r"\s+", " ", question.casefold()).strip(" ?.\n\t")


def _explicit_item_rule(question: str) -> dict[str, object] | None:
    normalized = _normalize_question_text(question)
    for rule in EXPLICIT_ITEM_ROUTING_RULES:
        item_text = _normalize_question_text(str(rule["item"]))
        hints = tuple(str(hint).casefold() for hint in rule["hints"])
        if normalized == item_text or any(hint in normalized for hint in hints):
            return rule
    return None


def _classify_query_intent(question: str) -> str:
    normalized = question.casefold()
    explicit_item = _explicit_item_rule(question)
    if any(hint in normalized for hint in NUMERIC_QUERY_HINTS):
        return "numeric_table"
    if normalized.startswith("who is ") or normalized.startswith("who are "):
        return "entity_lookup"
    if any(hint in normalized for hint in EXECUTIVE_QUERY_HINTS):
        return "entity_lookup"
    if explicit_item is not None:
        return str(explicit_item["intent"])
    if any(hint in normalized for hint in RISK_HEADING_HINTS) or (len(question.split()) >= 8 and question[:1].isupper()):
        return "heading_lookup"
    if any(hint in normalized for hint in ITEM_1_HINTS + ITEM_2_HINTS + ITEM_3_HINTS + ITEM_5_HINTS + ITEM_7A_HINTS + ITEM_8_HINTS):
        return "narrative_explainer"
    if "management" in normalized or "results of operations" in normalized or "liquidity" in normalized:
        return "narrative_explainer"
    return "general_lookup"


def _expand_query(question: str, intent: str) -> str:
    normalized = question.casefold()
    explicit_item = _explicit_item_rule(question)
    if intent == "entity_lookup":
        return f"{question} Information About Our Executive Officers Executive Officers and Directors Board of Directors leadership"
    if intent == "heading_lookup":
        return f"{question} Item 1A Risk Factors subsection heading"
    if intent == "numeric_table":
        return f"{question} Selected Consolidated Financial Data table"
    if explicit_item is not None:
        return f"{question} {explicit_item['expansion']}"
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
    if intent == "narrative_explainer":
        return [field.replace("item^4", "item^10").replace("subsection^8", "subsection^12").replace("subsubsection^9", "subsubsection^14") for field in base_fields]
    return base_fields


def _build_lexical_query(question: str, top_k: int) -> dict[str, object]:
    intent = _classify_query_intent(question)
    expanded_question = _expand_query(question, intent)
    normalized = question.casefold()
    explicit_item = _explicit_item_rule(question)
    should = [
        {
            "multi_match": {
                "query": expanded_question,
                "fields": _fields_for_intent(intent),
                "type": "best_fields",
                "operator": "or",
            }
        },
        {
            "multi_match": {
                "query": expanded_question,
                "fields": _fields_for_intent(intent, phrase=True),
                "type": "phrase",
                "slop": 1,
            }
        },
    ]
    if intent == "narrative_explainer":
        if explicit_item is not None:
            should.extend(explicit_item["boosts"])
        if any(hint in normalized for hint in ITEM_1_HINTS) and not any(hint in normalized for hint in ITEM_2_HINTS):
            should.append({"term": {"item.keyword": {"value": "Item 1. Business", "boost": 25}}})
            should.append({"term": {"subsection.keyword": {"value": "General", "boost": 12}}})
            should.append({"term": {"subsection.keyword": {"value": "Consumers", "boost": 16}}})
        if explicit_item is None and any(hint in normalized for hint in ITEM_3_HINTS):
            should.append({"term": {"item.keyword": {"value": "Item 3. Legal Proceedings", "boost": 28}}})
        if explicit_item is None and any(hint in normalized for hint in ITEM_2_HINTS):
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


def _build_vector_query(top_k: int) -> dict[str, object]:
    return {
        "size": max(top_k * VECTOR_CANDIDATE_MULTIPLIER, top_k),
        "query": {
            "bool": {
                "filter": _build_doc_filter(),
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


def _run_lexical_search(client: OpenSearch, index_name: str, question: str, top_k: int) -> list[RetrievedChunk]:
    response = client.search(index=index_name, body=_build_lexical_query(question, top_k))
    hits = response.get("hits", {}).get("hits", [])
    chunks: list[RetrievedChunk] = []
    for hit in hits:
        normalized = _normalize_hit(hit, lexical_score=float(hit.get("_score", 0.0)))
        if normalized is not None:
            chunks.append(normalized)
    return chunks


def _run_vector_search(client: OpenSearch, index_name: str, question: str, top_k: int) -> list[RetrievedChunk]:
    response = client.search(index=index_name, body=_build_vector_query(top_k))
    hits = response.get("hits", {}).get("hits", [])
    normalized_hits: list[RetrievedChunk] = []
    has_embeddings = False
    for hit in hits:
        normalized = _normalize_hit(hit)
        if normalized is None:
            continue
        normalized_hits.append(normalized)
        if normalized.embedding is not None:
            has_embeddings = True

    if not has_embeddings:
        return []

    try:
        question_embedding = generate_embedding(question)
    except (ValueError, LLMClientError):
        return []

    chunks: list[RetrievedChunk] = []
    for normalized in normalized_hits:
        if normalized.embedding is None:
            continue
        normalized.vector_score = _cosine_similarity(question_embedding, normalized.embedding)
        normalized.score = normalized.vector_score
        chunks.append(normalized)
    chunks.sort(key=lambda chunk: chunk.vector_score, reverse=True)
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


def _merge_candidates(lexical_chunks: list[RetrievedChunk], vector_chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
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
        chunk.score = lexical_norm.get(chunk.chunk_id, 0.0) * LEXICAL_WEIGHT + vector_norm.get(chunk.chunk_id, 0.0) * VECTOR_WEIGHT

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
        lexical_chunks = _run_lexical_search(client, index_name, question, top_k)
        vector_chunks = _run_vector_search(client, index_name, question, top_k)
    except OpenSearchException as exc:
        raise RuntimeError("OpenSearch search failed.") from exc

    return _merge_candidates(lexical_chunks, vector_chunks, top_k)
