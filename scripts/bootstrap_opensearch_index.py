from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.search_client import _build_client  # noqa: E402
from scripts.index_sample_docs import ensure_index_exists  # noqa: E402


def main() -> int:
    index_name = os.getenv("OPENSEARCH_INDEX_NAME")
    if not index_name:
        raise ValueError("OPENSEARCH_INDEX_NAME is not configured.")
    client = _build_client()
    ensure_index_exists(client, index_name)
    print(f"Ensured OpenSearch index '{index_name}' exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
