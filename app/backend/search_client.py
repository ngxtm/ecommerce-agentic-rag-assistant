from __future__ import annotations

import math
import os
from dataclasses import dataclass

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException
from requests_aws4auth import AWS4Auth

from app.backend.aws_auth import get_frozen_credentials
from app.backend.config import get_aws_region
from app.backend.llm_client import LLMClientError, generate_embedding

TARGET_DOC_ID = "amazon_10k_2019"
VECTOR_FIELD = "embedding"
LEXICAL_CANDIDATE_MULTIPLIER = 3
VECTOR_CANDIDATE_MULTIPLIER = 3
MIN_VECTOR_DIMENSIONS = 8


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
    return [{"term": {"doc_id.keyword": TARGET_DOC_ID}}]


def _build_lexical_query(question: str, top_k: int) -> dict[str, object]:
    return {
        "size": max(top_k * LEXICAL_CANDIDATE_MULTIPLIER, top_k),
        "query": {
            "bool": {
                "filter": _build_doc_filter(),
                "should": [
                    {
                        "multi_match": {
                            "query": question,
                            "fields": [
                                "title^4",
                                "section^4",
                                "item^4",
                                "subsection^3",
                                "table_name^3",
                                "metric^6",
                                "year^5",
                                "content^2",
                            ],
                            "type": "best_fields",
                            "operator": "or",
                        }
                    },
                    {
                        "multi_match": {
                            "query": question,
                            "fields": [
                                "title^8",
                                "section^8",
                                "item^8",
                                "subsection^5",
                                "table_name^6",
                                "metric^10",
                                "year^8",
                                "content^3",
                            ],
                            "type": "phrase",
                            "slop": 1,
                        }
                    },
                ],
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


def _merge_candidates(lexical_chunks: list[RetrievedChunk], vector_chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    for chunk in lexical_chunks + vector_chunks:
        existing = merged.get(chunk.chunk_id)
        if existing is None:
            merged[chunk.chunk_id] = chunk
            merged[chunk.chunk_id].score = chunk.lexical_score + chunk.vector_score
            continue
        existing.lexical_score = max(existing.lexical_score, chunk.lexical_score)
        existing.vector_score = max(existing.vector_score, chunk.vector_score)
        existing.score = existing.lexical_score + existing.vector_score
        if existing.embedding is None and chunk.embedding is not None:
            existing.embedding = chunk.embedding
    return sorted(
        merged.values(),
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
