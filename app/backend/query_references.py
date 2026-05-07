from __future__ import annotations

import re
from dataclasses import dataclass

QUERY_REFERENCE_WRAPPER_PATTERNS = (
    re.compile(
        r"^(?:can you tell me more about|tell me more about|please explain|explain|describe|summarize)\s*:?\s*(?P<reference>.+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:what can you tell me about|what does)\s+(?P<reference>.+)$", re.IGNORECASE),
)
OUTER_QUOTE_PAIRS = (
    ('"', '"'),
    ("'", "'"),
    ("“", "”"),
    ("‘", "’"),
    ("(", ")"),
    ("[", "]"),
)


@dataclass(frozen=True)
class SectionOverviewRule:
    item: str
    aliases: tuple[str, ...]


SECTION_OVERVIEW_RULES = (
    SectionOverviewRule(
        item="Item 1A. Risk Factors",
        aliases=(
            "risk factor",
            "risk factors",
            "item 1a",
            "item 1a risk factor",
            "item 1a risk factors",
            "risk factor in item 1a",
            "risk factors in item 1a",
            "risk factor described in item 1a",
            "risk factors described in item 1a",
        ),
    ),
    SectionOverviewRule(
        item="Item 1. Business",
        aliases=(
            "business",
            "item 1",
            "item 1 business",
        ),
    ),
    SectionOverviewRule(
        item="Item 2. Properties",
        aliases=(
            "properties",
            "item 2",
            "item 2 properties",
        ),
    ),
    SectionOverviewRule(
        item="Item 3. Legal Proceedings",
        aliases=(
            "legal proceedings",
            "item 3",
            "item 3 legal proceedings",
        ),
    ),
    SectionOverviewRule(
        item="Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
        aliases=(
            "item 5",
            "item 5 market for the registrant's common stock",
            "item 5 market for the registrant’s common stock",
            "item 5 market for the registrant's common stock, related shareholder matters, and issuer purchases of equity securities",
            "item 5 market for the registrant’s common stock, related shareholder matters, and issuer purchases of equity securities",
            "market for the registrant's common stock",
            "market for the registrant’s common stock",
            "market for the registrant's common stock, related shareholder matters, and issuer purchases of equity securities",
            "market for the registrant’s common stock, related shareholder matters, and issuer purchases of equity securities",
            "related shareholder matters",
            "issuer purchases of equity securities",
            "shareholder matters",
        ),
    ),
    SectionOverviewRule(
        item="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        aliases=(
            "item 7a",
            "item 7a market risk",
            "market risk",
            "quantitative and qualitative disclosures about market risk",
        ),
    ),
    SectionOverviewRule(
        item="Item 8. Financial Statements and Supplementary Data",
        aliases=(
            "item 8",
            "item 8 financial statements",
            "financial statements and supplementary data",
        ),
    ),
)
SECTION_OVERVIEW_RULE_KEYS = {
    rule.item: {" ".join(re.findall(r"[a-z0-9]+", alias.casefold())) for alias in rule.aliases}
    for rule in SECTION_OVERVIEW_RULES
}


def normalize_reference_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_outer_reference_punctuation(text: str) -> str:
    candidate = normalize_reference_text(text)
    if not candidate:
        return ""

    while True:
        updated = re.sub(r"^[\s:;,\-]+", "", candidate)
        updated = re.sub(r"[\s:;,\-?.!]+$", "", updated)
        updated = normalize_reference_text(updated)

        for left, right in OUTER_QUOTE_PAIRS:
            if len(updated) >= 2 and updated.startswith(left) and updated.endswith(right):
                updated = normalize_reference_text(updated[1:-1])
                break

        if updated == candidate:
            return updated
        candidate = updated


def extract_query_reference(question: str) -> str | None:
    candidate = _strip_outer_reference_punctuation(question)
    if not candidate:
        return None

    while True:
        matched = False
        for pattern in QUERY_REFERENCE_WRAPPER_PATTERNS:
            match = pattern.match(candidate)
            if not match:
                continue
            candidate = _strip_outer_reference_punctuation(match.group("reference"))
            matched = True
            break
        if not matched:
            break
    return candidate or None


def normalize_reference_key(text: str) -> str:
    normalized = extract_query_reference(text) or text
    return " ".join(re.findall(r"[a-z0-9]+", normalized.casefold()))


def resolve_section_overview_rule(question: str) -> SectionOverviewRule | None:
    normalized_reference = normalize_reference_key(question)
    if not normalized_reference:
        return None
    for rule in SECTION_OVERVIEW_RULES:
        if normalized_reference in SECTION_OVERVIEW_RULE_KEYS[rule.item]:
            return rule
    return None


def resolve_section_overview_item(question: str) -> str | None:
    rule = resolve_section_overview_rule(question)
    return rule.item if rule is not None else None
