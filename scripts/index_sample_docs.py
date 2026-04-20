from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from opensearchpy.exceptions import ConnectionTimeout, NotFoundError, RequestError

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
INDEX_SCHEMA_VERSION = "v2_parser_foundation"
PRIMARY_TABLE_SECTION = "Item 6. Selected Consolidated Financial Data"
EXECUTIVE_OFFICERS_SECTION = "Executive Officers and Directors"
ITEM_1A_SECTION = "Item 1A. Risk Factors"
ITEM_7_SECTION = "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations"
EXECUTIVE_OFFICER_NAMES = (
    "Jeffrey P. Bezos",
    "Jeffrey M. Blackburn",
    "Andrew R. Jassy",
    "Brian T. Olsavsky",
    "Shelley L. Reynolds",
    "Jeffrey A. Wilke",
    "David A. Zapolsky",
)
YEAR_RE = re.compile(r"\b(2015|2016|2017|2018|2019)\b")
PART_RE = re.compile(r"^PART\s+([IVX]+)\b", re.IGNORECASE)
ITEM_HEADING_START_RE = re.compile(r"^(Item\s+\d+[A-Z]?\.)(.*)$", re.IGNORECASE)
ITEM_HEADING_TAIL_RE = re.compile(
    r"^(?P<title>[A-Za-z][A-Za-z ,’'\-()&/]+?)(?:\s{2,}|\s+The following|\s+This |\s+Our |\s+We |\s+Year Ended|\s+December 31,|$)(?P<remainder>.*)$",
    re.IGNORECASE,
)
TABLE_HEADER_RE = re.compile(r"\(in\s+millions(?:,\s*except\s+per\s+share\s+data)?\)", re.IGNORECASE)
ITEM6_LABEL_RE = re.compile(r"Item\s*6\.\s*Selected\s+Consolidated\s+Financial\s+Data", re.IGNORECASE)
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
TOC_LINE_RE = re.compile(
    r"^(INDEX|TABLE OF CONTENTS|PART\s+[IVX]+|Item\s+\d+[A-Z]?\.|\d+\s*$|[A-Za-z].+\.{2,}\s*\d+)$",
    re.IGNORECASE,
)
HEADER_FOOTER_RE = re.compile(r"^(AMAZON\.COM,\s*INC\.?|FORM\s+10-K|Page\s+\d+|\d+)$", re.IGNORECASE)
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
TABLE_METRICS = {
    "Net sales": "million USD",
    "Operating income": "million USD",
    "Net income": "million USD",
    "Total assets": "million USD",
    "Basic earnings per share": "USD/share",
    "Diluted earnings per share": "USD/share",
}
METRIC_NORMALIZATION = {
    "Basic earnings per share (2)": "Basic earnings per share",
    "Diluted earnings per share (2)": "Diluted earnings per share",
}
MDA_HEADING_HINTS = (
    "Results of Operations",
    "Liquidity and Capital Resources",
    "Critical Accounting Policies",
    "Overview",
)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.search_client import _build_client


INDEX_SETTINGS = {
    "index": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
    }
}

INDEX_MAPPINGS = {
    "dynamic": True,
    "properties": {
        "chunk_id": {"type": "keyword"},
        "doc_id": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "section": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "content": {"type": "text"},
        "source_path": {"type": "keyword"},
        "source_uri": {"type": "keyword"},
        "updated_at": {"type": "date"},
        "index_version": {"type": "keyword"},
        "part": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "item": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "subsection": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "page_start": {"type": "integer"},
        "page_end": {"type": "integer"},
        "filing_type": {"type": "keyword"},
        "fiscal_year": {"type": "keyword"},
        "company_name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "content_type": {"type": "keyword"},
        "table_name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "metric": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "year": {"type": "keyword"},
        "value_raw": {"type": "keyword"},
        "value_normalized": {"type": "float"},
        "unit": {"type": "keyword"},
        "entity_name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "entity_role": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
        "embedding": {"type": "float"},
    },
}


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
    index_version: str = INDEX_SCHEMA_VERSION
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
    entity_name: str | None = None
    entity_role: str | None = None
    embedding: list[float] | None = None


@dataclass
class NormalizedLine:
    page_number: int
    text: str
    raw_text: str
    source_index: int


