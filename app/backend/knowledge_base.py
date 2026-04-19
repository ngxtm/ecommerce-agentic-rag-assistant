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


def _content_type_priority(chunk: RetrievedChunk, is_numeric: bool) -> int:
    if is_numeric:
        if chunk.content_type == "table_row":
            return 3
        if chunk.content_type == "table_block":
            return 2
        return 1
    if chunk.content_type == "narrative":
        return 3
    if chunk.content_type == "table_block":
        return 2
    return 1


def _rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    keywords = _extract_question_keywords(question)
    is_numeric = _is_numeric_question(question)
    if not keywords and not is_numeric:
        return chunks

    def rank_key(chunk: RetrievedChunk) -> tuple[float, float, float, float]:
        title_tokens = set(re.findall(r"[a-z0-9]+", chunk.title.casefold()))
        section_tokens = set(re.findall(r"[a-z0-9]+", chunk.section.casefold()))
        item_tokens = set(re.findall(r"[a-z0-9]+", (chunk.item or "").casefold()))
        subsection_tokens = set(re.findall(r"[a-z0-9]+", (chunk.subsection or "").casefold()))
        metric_tokens = set(re.findall(r"[a-z0-9]+", (chunk.metric or "").casefold()))
        table_tokens = set(re.findall(r"[a-z0-9]+", (chunk.table_name or "").casefold()))
        year_tokens = {chunk.year.casefold()} if chunk.year else set()
        overlap_score = (
            len(keywords & title_tokens) * 3
            + len(keywords & section_tokens) * 4
            + len(keywords & item_tokens) * 4
            + len(keywords & subsection_tokens) * 3
            + len(keywords & metric_tokens) * 6
            + len(keywords & table_tokens) * 3
            + len(keywords & year_tokens) * 6
        )
        type_score = _content_type_priority(chunk, is_numeric)
        retrieval_score = chunk.lexical_score + chunk.vector_score
        exact_match_bonus = 0
        if is_numeric and chunk.metric and chunk.metric.casefold() in question.casefold():
            exact_match_bonus += 6
        if is_numeric and chunk.year and chunk.year in question:
            exact_match_bonus += 6
        if not is_numeric and chunk.subsection and any(token in chunk.subsection.casefold() for token in keywords):
            exact_match_bonus += 3
        return (type_score, exact_match_bonus + overlap_score, retrieval_score, chunk.score)

    return sorted(chunks, key=rank_key, reverse=True)


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
    return _rerank_chunks(question, relevant_chunks)


def generate_grounded_answer(question: str, chunks: list[RetrievedChunk]) -> str:
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
    if chunk.subsection:
        return f"{chunk.title} - {chunk.section} - {chunk.subsection}"
    if chunk.section:
        return f"{chunk.title} - {chunk.section}"
    return chunk.title


def _build_sources(chunks: list[RetrievedChunk]) -> list[SourceItem]:
    seen: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        source_key = f"{chunk.doc_id}:{chunk.section}:{chunk.metric}:{chunk.year}:{chunk.chunk_id}"
        if source_key in seen:
            continue
        seen.add(source_key)
        snippet = chunk.content[:220]
        sources.append(
            SourceItem(
                source_id=chunk.chunk_id,
                title=_build_source_title(chunk),
                snippet=snippet,
                item=chunk.item,
                subsection=chunk.subsection,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                metric=chunk.metric,
                year=chunk.year,
                table_name=chunk.table_name,
            )
        )
    return sources


def answer_question(question: str) -> tuple[str, list[SourceItem]]:
    try:
        chunks = retrieve_relevant_chunks(question)
        if not chunks:
            return CONSERVATIVE_FALLBACK, []

        answer = generate_grounded_answer(question, chunks)
        if answer == CONSERVATIVE_FALLBACK:
            return answer, []
        return answer, _build_sources(chunks)
    except (ValueError, RuntimeError, LLMClientError):
        return CONSERVATIVE_FALLBACK, []
