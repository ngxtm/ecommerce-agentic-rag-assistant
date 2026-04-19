from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from opensearchpy.exceptions import ConnectionTimeout, NotFoundError

try:
    from pypdf import PdfReader
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly when dependency is absent
    PdfReader = None


ROOT_DIR = Path(__file__).resolve().parents[1]
COMPANY_PDF_PATH = ROOT_DIR / "docs" / "company" / "Company-10k-18pages.pdf"
AMAZON_10K_DOC_ID = "amazon_10k_2019"
LEGACY_MARKDOWN_DOC_IDS = (
    "shipping_policy",
    "returns_policy",
    "refund_policy",
    "order_tracking_faq",
)
MAX_CHUNK_CHARS = 800
PRIMARY_TABLE_SECTION = "Item 6. Selected Consolidated Financial Data"
YEAR_RE = re.compile(r"\b(2015|2016|2017|2018|2019)\b")
PART_RE = re.compile(r"^PART\s+([IVX]+)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"^(Item\s+\d+[A-Z]?\.)\s*(.*)$", re.IGNORECASE)
ITEM6_LABEL_RE = re.compile(r"Item\s*6\.\s*Selected\s+Consolidated\s+Financial\s+Data", re.IGNORECASE)
ITEM_HEADING_START_RE = re.compile(r"^(Item\s+\d+[A-Z]?\.)(.*)$", re.IGNORECASE)
ITEM_HEADING_TAIL_RE = re.compile(r"^(?P<title>[A-Za-z][A-Za-z ,’'\-()&]+?)(?:\s{2,}|\s+The following|\s+This |\s+Our |\s+We |\s+Year Ended|\s+December 31,|$)(?P<remainder>.*)$", re.IGNORECASE)
TABLE_HEADER_RE = re.compile(r"\(in\s+millions(?:,\s*except\s+per\s+share\s+data)?\)", re.IGNORECASE)
ITEM6_ROW_RE = re.compile(
    r"(?P<metric>Net sales|Operating income|Net income \(loss\)|Basic earnings per share(?: \(2\))?|Diluted earnings per share(?: \(2\))?|Basic|Diluted|Total assets|Total long-term obligations)\s+"
    r"(?P<v1>\(?\$?[\d,]+(?:\.\d+)?\)?)\s+"
    r"(?P<v2>\(?\$?[\d,]+(?:\.\d+)?\)?)\s+"
    r"(?P<v3>\(?\$?[\d,]+(?:\.\d+)?\)?)\s+"
    r"(?P<v4>\(?\$?[\d,]+(?:\.\d+)?\)?)\s+"
    r"(?P<v5>\(?\$?[\d,]+(?:\.\d+)?\)?)",
    re.IGNORECASE,
)
YEAR_HEADER_RE = re.compile(r"(?:Year Ended December 31,\s*)?(2015)\s+(2016)\s+(2017)\s+(?:\(\d+\)\s+)?(2018)\s+(2019)", re.IGNORECASE)
Y2019_TO_2015_RE = re.compile(r"(2019)\s+(2018)\s+(2017)\s+(2016)\s+(2015)")
METRIC_NORMALIZATION = {
    "Basic earnings per share (2)": "Basic earnings per share",
    "Diluted earnings per share (2)": "Diluted earnings per share",
}
KNOWN_ITEM_TITLES = {
    "Item 1.": "Business",
    "Item 1A.": "Risk Factors",
    "Item 1B.": "Unresolved Staff Comments",
    "Item 2.": "Properties",
    "Item 3.": "Legal Proceedings",
    "Item 4.": "Mine Safety Disclosures",
    "Item 5.": "Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
    "Item 6.": "Selected Consolidated Financial Data",
    "Item 7.": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "Item 7A.": "Quantitative and Qualitative Disclosures About Market Risk",
    "Item 8.": "Financial Statements and Supplementary Data",
    "Item 9.": "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
    "Item 9A.": "Controls and Procedures",
    "Item 9B.": "Other Information",
}
TOC_LINE_RE = re.compile(
    r"^(INDEX|TABLE OF CONTENTS|PART\s+[IVX]+|Item\s+\d+[A-Z]?\.|\d+\s*$|[A-Za-z].+\.{2,}\s*\d+)$",
    re.IGNORECASE,
)
HEADER_FOOTER_RE = re.compile(r"^(AMAZON\.COM,\s*INC\.?|FORM\s+10-K|Page\s+\d+|\d+)$", re.IGNORECASE)
TABLE_METRICS = {
    "Net sales": "million USD",
    "Operating income": "million USD",
    "Net income": "million USD",
    "Cash and cash equivalents": "million USD",
    "Total assets": "million USD",
    "Long-term debt": "million USD",
    "Basic earnings per share": "USD/share",
    "Diluted earnings per share": "USD/share",
}

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


@dataclass
class SectionBlock:
    part: str | None
    item: str | None
    subsection: str | None
    section_label: str
    lines: list[str]
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class TableExtraction:
    table_block: str
    row_chunks: list[ChunkDocument]


def _s3_source_uri(path: Path) -> str:
    bucket = os.getenv("DOCS_S3_BUCKET", "")
    prefix = os.getenv("DOCS_S3_PREFIX", "")
    source_key = f"{prefix}{path.name}" if prefix else path.name
    return f"s3://{bucket}/{source_key}" if bucket else str(path)


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


def _normalize_text_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_decorative(line: str) -> bool:
    return bool(line) and all(char in "._-–— " for char in line)


def _is_toc_line(line: str) -> bool:
    normalized = _normalize_text_line(line)
    if not normalized:
        return False
    if TOC_LINE_RE.match(normalized):
        return True
    if ". ." in normalized or re.search(r"\.{3,}\s*\d+$", normalized):
        return True
    return False


def _clean_pdf_line(line: str) -> str | None:
    normalized = _normalize_text_line(line)
    if not normalized:
        return None
    if normalized.upper().startswith("TABLE OF CONTENTS"):
        normalized = normalized[len("Table of Contents") :].strip()
        if not normalized:
            return None
    if HEADER_FOOTER_RE.match(normalized):
        return None
    if _is_decorative(normalized):
        return None
    return normalized


def _extract_pdf_pages(path: Path) -> list[tuple[int, list[str]]]:
    if PdfReader is None:
        raise ModuleNotFoundError("pypdf is required to index the 10-K PDF. Install dependencies from requirements.txt.")
    reader = PdfReader(str(path))
    pages: list[tuple[int, list[str]]] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = []
        for raw_line in text.splitlines():
            cleaned = _clean_pdf_line(raw_line)
            if cleaned is not None:
                lines.append(cleaned)
        pages.append((page_index, lines))
    return pages


def _extract_pdf_metadata(pages: list[tuple[int, list[str]]]) -> tuple[str, str | None, str | None]:
    cover_lines = pages[0][1] if pages else []
    cover_text = "\n".join(cover_lines)

    company_name = "Amazon.com, Inc."
    filing_type = "FORM 10-K" if "FORM 10-K" in cover_text.upper() else None
    fiscal_year = None
    match = re.search(r"Fiscal Year Ended\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", cover_text, re.IGNORECASE)
    if match:
        fiscal_year = match.group(1)
    elif re.search(r"2019", cover_text):
        fiscal_year = "December 31, 2019"

    return company_name, filing_type, fiscal_year


def _remove_toc_pages(pages: list[tuple[int, list[str]]]) -> list[tuple[int, list[str]]]:
    filtered_pages: list[tuple[int, list[str]]] = []
    for page_number, lines in pages:
        joined_page = " ".join(lines).upper()
        has_toc_header = any(line.upper() in {"INDEX", "TABLE OF CONTENTS"} for line in lines)
        toc_like_lines = sum(1 for line in lines if _is_toc_line(line))
        substantive_lines = sum(1 for line in lines if not _is_toc_line(line))
        is_toc_page = has_toc_header or (
            "TABLE OF CONTENTS" in joined_page
            or ("INDEX" in joined_page and "ITEM 1." in joined_page and "PART I" in joined_page)
        )
        if not is_toc_page and toc_like_lines >= 4 and substantive_lines <= 2:
            is_toc_page = True
        if is_toc_page:
            continue
        filtered_pages.append((page_number, lines))
    return filtered_pages


def _is_index_noise(section: SectionBlock, chunk: str) -> bool:
    upper_chunk = chunk.upper()
    if section.section_label == "Overview" and ("TABLE OF CONTENTS" in upper_chunk or ("INDEX" in upper_chunk and "ITEM 1." in upper_chunk and "PART I" in upper_chunk)):
        return True
    return False


def _doc_id_exists(client: object, index_name: str, doc_id: str) -> bool:
    response = client.search(
        index=index_name,
        body={
            "size": 0,
            "query": {"term": {"doc_id.keyword": doc_id}},
        },
    )
    total = response.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return int(total.get("value", 0)) > 0
    return int(total or 0) > 0


def _clear_doc_id(client: object, index_name: str, doc_id: str) -> None:
    for _ in range(20):
        _delete_existing_doc_chunks(client, index_name, doc_id)
        try:
            client.indices.refresh(index=index_name)
        except NotFoundError:
            pass
        if not _doc_id_exists(client, index_name, doc_id):
            return

    raise RuntimeError(f"Failed to fully clear doc_id from index: {doc_id}")


def _clear_target_doc_ids(client: object, index_name: str) -> None:
    for doc_id in (AMAZON_10K_DOC_ID, *LEGACY_MARKDOWN_DOC_IDS):
        _clear_doc_id(client, index_name, doc_id)

    smoke_doc_count = _count_documents_by_doc_id(client, index_name, "smoke_doc")
    if smoke_doc_count:
        _clear_doc_id(client, index_name, "smoke_doc")

    try:
        client.indices.refresh(index=index_name)
    except NotFoundError:
        pass


def _verify_expected_doc_ids(client: object, index_name: str) -> None:
    response = client.search(
        index=index_name,
        body={
            "size": 0,
            "aggs": {"doc_ids": {"terms": {"field": "doc_id.keyword", "size": 20}}},
        },
    )
    buckets = response.get("aggregations", {}).get("doc_ids", {}).get("buckets", [])
    unexpected = [bucket.get("key") for bucket in buckets if bucket.get("key") != AMAZON_10K_DOC_ID]
    if unexpected:
        raise RuntimeError(f"Unexpected doc_ids remain in index: {unexpected}")



def _deduplicate_documents(documents: list[ChunkDocument]) -> list[ChunkDocument]:
    seen: set[tuple[str, str, str | None, str | None, int | None, int | None, str]] = set()
    unique_documents: list[ChunkDocument] = []
    for document in documents:
        key = (
            document.doc_id,
            document.section,
            document.metric,
            document.year,
            document.page_start,
            document.page_end,
            document.content,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_documents.append(document)
    return unique_documents


def _count_documents_by_doc_id(client: object, index_name: str, doc_id: str) -> int:
    response = client.search(
        index=index_name,
        body={
            "size": 0,
            "query": {"term": {"doc_id.keyword": doc_id}},
        },
    )
    total = response.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total or 0)


def _verify_doc_id_cleanup(client: object, index_name: str) -> None:
    for doc_id in LEGACY_MARKDOWN_DOC_IDS:
        remaining = _count_documents_by_doc_id(client, index_name, doc_id)
        if remaining:
            raise RuntimeError(f"Legacy markdown doc_id still present after cleanup: {doc_id} ({remaining})")
    if _count_documents_by_doc_id(client, index_name, AMAZON_10K_DOC_ID) <= 0:
        raise RuntimeError("10-K corpus was not present after indexing.")


def _verify_no_overview_index_noise(documents: list[ChunkDocument]) -> None:
    for document in documents:
        if document.section == "Overview" and _is_index_noise(SectionBlock(None, None, None, document.section, [], document.page_start, document.page_end), document.content):
            raise RuntimeError("TOC/INDEX noise leaked into the indexed 10-K corpus.")
    return None




def _is_probable_subsection(line: str) -> bool:
    if PART_RE.match(line) or ITEM_RE.match(line):
        return False
    if len(line) > 120:
        return False
    if YEAR_RE.search(line):
        return False
    words = line.split()
    if len(words) > 14:
        return False
    if line.endswith(":"):
        return True
    capitalized = sum(1 for word in words if word[:1].isupper())
    return capitalized >= max(1, len(words) - 1)


def _split_item_title_and_remainder(item_prefix: str, item_text: str) -> tuple[str, str]:
    normalized_text = _normalize_text_line(item_text)
    known_title = KNOWN_ITEM_TITLES.get(item_prefix)
    if known_title:
        collapsed_known = re.sub(r"\s+", "", known_title).casefold()
        collapsed_text = re.sub(r"\s+", "", normalized_text).casefold()
        if collapsed_text.startswith(collapsed_known):
            remainder = normalized_text[len(known_title):].strip()
            return known_title, remainder
    heading_match = ITEM_HEADING_TAIL_RE.match(normalized_text)
    if heading_match:
        item_title = heading_match.group("title").strip()
        remainder = heading_match.group("remainder").strip()
        return item_title, remainder
    return normalized_text, ""


def _parse_item_heading(line: str) -> tuple[str, str, str] | None:
    normalized = _normalize_text_line(line)
    if not normalized:
        return None
    item_match = ITEM_HEADING_START_RE.match(normalized)
    if not item_match:
        return None
    item_prefix = item_match.group(1).replace("  ", " ").strip()
    item_title, remainder = _split_item_title_and_remainder(item_prefix, item_match.group(2).strip())
    return item_prefix, item_title, remainder


def _split_pdf_into_sections(pages: list[tuple[int, list[str]]]) -> list[SectionBlock]:
    sections: list[SectionBlock] = []
    current = SectionBlock(part=None, item=None, subsection=None, section_label="Overview", lines=[])

    def flush() -> None:
        if current.lines:
            sections.append(
                SectionBlock(
                    part=current.part,
                    item=current.item,
                    subsection=current.subsection,
                    section_label=current.section_label,
                    lines=current.lines.copy(),
                    page_start=current.page_start,
                    page_end=current.page_end,
                )
            )
            current.lines.clear()

    for page_number, lines in pages:
        for line in lines:
            part_match = PART_RE.match(line)
            item_heading = _parse_item_heading(line)

            if part_match:
                flush()
                current.part = f"PART {part_match.group(1).upper()}"
                current.item = None
                current.subsection = None
                current.section_label = current.part
                current.page_start = page_number
                current.page_end = page_number
                continue

            if item_heading:
                flush()
                item_prefix, item_title, remainder = item_heading
                current.item = f"{item_prefix} {item_title}".strip()
                current.subsection = None
                current.section_label = current.item
                current.page_start = page_number
                current.page_end = page_number
                if remainder:
                    current.lines.append(remainder)
                continue

            if current.item and _is_probable_subsection(line):
                flush()
                current.subsection = line
                current.section_label = current.item
                current.page_start = page_number
                current.page_end = page_number
                continue

            if not current.page_start:
                current.page_start = page_number
            current.page_end = page_number
            current.lines.append(line)

    flush()
    return [section for section in sections if section.lines]


def _infer_unit(metric: str, default_unit: str | None) -> str | None:
    if metric in TABLE_METRICS:
        return TABLE_METRICS[metric]
    return default_unit


def _normalize_numeric_value(value_raw: str) -> float | None:
    cleaned = value_raw.replace(",", "").replace("$", "").strip()
    cleaned = cleaned.strip("()")
    if not cleaned or cleaned in {"-", "—"}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value_raw.strip().startswith("(") and value_raw.strip().endswith(")"):
        value *= -1
    return value


def _extract_item6_table(section: SectionBlock, source_path: Path, updated_at: str, source_uri: str, company_name: str, filing_type: str | None, fiscal_year: str | None) -> TableExtraction | None:
    joined_text = "\n".join(section.lines)
    normalized_text = _normalize_text_line(joined_text)
    if not ITEM6_LABEL_RE.search(section.section_label) and not ITEM6_LABEL_RE.search(normalized_text):
        return None
    if not YEAR_RE.search(normalized_text):
        return None

    default_unit = "million USD" if TABLE_HEADER_RE.search(normalized_text) else None
    year_match = YEAR_HEADER_RE.search(normalized_text) or Y2019_TO_2015_RE.search(normalized_text)
    years = list(year_match.groups()) if year_match else ["2015", "2016", "2017", "2018", "2019"]
    row_chunks: list[ChunkDocument] = []

    for match in ITEM6_ROW_RE.finditer(normalized_text):
        metric = re.sub(r"\s+", " ", match.group("metric")).strip()
        metric = METRIC_NORMALIZATION.get(metric, metric)
        unit = _infer_unit(metric, default_unit)
        values = [match.group("v1"), match.group("v2"), match.group("v3"), match.group("v4"), match.group("v5")]
        for year, value_raw in zip(years, values, strict=False):
            normalized = _normalize_numeric_value(value_raw)
            row_chunks.append(
                ChunkDocument(
                    chunk_id=f"{AMAZON_10K_DOC_ID}-{uuid4()}",
                    doc_id=AMAZON_10K_DOC_ID,
                    title="Amazon.com, Inc. Form 10-K",
                    section=PRIMARY_TABLE_SECTION,
                    content=f"{metric} for {year}: {value_raw}",
                    source_path=source_path.name,
                    source_uri=source_uri,
                    updated_at=updated_at,
                    part=section.part,
                    item=section.item,
                    subsection=section.subsection,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    filing_type=filing_type,
                    fiscal_year=fiscal_year,
                    company_name=company_name,
                    content_type="table_row",
                    table_name=PRIMARY_TABLE_SECTION,
                    metric=metric,
                    year=year,
                    value_raw=value_raw,
                    value_normalized=normalized,
                    unit=unit,
                )
            )

    if not row_chunks:
        return None

    return TableExtraction(table_block=normalized_text, row_chunks=row_chunks)


def _build_pdf_documents(path: Path, updated_at: str) -> list[ChunkDocument]:
    if not path.exists():
        return []

    source_uri = _s3_source_uri(path)
    pages = _remove_toc_pages(_extract_pdf_pages(path))
    company_name, filing_type, fiscal_year = _extract_pdf_metadata(pages)
    sections = _split_pdf_into_sections(pages)
    documents: list[ChunkDocument] = []

    for section in sections:
        section_text = "\n".join(section.lines)
        if not section_text.strip():
            continue
        if _is_index_noise(section, section_text):
            continue
        if section.section_label == "Overview":
            continue

        table_extraction = _extract_item6_table(section, path, updated_at, source_uri, company_name, filing_type, fiscal_year)
        if table_extraction:
            documents.extend(table_extraction.row_chunks)
            documents.append(
                ChunkDocument(
                    chunk_id=f"{AMAZON_10K_DOC_ID}-{uuid4()}",
                    doc_id=AMAZON_10K_DOC_ID,
                    title="Amazon.com, Inc. Form 10-K",
                    section=section.section_label,
                    content=table_extraction.table_block,
                    source_path=path.name,
                    source_uri=source_uri,
                    updated_at=updated_at,
                    part=section.part,
                    item=section.item,
                    subsection=section.subsection,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    filing_type=filing_type,
                    fiscal_year=fiscal_year,
                    company_name=company_name,
                    content_type="table_block",
                    table_name=PRIMARY_TABLE_SECTION,
                )
            )

        for chunk in _chunk_text(section_text):
            documents.append(
                ChunkDocument(
                    chunk_id=f"{AMAZON_10K_DOC_ID}-{uuid4()}",
                    doc_id=AMAZON_10K_DOC_ID,
                    title="Amazon.com, Inc. Form 10-K",
                    section=section.section_label,
                    content=chunk,
                    source_path=path.name,
                    source_uri=source_uri,
                    updated_at=updated_at,
                    part=section.part,
                    item=section.item,
                    subsection=section.subsection,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    filing_type=filing_type,
                    fiscal_year=fiscal_year,
                    company_name=company_name,
                    content_type="narrative",
                )
            )

    return documents


def build_documents() -> list[ChunkDocument]:
    updated_at = datetime.now(UTC).isoformat()
    documents = _build_pdf_documents(COMPANY_PDF_PATH, updated_at)
    documents = _deduplicate_documents(documents)
    _verify_no_overview_index_noise(documents)
    return documents


def _delete_existing_doc_chunks(client: object, index_name: str, doc_id: str) -> None:
    query = {"query": {"term": {"doc_id.keyword": doc_id}}}
    try:
        client.delete_by_query(index=index_name, body=query, conflicts="proceed")
    except NotFoundError:
        pass


def _index_with_retry(client: object, index_name: str, document: ChunkDocument, retries: int = 3) -> None:
    payload = asdict(document)
    for attempt in range(1, retries + 1):
        try:
            client.index(index=index_name, id=document.chunk_id, body=payload, refresh=False)
            return
        except ConnectionTimeout:
            if attempt == retries:
                raise
            time.sleep(attempt)


def index_documents() -> int:
    index_name = os.getenv("OPENSEARCH_INDEX_NAME")
    if not index_name:
        raise ValueError("OPENSEARCH_INDEX_NAME is not configured.")

    client = _build_client()
    documents = build_documents()
    if documents:
        _clear_target_doc_ids(client, index_name)

    for document in documents:
        _index_with_retry(client, index_name, document)

    try:
        client.indices.refresh(index=index_name)
    except NotFoundError:
        pass
    _verify_doc_id_cleanup(client, index_name)
    return len(documents)


if __name__ == "__main__":
    load_dotenv(ROOT_DIR / ".env")
    indexed_count = index_documents()
    print(f"Indexed {indexed_count} document chunks into OpenSearch.")