@dataclass
class DocumentBlock:
    part: str | None
    item: str | None
    label: str
    lines: list[NormalizedLine]
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class RefinedBlock:
    part: str | None
    item: str | None
    section: str
    subsection: str | None
    block_type: str
    lines: list[str]
    page_start: int | None = None
    page_end: int | None = None
    table_name: str | None = None
    metric: str | None = None
    year: str | None = None
    value_raw: str | None = None
    value_normalized: float | None = None
    unit: str | None = None
    entity_name: str | None = None
    entity_role: str | None = None


def _mapping_supports_doc_id_keyword(client: object, index_name: str) -> bool:
    try:
        mapping = client.indices.get_mapping(index=index_name)
    except NotFoundError:
        return False
    index_mapping = mapping.get(index_name, {}) if isinstance(mapping, dict) else {}
    properties = index_mapping.get("mappings", {}).get("properties", {}) if isinstance(index_mapping, dict) else {}
    doc_id_mapping = properties.get("doc_id", {}) if isinstance(properties, dict) else {}
    entity_name_mapping = properties.get("entity_name", {}) if isinstance(properties, dict) else {}
    index_version_mapping = properties.get("index_version", {}) if isinstance(properties, dict) else {}
    fields = doc_id_mapping.get("fields", {}) if isinstance(doc_id_mapping, dict) else {}
    keyword_mapping = fields.get("keyword", {}) if isinstance(fields, dict) else {}
    return (
        isinstance(keyword_mapping, dict)
        and keyword_mapping.get("type") == "keyword"
        and isinstance(entity_name_mapping, dict)
        and isinstance(index_version_mapping, dict)
        and index_version_mapping.get("type") == "keyword"
    )


def _normalize_text_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _stable_content_hash(*parts: str) -> str:
    normalized = "|".join(_normalize_text_line(part) for part in parts if part is not None)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _build_chunk_id(*parts: str) -> str:
    return _stable_content_hash(*parts)


def _s3_source_uri(path: Path) -> str:
    bucket = os.getenv("DOCS_S3_BUCKET", "")
    prefix = os.getenv("DOCS_S3_PREFIX", "")
    source_key = f"{prefix}{path.name}" if prefix else path.name
    return f"s3://{bucket}/{source_key}" if bucket else str(path)


def _is_decorative(line: str) -> bool:
    return bool(line) and all(char in "._-–— " for char in line)


def _is_toc_line(line: str) -> bool:
    normalized = _normalize_text_line(line)
    if not normalized:
        return False
    if TOC_LINE_RE.match(normalized):
        return True
    return bool(". ." in normalized or re.search(r"\.{3,}\s*\d+$", normalized))


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
        is_toc_page = has_toc_header or ("TABLE OF CONTENTS" in joined_page or ("INDEX" in joined_page and "ITEM 1." in joined_page and "PART I" in joined_page))
        if not is_toc_page and toc_like_lines >= 4 and substantive_lines <= 2:
            is_toc_page = True
        if is_toc_page:
            continue
        filtered_pages.append((page_number, lines))
    return filtered_pages


def _normalize_pdf_lines(pages: list[tuple[int, list[str]]]) -> list[NormalizedLine]:
    normalized_lines: list[NormalizedLine] = []
    for page_number, lines in pages:
        for source_index, raw_line in enumerate(lines):
            text = _normalize_text_line(raw_line)
            if not text:
                continue
            normalized_lines.append(NormalizedLine(page_number=page_number, text=text, raw_text=raw_line, source_index=source_index))
    return normalized_lines


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
        return heading_match.group("title").strip(), heading_match.group("remainder").strip()
    return normalized_text, ""


def _parse_item_heading(line: str) -> tuple[str, str, str] | None:
    normalized = _normalize_text_line(line)
    item_match = ITEM_HEADING_START_RE.match(normalized)
    if not item_match:
        return None
    item_prefix = item_match.group(1).replace("  ", " ").strip()
    item_title, remainder = _split_item_title_and_remainder(item_prefix, item_match.group(2).strip())
    return item_prefix, item_title, remainder


