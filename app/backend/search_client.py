from __future__ import annotations

import os
from dataclasses import dataclass

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException
from requests_aws4auth import AWS4Auth

from app.backend.aws_auth import get_frozen_credentials


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


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.removeprefix("https://").removeprefix("http://")


def _build_client() -> OpenSearch:
    region = os.getenv("AWS_REGION")
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


def search_chunks(question: str, top_k: int = 4) -> list[RetrievedChunk]:
    index_name = os.getenv("OPENSEARCH_INDEX_NAME")
    if not index_name:
        raise ValueError("OPENSEARCH_INDEX_NAME is not configured.")

    client = _build_client()
    query = {
        "size": top_k,
        "query": {
            "multi_match": {
                "query": question,
                "fields": ["title^3", "section^2", "content"],
                "type": "best_fields",
                "operator": "or",
            }
        },
    }

    try:
        response = client.search(index=index_name, body=query)
    except OpenSearchException as exc:
        raise RuntimeError("OpenSearch search failed.") from exc

    hits = response.get("hits", {}).get("hits", [])
    chunks: list[RetrievedChunk] = []
    for hit in hits:
        source = hit.get("_source", {})
        content = source.get("content", "")
        if not content.strip():
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=source.get("chunk_id", hit.get("_id", "")),
                doc_id=source.get("doc_id", ""),
                title=source.get("title", "Untitled"),
                section=source.get("section", ""),
                content=content,
                source_path=source.get("source_path", ""),
                source_uri=source.get("source_uri", ""),
                score=float(hit.get("_score", 0.0)),
            )
        )
    return chunks
