from __future__ import annotations

import os
import re
from collections.abc import Iterator

from app.backend.llm_client import LLMClientError, generate_chat_completion, generate_chat_completion_stream
from app.backend.models import SourceItem
from app.backend.search_client import RetrievedChunk, search_chunks


CONSERVATIVE_FALLBACK = "I do not have enough grounded context in the available documents to answer that confidently yet."
MIN_RETRIEVAL_SCORE = 0.1
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
}
NUMERIC_HINTS = {
    "2015",
    "2016",
    "2017",
    "2018",
    "2019",
    "net sales",
    "operating income",
    "net income",
    "employees",
    "employee count",
    "how many",
    "revenue",
    "income",
    "sales",
    "per share",
}
EXECUTIVE_QUERY_HINTS = {
    "executive",
    "officers",
    "officer",
    "directors",
    "director",
    "board",
    "leadership",
}
RISK_QUERY_HINTS = {
    "risk",
    "harm",
    "personnel",
    "management",
}
BUSINESS_QUERY_HINTS = {"business", "focus", "customers", "consumer", "sellers", "aws"}
PROPERTIES_QUERY_HINTS = {"properties", "facilities", "headquarters", "offices", "fulfillment", "centers", "data"}
LEGAL_QUERY_HINTS = {"legal", "proceedings", "litigation", "lawsuit", "claims"}
MARKET_RISK_QUERY_HINTS = {"market", "risk", "7a", "interest", "foreign", "exchange", "currency"}
ITEM8_QUERY_HINTS = {"financial", "statements", "supplementary", "balance", "cash", "flows", "stockholders"}


def _extract_question_keywords(question: str) -> set[str]:
    tokens = {token for token in re.findall(r"[a-z0-9]+", question.casefold()) if token not in STOPWORDS}
    normalized = set(tokens)
    if "return" in tokens:
        normalized.add("returns")
    if "returns" in tokens:
        normalized.add("return")
    if "refund" in tokens:
        normalized.add("refunds")
    if "refunds" in tokens:
        normalized.add("refund")
    return normalized


def _is_numeric_question(question: str) -> bool:
    question_lower = question.casefold()
    if any(hint in question_lower for hint in NUMERIC_HINTS):
        return True
    return bool(re.search(r"\b20\d{2}\b", question_lower))


def _classify_question_intent(question: str) -> str:
    question_lower = question.casefold()
    keywords = _extract_question_keywords(question)
    if _is_numeric_question(question):
        return "numeric_table"
    if question_lower.startswith("who is ") or question_lower.startswith("who are "):
        return "entity_lookup"
    if "selected consolidated financial data" in question_lower:
        return "numeric_table"
    if keywords & EXECUTIVE_QUERY_HINTS:
        return "entity_lookup"
    if not (keywords & MARKET_RISK_QUERY_HINTS or "item 7a" in question_lower) and keywords & RISK_QUERY_HINTS and len(question.split()) >= 6:
        return "heading_lookup"
    if keywords & (BUSINESS_QUERY_HINTS | PROPERTIES_QUERY_HINTS | LEGAL_QUERY_HINTS | MARKET_RISK_QUERY_HINTS | ITEM8_QUERY_HINTS):
        return "narrative_explainer"
    if any(token in question_lower for token in {"results of operations", "liquidity", "capital resources", "why", "explain"}):
        return "narrative_explainer"
    return "general_lookup"


def _entity_target_name(question: str) -> str | None:
    question_lower = question.casefold().strip()
    if question_lower.startswith("who is "):
        return question[7:].strip(" ?.")
    if question_lower.startswith("who are "):
        return question[8:].strip(" ?.")
    return None


def _matches_entity_target(chunk: RetrievedChunk, target_name: str | None) -> bool:
    if not target_name:
        return False
    target_tokens = set(re.findall(r"[a-z0-9]+", target_name.casefold()))
    if not target_tokens:
        return False
    entity_tokens = set(re.findall(r"[a-z0-9]+", (chunk.entity_name or "").casefold()))
    if entity_tokens and target_tokens <= entity_tokens:
        return True
    content_tokens = set(re.findall(r"[a-z0-9]+", chunk.content.casefold()))
    return target_tokens <= content_tokens