def _build_document_skeleton(lines: list[NormalizedLine]) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    current = DocumentBlock(part=None, item=None, label="Overview", lines=[])

    def flush() -> None:
        nonlocal current
        if not current.lines:
            return
        current.page_start = current.lines[0].page_number
        current.page_end = current.lines[-1].page_number
        blocks.append(current)
        current = DocumentBlock(part=current.part, item=current.item, label=current.label, lines=[])

    for line in lines:
        part_match = PART_RE.match(line.text)
        item_heading = _parse_item_heading(line.text)
        if part_match:
            flush()
            current = DocumentBlock(part=f"PART {part_match.group(1).upper()}", item=None, label=f"PART {part_match.group(1).upper()}", lines=[])
            continue
        if item_heading:
            flush()
            item_prefix, item_title, remainder = item_heading
            current = DocumentBlock(part=current.part, item=f"{item_prefix} {item_title}".strip(), label=f"{item_prefix} {item_title}".strip(), lines=[])
            if remainder:
                current.lines.append(NormalizedLine(page_number=line.page_number, text=remainder, raw_text=remainder, source_index=line.source_index))
            continue
        current.lines.append(line)
    flush()
    return [block for block in blocks if block.lines]


def _is_index_noise(content: str) -> bool:
    upper_content = content.upper()
    return "TABLE OF CONTENTS" in upper_content or ("INDEX" in upper_content and "ITEM 1." in upper_content and "PART I" in upper_content)


def _make_block(block: DocumentBlock, section: str, subsection: str | None, block_type: str, lines: list[str], **extra: object) -> RefinedBlock:
    return RefinedBlock(
        part=block.part,
        item=block.item,
        section=section,
        subsection=subsection,
        block_type=block_type,
        lines=lines,
        page_start=block.page_start,
        page_end=block.page_end,
        table_name=extra.get("table_name"),
        metric=extra.get("metric"),
        year=extra.get("year"),
        value_raw=extra.get("value_raw"),
        value_normalized=extra.get("value_normalized"),
        unit=extra.get("unit"),
        entity_name=extra.get("entity_name"),
        entity_role=extra.get("entity_role"),
    )


def _default_item_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    text = [_normalize_text_line(line.text) for line in block.lines if _normalize_text_line(line.text)]
    if not text:
        return []
    return [_make_block(block, block.item or block.label, None, "narrative", text)]


def _overview_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    text = " ".join(line.text for line in block.lines)
    if not text or _is_index_noise(text):
        return []
    factual_lines = []
    for line in (entry.text for entry in block.lines):
        lowered = line.casefold()
        if "available information" in lowered or "investor relations" in lowered or "executive officers and directors" in lowered or "seattle, washington" in lowered:
            factual_lines.append(line)
    if not factual_lines:
        return []
    return [_make_block(block, "Overview", None, "fact", factual_lines)]


