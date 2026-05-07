from __future__ import annotations

import os

INDEX_SCHEMA_VERSION = "v4_true_hybrid_vector"
VECTOR_FIELD = "embedding"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
MIN_EMBEDDING_DIMENSIONS = 8
VECTOR_INDEX_ENGINE = "faiss"
VECTOR_INDEX_METHOD = "hnsw"
VECTOR_SPACE_TYPE = "cosinesimil"

def _validate_embedding_dimensions(dimensions: int) -> int:
    if dimensions < MIN_EMBEDDING_DIMENSIONS:
        raise ValueError(f"Embedding dimensions must be at least {MIN_EMBEDDING_DIMENSIONS}.")
    return dimensions

def get_embedding_dimensions_override() -> int | None:
    raw_value = os.getenv("LLM_EMBEDDING_DIMENSIONS")
    if raw_value is None or not raw_value.strip():
        return None
    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise ValueError("LLM_EMBEDDING_DIMENSIONS must be an integer.") from exc
    return _validate_embedding_dimensions(parsed_value)

def resolve_embedding_dimensions(preferred: int | None = None) -> int:
    if preferred is not None:
        return _validate_embedding_dimensions(preferred)
    configured = get_embedding_dimensions_override()
    if configured is not None:
        return configured
    return DEFAULT_EMBEDDING_DIMENSIONS

def build_vector_field_mapping(dimensions: int | None = None) -> dict[str, object]:
    resolved_dimensions = resolve_embedding_dimensions(dimensions)
    return {
        "type": "knn_vector",
        "dimension": resolved_dimensions,
        "method": {
            "engine": VECTOR_INDEX_ENGINE,
            "name": VECTOR_INDEX_METHOD,
            "space_type": VECTOR_SPACE_TYPE,
        },
    }