def _metric_tokens(metric: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (metric or "").casefold()))


def _heading_specific_tokens(question: str) -> set[str]:
    generic = {"could", "harm", "business", "may", "adversely", "affect"}
    return _extract_question_keywords(question) - generic


def _heading_query_text(question: str) -> str | None:
    intent = _classify_question_intent(question)
    if intent != "heading_lookup":
        return None
    normalized = question.strip().strip("?. ")
    return normalized or None


def _expected_items(question: str) -> set[str]:
    keywords = _extract_question_keywords(question)
    question_lower = question.casefold()
    expected: set[str] = set()
    if keywords & BUSINESS_QUERY_HINTS and not (keywords & PROPERTIES_QUERY_HINTS):
        expected.add("Item 1. Business")
    if keywords & PROPERTIES_QUERY_HINTS:
        expected.add("Item 2. Properties")
    if keywords & LEGAL_QUERY_HINTS:
        expected.add("Item 3. Legal Proceedings")
    if "item 7a" in question_lower or (keywords & MARKET_RISK_QUERY_HINTS and "item 1a" not in question_lower):
        expected.add("Item 7A. Quantitative and Qualitative Disclosures About Market Risk")
    if keywords & ITEM8_QUERY_HINTS:
        expected.add("Item 8. Financial Statements and Supplementary Data")
    return expected


def _is_large_item2_blob(chunk: RetrievedChunk) -> bool:
    return chunk.item == "Item 2. Properties" and len(chunk.content) > 350 and chunk.subsection is None


def _content_type_priority(chunk: RetrievedChunk, intent: str) -> int:
    if intent == "numeric_table":
        if chunk.content_type == "table_row":
            return 5
        if chunk.content_type == "table_block":
            return 4
        if chunk.content_type == "fact":
            return 3
        return 1
    if intent == "entity_lookup":
        if chunk.content_type == "profile_row":
            return 5
        if chunk.content_type == "profile_bio":
            return 4
        if chunk.content_type == "fact":
            return 3
        return 1
    if intent == "heading_lookup":
        if chunk.content_type == "narrative":
            return 5
        if chunk.content_type == "fact":
            return 3
        return 1
    if intent == "narrative_explainer":
        if chunk.content_type == "fact":
            return 5
        if chunk.content_type == "narrative":
            return 4
        if chunk.content_type == "table_block":
            return 2
        return 1
    if chunk.content_type == "narrative":
        return 3
    if chunk.content_type == "fact":
        return 2
    return 1