def _extract_executive_rows(text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    officers_block = text
    if "Information About Our Executive Officers" in officers_block and "Board of Directors" in officers_block:
        officers_block = officers_block.split("Information About Our Executive Officers", 1)[1].split("Board of Directors", 1)[0].strip()
    name_pattern = "|".join(re.escape(name) for name in EXECUTIVE_OFFICER_NAMES)
    row_re = re.compile(
        rf"(?P<name>{name_pattern})\s+(?P<age>\d{{2}})\s+(?P<role>.*?)(?=(?:{name_pattern})\s+\d{{2}}|(?:{name_pattern})\.|Board of Directors|$)",
        re.DOTALL,
    )
    for match in row_re.finditer(officers_block):
        name = _normalize_text_line(match.group("name"))
        age = match.group("age")
        role = _normalize_text_line(match.group("role")).strip(" .:")
        role = re.sub(r"([A-Za-z])([A-Z][a-z])", r"\1 \2", role)
        if role:
            rows.append((name, age, role))
    return rows


def _extract_executive_bios(text: str) -> list[tuple[str, str]]:
    bios: list[tuple[str, str]] = []
    for index, name in enumerate(EXECUTIVE_OFFICER_NAMES):
        marker = f"{name}."
        if marker not in text:
            continue
        bio_start = text.index(marker) + len(marker)
        remaining = text[bio_start:]
        next_markers = [f"{candidate}." for candidate in EXECUTIVE_OFFICER_NAMES[index + 1 :] if f"{candidate}." in remaining]
        bio_end = len(remaining)
        if next_markers:
            bio_end = min(remaining.index(candidate) for candidate in next_markers)
        if "Board of Directors" in remaining[:bio_end]:
            bio_end = remaining.index("Board of Directors")
        bio = re.sub(r"\s+", " ", remaining[:bio_end]).strip()
        if bio:
            bios.append((name, bio))
    return bios


def _executive_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    text = " ".join(line.text for line in block.lines)
    if EXECUTIVE_OFFICERS_SECTION.casefold() not in text.casefold():
        return []
    refined: list[RefinedBlock] = []
    rows = _extract_executive_rows(text)
    bios = _extract_executive_bios(text)
    for name, age, role in rows:
        refined.append(_make_block(block, EXECUTIVE_OFFICERS_SECTION, "Information About Our Executive Officers", "profile_row", [f"{name}, age {age}, serves as {role}."], entity_name=name, entity_role=role, year=age))
    for name, bio in bios:
        refined.append(_make_block(block, EXECUTIVE_OFFICERS_SECTION, "Executive Officer Biographies", "profile_bio", [f"{name}. {bio}"], entity_name=name))
    if rows:
        trimmed = text
        if "Information About Our Executive Officers" in trimmed:
            trimmed = trimmed.split("Information About Our Executive Officers", 1)[1]
        if "Board of Directors" in trimmed:
            trimmed = trimmed.split("Board of Directors", 1)[0]
        trimmed = trimmed.strip()
        if trimmed:
            refined.append(_make_block(block, EXECUTIVE_OFFICERS_SECTION, "Information About Our Executive Officers", "narrative", [trimmed]))
    return refined


def _is_risk_heading(line: str) -> bool:
    words = line.split()
    if len(words) < 5 or len(words) > 30:
        return False
    if YEAR_RE.search(line):
        return False
    if line.endswith("."):
        return False
    lowercase_words = sum(1 for word in words if word.islower())
    return lowercase_words >= 2 and not line.startswith("We ")


def _split_embedded_risk_heading(line: str) -> tuple[str, str] | None:
    normalized = _normalize_text_line(line)
    if not normalized or len(normalized.split()) < 10:
        return None
    match = re.match(r"^(?P<heading>.+?(?:Could Harm Our Business|May Harm Our Business|May Adversely Affect Our Business|Could Adversely Affect Our Business))\s+(?P<body>Our |We |This ).*$", normalized)
    if not match:
        return None
    heading = _normalize_text_line(match.group("heading"))
    body = normalized[len(heading):].strip()
    if _is_risk_heading(heading) and body:
        return heading, body
    return None


def _extract_risk_sections_from_text(text: str) -> list[tuple[str, str]]:
    normalized = _normalize_text_line(re.sub(r"(?<=[a-z\)])(?=[A-Z])", " ", text))
    if not normalized:
        return []
    sections: list[tuple[str, str]] = []
    key_personnel_match = re.search(
        r"(?P<heading>The Loss of Key Senior Management Personnel.*?Could (?:Harm|Negatively Affect) Our Business)\s+(?P<body>We depend on our senior management.*?)(?=(?:We Could Be Harmed by Data Loss or Other Security Breaches|We Face Risks Related to System Interruption and Lack of Redundancy|We Face Significant Inventory Risk|We Face Risks Related to Adequately Protecting Our Intellectual Property Rights)|$)",
        normalized,
    )
    if key_personnel_match:
        sections.append(
            (
                _normalize_text_line(key_personnel_match.group("heading")),
                _normalize_text_line(key_personnel_match.group("body")),
            )
        )
    pattern = re.compile(
        r"(?P<heading>[A-Z][A-Za-z0-9,;:'’\-()&/ ]+?(?:Could Harm Our Business|May Harm Our Business|May Adversely Affect Our Business|Could Adversely Affect Our Business))\s+(?P<body>(?:Our|We|This) .*?)(?=(?:[A-Z][A-Za-z0-9,;:'’\-()&/ ]+?(?:Could Harm Our Business|May Harm Our Business|May Adversely Affect Our Business|Could Adversely Affect Our Business))\s+(?:Our|We|This)|$)"
    )
    for match in pattern.finditer(normalized):
        heading = _normalize_text_line(match.group("heading"))
        body = _normalize_text_line(match.group("body"))
        if heading and body:
            candidate = (heading, body)
            if candidate not in sections:
                sections.append(candidate)
    return sections


def _risk_factor_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    if block.item != ITEM_1A_SECTION:
        return []
    refined: list[RefinedBlock] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in (entry.text for entry in block.lines):
        embedded_heading = _split_embedded_risk_heading(line)
        if embedded_heading:
            if current_heading and current_lines:
                refined.append(_make_block(block, ITEM_1A_SECTION, current_heading, "narrative", [current_heading, *current_lines]))
            current_heading, first_body_line = embedded_heading
            current_lines = [first_body_line]
            continue
        if _is_risk_heading(line):
            if current_heading and current_lines:
                refined.append(_make_block(block, ITEM_1A_SECTION, current_heading, "narrative", [current_heading, *current_lines]))
            current_heading = line
            current_lines = []
            continue
        if current_heading:
            current_lines.append(line)
    if current_heading and current_lines:
        refined.append(_make_block(block, ITEM_1A_SECTION, current_heading, "narrative", [current_heading, *current_lines]))
    if refined:
        return refined
    fallback = _default_item_refiner(block)
    if not fallback:
        return []
    full_text_sections = _extract_risk_sections_from_text(" ".join(line.text for line in block.lines))
    if full_text_sections:
        return [_make_block(block, ITEM_1A_SECTION, heading, "narrative", [heading, body]) for heading, body in full_text_sections]
    inferred: list[RefinedBlock] = []
    for candidate in fallback:
        content = " ".join(candidate.lines)
        embedded_heading = _split_embedded_risk_heading(content)
        if embedded_heading:
            heading, body = embedded_heading
            inferred.append(_make_block(block, ITEM_1A_SECTION, heading, "narrative", [heading, body]))
        else:
            inferred.append(candidate)
    return inferred


def _infer_unit(metric: str, default_unit: str | None) -> str | None:
    return TABLE_METRICS.get(metric, default_unit)


def _normalize_numeric_value(value_raw: str) -> float | None:
    cleaned = value_raw.replace(",", "").replace("$", "").strip().strip("()")
    if not cleaned or cleaned in {"-", "—"}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value_raw.strip().startswith("(") and value_raw.strip().endswith(")"):
        value *= -1
    return value


def _financial_table_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    joined_text = "\n".join(line.text for line in block.lines)
    normalized_text = _normalize_text_line(joined_text)
    if block.item != PRIMARY_TABLE_SECTION and not ITEM6_LABEL_RE.search(normalized_text):
        return []
    if not YEAR_RE.search(normalized_text):
        return []
    default_unit = "million USD" if TABLE_HEADER_RE.search(normalized_text) else None
    year_match = YEAR_HEADER_RE.search(normalized_text) or Y2019_TO_2015_RE.search(normalized_text)
    years = list(year_match.groups()) if year_match else ["2015", "2016", "2017", "2018", "2019"]
    refined: list[RefinedBlock] = []
    for match in ITEM6_ROW_RE.finditer(normalized_text):
        metric = METRIC_NORMALIZATION.get(re.sub(r"\s+", " ", match.group("metric")).strip(), re.sub(r"\s+", " ", match.group("metric")).strip())
        values = [match.group("v1"), match.group("v2"), match.group("v3"), match.group("v4"), match.group("v5")]
        for year, value_raw in zip(years, values, strict=False):
            refined.append(_make_block(block, PRIMARY_TABLE_SECTION, None, "table_row", [f"{metric} for {year}: {value_raw}"], table_name=PRIMARY_TABLE_SECTION, metric=metric, year=year, value_raw=value_raw, value_normalized=_normalize_numeric_value(value_raw), unit=_infer_unit(metric, default_unit)))
    if refined:
        refined.append(_make_block(block, PRIMARY_TABLE_SECTION, None, "table_block", [normalized_text], table_name=PRIMARY_TABLE_SECTION))
    return refined


def _is_mda_heading(line: str) -> bool:
    if line in MDA_HEADING_HINTS:
        return True
    words = line.split()
    if len(words) < 2 or len(words) > 12:
        return False
    capitalized = sum(1 for word in words if word[:1].isupper())
    return capitalized >= max(2, len(words) - 1) and not YEAR_RE.search(line)


def _mda_refiner(block: DocumentBlock) -> list[RefinedBlock]:
    if block.item != ITEM_7_SECTION:
        return []
    refined: list[RefinedBlock] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in (entry.text for entry in block.lines):
        if _is_mda_heading(line):
            if current_heading and current_lines:
                refined.append(_make_block(block, ITEM_7_SECTION, current_heading, "narrative", current_lines.copy()))
            current_heading = line
            current_lines = []
            continue
        current_lines.append(line)
    if current_heading and current_lines:
        refined.append(_make_block(block, ITEM_7_SECTION, current_heading, "narrative", current_lines.copy()))
    return refined or _default_item_refiner(block)


def _get_refiner(block: DocumentBlock):
    joined_text = " ".join(line.text for line in block.lines)
    if EXECUTIVE_OFFICERS_SECTION.casefold() in joined_text.casefold():
        return _executive_refiner
    if block.label == "Overview":
        return _overview_refiner
    if block.item == ITEM_1A_SECTION:
        return _risk_factor_refiner
    if block.item == PRIMARY_TABLE_SECTION:
        return _financial_table_refiner
    if block.item == ITEM_7_SECTION:
        return _mda_refiner
    return _default_item_refiner


def _refine_blocks(blocks: list[DocumentBlock]) -> list[RefinedBlock]:
    refined: list[RefinedBlock] = []
    for block in blocks:
        refined.extend(_get_refiner(block)(block))
    return [block for block in refined if block.lines]


def _split_text_to_chunks(lines: list[str]) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
    if current:
        chunks.append(current)
    return chunks


def _build_document_from_block(block: RefinedBlock, path: Path, updated_at: str, source_uri: str, company_name: str, filing_type: str | None, fiscal_year: str | None, content: str) -> ChunkDocument:
    if block.block_type == "table_row":
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "table_row", block.item or "", block.metric or "", block.year or "")
    elif block.block_type == "table_block":
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "table_block", block.item or "", block.table_name or "")
    elif block.block_type == "profile_row":
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "profile_row", block.section, block.entity_name or "")
    elif block.block_type == "profile_bio":
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "profile_bio", block.section, block.entity_name or "")
    elif block.block_type == "fact":
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "fact", block.section, block.subsection or "", content)
    else:
        chunk_id = _build_chunk_id(AMAZON_10K_DOC_ID, "narrative", block.section, block.subsection or "", str(block.page_start or ""), str(block.page_end or ""), content)
    return ChunkDocument(
        chunk_id=chunk_id,
        doc_id=AMAZON_10K_DOC_ID,
        title="Amazon.com, Inc. Form 10-K",
        section=block.section,
        content=content,
        source_path=path.name,
        source_uri=source_uri,
        updated_at=updated_at,
        index_version=INDEX_SCHEMA_VERSION,
        part=block.part,
        item=block.item,
        subsection=block.subsection,
        page_start=block.page_start,
        page_end=block.page_end,
        filing_type=filing_type,
        fiscal_year=fiscal_year,
        company_name=company_name,
        content_type=block.block_type,
        table_name=block.table_name,
        metric=block.metric,
        year=block.year,
        value_raw=block.value_raw,
        value_normalized=block.value_normalized,
        unit=block.unit,
        entity_name=block.entity_name,
        entity_role=block.entity_role,
    )


