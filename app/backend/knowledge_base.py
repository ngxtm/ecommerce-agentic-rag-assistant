from __future__ import annotations

import os

from app.backend.llm_client import LLMClientError, generate_chat_completion
from app.backend.models import SourceItem
from app.backend.search_client import RetrievedChunk, search_chunks


CONSERVATIVE_FALLBACK = "I do not have enough grounded context in the available documents to answer that confidently yet."
MIN_RETRIEVAL_SCORE = 0.1


def _format_context(chunks: list[RetrievedChunk]) -> str:
    sections = []
    for index, chunk in enumerate(chunks, start=1):
        sections.append(
            f"Source {index}:\n"
            f"Title: {chunk.title}\n"
            f"Section: {chunk.section or 'General'}\n"
            f"Content: {chunk.content}"
        )
    return "\n\n".join(sections)


def _build_messages(question: str, context: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a customer support knowledge assistant. Answer only from the provided context. "
                "If the context is insufficient, say that you do not have enough grounded context. Do not fabricate details."
            ),
        },
        {
            "role": "user",
            "content": (
                "Answer the question using only the provided context. "
                "If the context is insufficient, say that you do not have enough grounded context.\n\n"
                f"Question: {question}\n\n"
                f"Context:\n{context}"
            ),
        }
    ]


def retrieve_relevant_chunks(question: str, top_k: int = 4) -> list[RetrievedChunk]:
    chunks = search_chunks(question, top_k=top_k)
    return [chunk for chunk in chunks if chunk.score >= MIN_RETRIEVAL_SCORE]


def generate_grounded_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    answer = generate_chat_completion(_build_messages(question, _format_context(chunks)))
    return answer or CONSERVATIVE_FALLBACK


def _build_sources(chunks: list[RetrievedChunk]) -> list[SourceItem]:
    seen: set[str] = set()
    sources: list[SourceItem] = []
    for chunk in chunks:
        source_key = f"{chunk.doc_id}:{chunk.section}:{chunk.chunk_id}"
        if source_key in seen:
            continue
        seen.add(source_key)
        snippet = chunk.content[:220]
        sources.append(
            SourceItem(
                source_id=chunk.chunk_id,
                title=chunk.title if not chunk.section else f"{chunk.title} - {chunk.section}",
                snippet=snippet,
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