def _rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    keywords = _extract_question_keywords(question)
    intent = _classify_question_intent(question)
    target_name = _entity_target_name(question)
    heading_specific_tokens = _heading_specific_tokens(question)
    if not keywords and intent == "general_lookup":
        return chunks

    def rank_key(chunk: RetrievedChunk) -> tuple[float, float, float, float, float]:
        title_tokens = set(re.findall(r"[a-z0-9]+", chunk.title.casefold()))
        section_tokens = set(re.findall(r"[a-z0-9]+", chunk.section.casefold()))
        item_tokens = set(re.findall(r"[a-z0-9]+", (chunk.item or "").casefold()))
        subsection_tokens = set(re.findall(r"[a-z0-9]+", (chunk.subsection or "").casefold()))
        subsubsection_tokens = set(re.findall(r"[a-z0-9]+", (chunk.subsubsection or "").casefold()))
        metric_tokens = set(re.findall(r"[a-z0-9]+", (chunk.metric or "").casefold()))
        table_tokens = set(re.findall(r"[a-z0-9]+", (chunk.table_name or "").casefold()))
        entity_tokens = set(re.findall(r"[a-z0-9]+", (chunk.entity_name or "").casefold()))
        year_tokens = {chunk.year.casefold()} if chunk.year else set()
        overlap_score = (
            len(keywords & title_tokens) * 3
            + len(keywords & section_tokens) * 4
            + len(keywords & item_tokens) * 4
            + len(keywords & subsection_tokens) * 5
            + len(keywords & subsubsection_tokens) * 6
            + len(keywords & metric_tokens) * 6
            + len(keywords & table_tokens) * 3
            + len(keywords & entity_tokens) * 8
            + len(keywords & year_tokens) * 6
        )
        type_score = _content_type_priority(chunk, intent)
        retrieval_score = chunk.lexical_score + chunk.vector_score
        exact_match_bonus = 0
        penalty = 0.0
        expected_items = _expected_items(question)
        if expected_items and chunk.item in expected_items:
            exact_match_bonus += 18
        elif expected_items and chunk.item and chunk.item not in expected_items:
            penalty += 10
        if intent == "narrative_explainer" and _is_large_item2_blob(chunk) and chunk.item not in expected_items:
            penalty += 24
        if intent == "narrative_explainer" and chunk.item == "Item 1. Business" and chunk.subsection in {"General", "Consumers"} and (keywords & BUSINESS_QUERY_HINTS):
            exact_match_bonus += 14
        if intent == "narrative_explainer" and chunk.item == "Item 3. Legal Proceedings" and (keywords & LEGAL_QUERY_HINTS):
            exact_match_bonus += 20
        if intent == "numeric_table" and chunk.metric and chunk.metric.casefold() in question.casefold():
            exact_match_bonus += 6
        if intent == "numeric_table" and chunk.year and chunk.year in question:
            exact_match_bonus += 6
        if intent == "numeric_table" and chunk.metric == "Net sales" and chunk.year and chunk.year != "2019" and "2019" in question:
            penalty += 20
        if intent == "numeric_table" and chunk.section != "Item 6. Selected Consolidated Financial Data":
            penalty += 15
        if chunk.subsection and any(token in chunk.subsection.casefold() for token in keywords):
            exact_match_bonus += 3
        if chunk.subsubsection and any(token in chunk.subsubsection.casefold() for token in keywords):
            exact_match_bonus += 5
        if intent == "entity_lookup":
            executive_fields = " ".join(filter(None, [chunk.section, chunk.subsection, chunk.table_name, chunk.entity_name, chunk.content[:220]])).casefold()
            if "executive officers and directors" in executive_fields:
                exact_match_bonus += 20
            if chunk.entity_name and any(token in chunk.entity_name.casefold() for token in keywords):
                exact_match_bonus += 10
            if question.casefold().startswith("who is ") and chunk.entity_name:
                if target_name and chunk.entity_name.casefold() == target_name.casefold():
                    exact_match_bonus += 40
                elif target_name and not _matches_entity_target(chunk, target_name):
                    penalty += 40
            elif question.casefold().startswith("who are ") and chunk.content_type == "profile_row":
                exact_match_bonus += 12
            if chunk.content_type == "table_row":
                penalty += 10
            if chunk.content_type == "narrative" and not chunk.entity_name:
                penalty += 8
        if intent == "heading_lookup" and chunk.subsection and chunk.subsection.casefold() in question.casefold():
            exact_match_bonus += 25
        if intent == "heading_lookup":
            if chunk.section != "Item 1A. Risk Factors":
                penalty += 25
            if not chunk.subsection:
                penalty += 30
            elif chunk.subsection.casefold() == question.casefold():
                exact_match_bonus += 50
            elif question.casefold() not in chunk.subsection.casefold():
                penalty += 20
            subsection_tokens = set(re.findall(r"[a-z0-9]+", (chunk.subsection or "").casefold()))
            specific_overlap = len(heading_specific_tokens & subsection_tokens)
            exact_match_bonus += specific_overlap * 12
            if heading_specific_tokens and specific_overlap == 0:
                penalty += 35
            generic_only_overlap = len((keywords - heading_specific_tokens) & subsection_tokens)
            if generic_only_overlap and specific_overlap == 0:
                penalty += 20
        if intent == "narrative_explainer" and chunk.item == "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations":
            exact_match_bonus += 10
        return (type_score, exact_match_bonus + overlap_score - penalty, retrieval_score, chunk.score, -penalty)

    return sorted(chunks, key=rank_key, reverse=True)