def _generate_chunks(refined_blocks: list[RefinedBlock], path: Path, updated_at: str, source_uri: str, company_name: str, filing_type: str | None, fiscal_year: str | None) -> list[ChunkDocument]:
    documents: list[ChunkDocument] = []
    for block in refined_blocks:
        if block.block_type in {"table_row", "table_block", "profile_row", "profile_bio", "fact"}:
            content = "\n".join(block.lines) if block.block_type not in {"table_row", "profile_row", "profile_bio"} else block.lines[0]
            documents.append(_build_document_from_block(block, path, updated_at, source_uri, company_name, filing_type, fiscal_year, content))
            continue
        for chunk in _split_text_to_chunks(block.lines):
            documents.append(_build_document_from_block(block, path, updated_at, source_uri, company_name, filing_type, fiscal_year, chunk))
    return documents


def _deduplicate_documents(documents: list[ChunkDocument]) -> list[ChunkDocument]:
    unique: dict[str, ChunkDocument] = {}
    for document in documents:
        unique[document.chunk_id] = document
    return list(unique.values())


def _verify_no_overview_index_noise(documents: list[ChunkDocument]) -> None:
    for document in documents:
        if document.section == "Overview" and _is_index_noise(document.content):
            raise RuntimeError("TOC/INDEX noise leaked into the indexed 10-K corpus.")


