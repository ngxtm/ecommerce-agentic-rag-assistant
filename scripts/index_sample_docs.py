from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from opensearchpy.exceptions import NotFoundError


ROOT_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DOCS_DIR = ROOT_DIR / "data" / "sample_docs"
MAX_CHUNK_CHARS = 800

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.search_client import _build_client


@dataclass
class ChunkDocument:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    content: str
    source_path: str
    source_uri: str
    updated_at: str


def _parse_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    lines = text.splitlines()
    title = "Untitled Document"
    sections: list[tuple[str, list[str]]] = []
    current_section = "Overview"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and title == "Untitled Document":
            title = stripped.removeprefix("# ").strip()
            continue
        if stripped.startswith("## "):
            if current_lines:
                sections.append((current_section, current_lines))
            current_section = stripped.removeprefix("## ").strip()
            current_lines = []
            continue
        if stripped:
            current_lines.append(stripped)

    if current_lines:
        sections.append((current_section, current_lines))

    normalized_sections = [(section, "\n".join(section_lines)) for section, section_lines in sections]
    return title, normalized_sections


def _chunk_text(section_text: str) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in section_text.split("\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph

    if current:
        chunks.append(current)
    return chunks


def build_documents() -> list[ChunkDocument]:
    bucket = os.getenv("DOCS_S3_BUCKET", "")
    prefix = os.getenv("DOCS_S3_PREFIX", "")
    updated_at = datetime.now(UTC).isoformat()
    documents: list[ChunkDocument] = []

    for path in sorted(SAMPLE_DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title, sections = _parse_sections(text)
        doc_id = path.stem
        for section, section_text in sections:
            for chunk in _chunk_text(section_text):
                source_key = f"{prefix}{path.name}" if prefix else path.name
                source_uri = f"s3://{bucket}/{source_key}" if bucket else str(path)
                documents.append(
                    ChunkDocument(
                        chunk_id=f"{doc_id}-{uuid4()}",
                        doc_id=doc_id,
                        title=title,
                        section=section,
                        content=chunk,
                        source_path=path.name,
                        source_uri=source_uri,
                        updated_at=updated_at,
                    )
                )

    return documents


def index_documents() -> int:
    index_name = os.getenv("OPENSEARCH_INDEX_NAME")
    if not index_name:
        raise ValueError("OPENSEARCH_INDEX_NAME is not configured.")

    client = _build_client()
    documents = build_documents()
    for document in documents:
        client.index(index=index_name, id=document.chunk_id, body=asdict(document), refresh=False)

    try:
        client.indices.refresh(index=index_name)
    except NotFoundError:
        # AOSS search collections may not expose refresh consistently; indexing is still durable.
        pass
    return len(documents)


if __name__ == "__main__":
    load_dotenv(ROOT_DIR / ".env")
    indexed_count = index_documents()
    print(f"Indexed {indexed_count} document chunks into OpenSearch.")