def _limit_chunks_for_intent(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    intent = _classify_question_intent(question)
    if intent == "entity_lookup":
        target_name = _entity_target_name(question)
        filtered = [chunk for chunk in chunks if chunk.content_type in {"profile_row", "profile_bio"}]
        if target_name:
            exact_filtered = [chunk for chunk in filtered if _matches_entity_target(chunk, target_name)]
            if exact_filtered:
                return exact_filtered[:4]
        if question.casefold().startswith("who are "):
            profile_rows = [chunk for chunk in filtered if chunk.content_type == "profile_row"]
            if profile_rows:
                return profile_rows[:8]
        return filtered[:6] if filtered else chunks[:6]
    if intent == "heading_lookup":
        filtered = [chunk for chunk in chunks if chunk.section == "Item 1A. Risk Factors" and chunk.subsection]
        return filtered[:4] if filtered else chunks[:4]
    if intent == "numeric_table":
        prioritized = [
            chunk
            for chunk in chunks
            if chunk.section == "Item 6. Selected Consolidated Financial Data" and chunk.content_type in {"table_row", "table_block"}
        ]
        question_lower = question.casefold()
        requested_years = re.findall(r"\b20\d{2}\b", question)
        requested_metric_tokens = _extract_question_keywords(question)
        exact_rows = [
            chunk
            for chunk in prioritized
            if chunk.content_type == "table_row"
            and (not requested_years or chunk.year in requested_years)
            and (_metric_tokens(chunk.metric) & requested_metric_tokens)
        ]
        if exact_rows:
            return exact_rows[:4]
        if "selected consolidated financial data" in question_lower:
            table_blocks = [chunk for chunk in prioritized if chunk.content_type == "table_block"]
            if table_blocks:
                return table_blocks[:2]
        return prioritized[:5] if prioritized else chunks[:5]
    if intent == "narrative_explainer":
        expected_items = _expected_items(question)
        prioritized = [chunk for chunk in chunks if chunk.content_type in {"narrative", "fact", "table_block"}]
        if expected_items:
            item_specific = [chunk for chunk in prioritized if chunk.item in expected_items]
            if item_specific:
                if "Item 7A. Quantitative and Qualitative Disclosures About Market Risk" in expected_items and not any(chunk.item == "Item 7A. Quantitative and Qualitative Disclosures About Market Risk" for chunk in prioritized):
                    item_specific = [chunk for chunk in item_specific if chunk.item != "Item 1A. Risk Factors"]
                if "Item 8. Financial Statements and Supplementary Data" in expected_items and not any(chunk.item == "Item 8. Financial Statements and Supplementary Data" for chunk in prioritized):
                    item_specific = [chunk for chunk in item_specific if chunk.item != "Item 1A. Risk Factors"]
                item_specific = [chunk for chunk in item_specific if not (_is_large_item2_blob(chunk) and chunk.item not in expected_items)]
                return item_specific[:5] if item_specific else chunks[:3]
        fallback = [chunk for chunk in prioritized if not _is_large_item2_blob(chunk)]
        if expected_items & {"Item 7A. Quantitative and Qualitative Disclosures About Market Risk", "Item 8. Financial Statements and Supplementary Data"}:
            fallback = [chunk for chunk in fallback if chunk.item != "Item 1A. Risk Factors"]
            return fallback[:3] if fallback else []
        return fallback[:5] if fallback else prioritized[:5] if prioritized else chunks[:5]
    return chunks[:6]


def _format_context(chunks: list[RetrievedChunk]) -> str:
    sections = []
    for index, chunk in enumerate(chunks, start=1):
        page_span = None
        if chunk.page_start and chunk.page_end:
            page_span = f"{chunk.page_start}-{chunk.page_end}" if chunk.page_start != chunk.page_end else str(chunk.page_start)
        lines = [f"Source {index}:", f"Title: {chunk.title}", f"Section: {chunk.section or 'General'}"]
        if chunk.item:
            lines.append(f"Item: {chunk.item}")
        if chunk.subsection:
            lines.append(f"Subsection: {chunk.subsection}")
        if chunk.subsubsection:
            lines.append(f"Subsubsection: {chunk.subsubsection}")
        if page_span:
            lines.append(f"Pages: {page_span}")
        if chunk.content_type:
            lines.append(f"Content Type: {chunk.content_type}")
        if chunk.lexical_score:
            lines.append(f"Lexical Score: {chunk.lexical_score:.4f}")
        if chunk.vector_score:
            lines.append(f"Vector Score: {chunk.vector_score:.4f}")
        if chunk.table_name:
            lines.append(f"Table: {chunk.table_name}")
        if chunk.metric:
            lines.append(f"Metric: {chunk.metric}")
        if chunk.year:
            lines.append(f"Year: {chunk.year}")
        if chunk.value_raw:
            lines.append(f"Value: {chunk.value_raw}")
        if chunk.unit:
            lines.append(f"Unit: {chunk.unit}")
        lines.append(f"Content: {chunk.content}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _build_messages(question: str, context: str) -> list[dict[str, str]]:
    system_prompt = (
        "You are a customer support knowledge assistant. Answer only from the provided context. "
        "If the context is insufficient, say that you do not have enough grounded context. Do not fabricate details."
    )
    if _is_numeric_question(question):
        system_prompt += " Prefer exact numeric answers from structured table rows when available."
    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                "Answer the question using only the provided context. "
                "If the context is insufficient, say that you do not have enough grounded context.\n\n"
                f"Question: {question}\n\n"
                f"Context:\n{context}"
            ),
        },
    ]