def _validate_documents(documents: list[ChunkDocument]) -> None:
    ids = [document.chunk_id for document in documents]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate chunk_id values detected in build_documents output.")
    item6_blocks = [doc for doc in documents if doc.section == PRIMARY_TABLE_SECTION and doc.content_type == "table_block"]
    if len(item6_blocks) > 1:
        raise RuntimeError("Item 6 emitted duplicate table_block chunks.")
    item6_rows = [(doc.metric, doc.year) for doc in documents if doc.section == PRIMARY_TABLE_SECTION and doc.content_type == "table_row"]
    if len(item6_rows) != len(set(item6_rows)):
        raise RuntimeError("Item 6 emitted duplicate metric/year rows.")
    profile_rows = [doc.entity_name for doc in documents if doc.content_type == "profile_row"]
    if len(profile_rows) != len(set(profile_rows)):
        raise RuntimeError("Duplicate executive profile rows detected.")
    profile_bios = [doc.entity_name for doc in documents if doc.content_type == "profile_bio"]
    if len(profile_bios) != len(set(profile_bios)):
        raise RuntimeError("Duplicate executive profile bios detected.")
    _verify_no_overview_index_noise(documents)


def _build_pdf_documents(path: Path, updated_at: str) -> list[ChunkDocument]:
    if not path.exists():
        return []
    source_uri = _s3_source_uri(path)
    pages = _remove_toc_pages(_extract_pdf_pages(path))
    company_name, filing_type, fiscal_year = _extract_pdf_metadata(pages)
    skeleton = _build_document_skeleton(_normalize_pdf_lines(pages))
    refined = _refine_blocks(skeleton)
    documents = _generate_chunks(refined, path, updated_at, source_uri, company_name, filing_type, fiscal_year)
    return _deduplicate_documents(documents)