def retrieve_relevant_chunks(question: str, top_k: int = 4) -> list[RetrievedChunk]:
    chunks = search_chunks(question, top_k=top_k)
    relevant_chunks = [chunk for chunk in chunks if chunk.score >= MIN_RETRIEVAL_SCORE]
    reranked = _rerank_chunks(question, relevant_chunks)
    return _limit_chunks_for_intent(question, reranked)


def generate_grounded_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    intent = _classify_question_intent(question)
    if intent == "numeric_table":
        exact_rows = [
            chunk
            for chunk in chunks
            if chunk.content_type == "table_row"
            and chunk.metric
            and chunk.year
            and (_metric_tokens(chunk.metric) & _extract_question_keywords(question))
            and chunk.year in question
        ]
        if len(exact_rows) == 1:
            row = exact_rows[0]
            unit = f" {row.unit}" if row.unit else ""
            return f"{row.metric} in {row.year} were **{row.value_raw}{unit}**."
    answer = generate_chat_completion(_build_messages(question, _format_context(chunks)))
    return answer or CONSERVATIVE_FALLBACK


def generate_grounded_answer_stream(question: str, chunks: list[RetrievedChunk]) -> Iterator[str]:
    yield from generate_chat_completion_stream(_build_messages(question, _format_context(chunks)))


def stream_answer_question(question: str) -> tuple[Iterator[str], list[SourceItem]]:
    chunks = retrieve_relevant_chunks(question)
    if not chunks:
        return iter([CONSERVATIVE_FALLBACK]), []
    return generate_grounded_answer_stream(question, chunks), _build_sources(chunks)