def build_documents() -> list[ChunkDocument]:
    updated_at = datetime.now(UTC).isoformat()
    documents = _build_pdf_documents(COMPANY_PDF_PATH, updated_at)
    _validate_documents(documents)
    return documents


def _doc_id_exists(client: object, index_name: str, doc_id: str) -> bool:
    try:
        response = client.search(index=index_name, body={"size": 0, "query": {"term": {"doc_id.keyword": doc_id}}})
    except NotFoundError:
        return False
    total = response.get("hits", {}).get("total", {})
    return int(total.get("value", 0) if isinstance(total, dict) else total or 0) > 0


def _ensure_index(client: object, index_name: str) -> None:
    if _mapping_supports_doc_id_keyword(client, index_name):
        return
    try:
        client.indices.delete(index=index_name)
    except NotFoundError:
        pass
    try:
        client.indices.create(index=index_name, body={"settings": INDEX_SETTINGS, "mappings": INDEX_MAPPINGS})
    except RequestError as exc:
        if exc.error == "resource_already_exists_exception":
            return
        if exc.info and isinstance(exc.info, dict):
            error = exc.info.get("error")
            if isinstance(error, dict) and error.get("type") == "resource_already_exists_exception":
                return
        raise
    except NotFoundError:
        return


def _delete_existing_doc_chunks(client: object, index_name: str, doc_id: str) -> None:
    query = {"query": {"term": {"doc_id.keyword": doc_id}}}
    try:
        client.delete_by_query(index=index_name, body=query, conflicts="proceed")
    except NotFoundError:
        pass


def _clear_doc_id(client: object, index_name: str, doc_id: str) -> None:
    for _ in range(20):
        _delete_existing_doc_chunks(client, index_name, doc_id)
        try:
            client.indices.refresh(index=index_name)
        except NotFoundError:
            pass
        if not _doc_id_exists(client, index_name, doc_id):
            return


def _count_documents_by_doc_id(client: object, index_name: str, doc_id: str) -> int:
    try:
        response = client.search(index=index_name, body={"size": 0, "query": {"term": {"doc_id.keyword": doc_id}}})
    except NotFoundError:
        return 0
    total = response.get("hits", {}).get("total", {})
    return int(total.get("value", 0) if isinstance(total, dict) else total or 0)


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


def _verify_doc_id_cleanup(client: object, index_name: str) -> None:
    for attempt in range(1, 6):
        legacy_remaining = {doc_id: _count_documents_by_doc_id(client, index_name, doc_id) for doc_id in LEGACY_MARKDOWN_DOC_IDS}
        if any(legacy_remaining.values()):
            if attempt == 5:
                return
            time.sleep(attempt)
            continue
        if _count_documents_by_doc_id(client, index_name, AMAZON_10K_DOC_ID) > 0:
            return
        if attempt == 5:
            raise RuntimeError("10-K corpus was not present after indexing.")
        time.sleep(attempt)


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
    _ensure_index(client, index_name)
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