def _build_source_title(chunk: RetrievedChunk) -> str:
    if chunk.content_type == "table_row" and chunk.metric and chunk.year:
        return f"{chunk.section} - {chunk.metric} ({chunk.year})"
    if chunk.content_type == "profile_row" and chunk.entity_name:
        return f"Executive Officers and Directors - {chunk.entity_name}"
    if chunk.content_type == "profile_bio" and chunk.entity_name:
        return f"Executive Officers and Directors - {chunk.entity_name} - Biography"
    if chunk.content_type == "table_block" and chunk.table_name:
        if chunk.subsection:
            return f"{chunk.title} - {chunk.section} - {chunk.subsection}"
        return f"{chunk.title} - {chunk.table_name}"
    if chunk.content_type == "fact":
        if chunk.subsubsection:
            return f"{chunk.title} - {chunk.section} - {chunk.subsection} - {chunk.subsubsection}"
        if chunk.subsection:
            return f"{chunk.title} - {chunk.section} - {chunk.subsection}"
        return f"{chunk.title} - {chunk.section} - Fact"
    if chunk.subsubsection:
        return f"{chunk.title} - {chunk.section} - {chunk.subsection} - {chunk.subsubsection}"
    if chunk.subsection:
        return f"{chunk.title} - {chunk.section} - {chunk.subsection}"
    inferred_heading = _heading_query_text(os.getenv("KB_ACTIVE_QUESTION", ""))
    if inferred_heading and chunk.section == "Item 1A. Risk Factors":
        return f"{chunk.title} - {chunk.section} - {inferred_heading}"
    if chunk.section:
        return f"{chunk.title} - {chunk.section}"
    return chunk.title


def _build_source_snippet(chunk: RetrievedChunk) -> str:
    if chunk.content_type in {"table_row", "profile_row", "profile_bio", "fact"}:
        return chunk.content[:220]
    if chunk.subsubsection:
        return f"{chunk.subsubsection}: {chunk.content[:180]}"[:220]
    if chunk.subsection:
        return f"{chunk.subsection}: {chunk.content[:180]}"[:220]
    inferred_heading = _heading_query_text(os.getenv("KB_ACTIVE_QUESTION", ""))
    if inferred_heading and chunk.section == "Item 1A. Risk Factors":
        return f"{inferred_heading}: {chunk.content[:180]}"[:220]
    return chunk.content[:220]


def _build_source_semantic_key(chunk: RetrievedChunk) -> str:
    if chunk.content_type == "table_row":
        return f"{chunk.doc_id}:{chunk.content_type}:{chunk.subsection}:{chunk.metric}:{chunk.year}"
    if chunk.content_type in {"profile_row", "profile_bio"}:
        return f"{chunk.doc_id}:{chunk.content_type}:{chunk.entity_name}"
    if chunk.content_type == "table_block":
        return f"{chunk.doc_id}:{chunk.content_type}:{chunk.section}:{chunk.subsection}:{chunk.table_name}"
    if chunk.content_type == "fact":
        return f"{chunk.doc_id}:{chunk.content_type}:{chunk.section}:{chunk.subsection}:{chunk.subsubsection}:{chunk.content[:80]}"
    return f"{chunk.doc_id}:{chunk.content_type}:{chunk.section}:{chunk.subsection}:{chunk.subsubsection}"


def _build_sources(chunks: list[RetrievedChunk]) -> list[SourceItem]:
    seen: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        source_key = _build_source_semantic_key(chunk)
        if source_key in seen:
            continue
        seen.add(source_key)
        sources.append(
            SourceItem(
                source_id=chunk.chunk_id,
                title=_build_source_title(chunk),
                snippet=_build_source_snippet(chunk),
                content_type=chunk.content_type,
                item=chunk.item,
                subsection=chunk.subsection,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                entity_name=chunk.entity_name,
                entity_role=chunk.entity_role,
                metric=chunk.metric,
                year=chunk.year,
                table_name=chunk.table_name,
            )
        )
    return sources


def answer_question(question: str) -> tuple[str, list[SourceItem]]:
    try:
        intent = _classify_question_intent(question)
        retrieval_k = 8 if intent == "entity_lookup" and question.casefold().startswith("who are ") else 4
        chunks = retrieve_relevant_chunks(question, top_k=retrieval_k)
        if not chunks:
            return CONSERVATIVE_FALLBACK, []

        os.environ["KB_ACTIVE_QUESTION"] = question
        answer = generate_grounded_answer(question, chunks)
        if answer == CONSERVATIVE_FALLBACK:
            return answer, []
        return answer, _build_sources(chunks)
    except (ValueError, RuntimeError, LLMClientError):
        return CONSERVATIVE_FALLBACK, []
    finally:
        os.environ.pop("KB_ACTIVE_QUESTION", None)
