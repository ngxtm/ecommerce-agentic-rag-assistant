from __future__ import annotations

import re

RISK_HEADING_ENDINGS = (
    "Could Harm Our Business",
    "May Harm Our Business",
    "May Adversely Affect Our Business",
    "Could Adversely Affect Our Business",
    "Could Negatively Affect Our Business",
)
RISK_HEADING_PREFIXES = (
    "risks related to ",
    "we are subject to ",
    "we face risks related to ",
    "our ",
)
QUESTION_PREFIX_PATTERNS = (
    re.compile(r"^(?:can you tell me more about|tell me more about|please explain|explain|describe|summarize)\s+(?P<heading>.+)$", re.IGNORECASE),
    re.compile(r"^(?:what does|what can you tell me about)\s+(?P<heading>.+)$", re.IGNORECASE),
)
CONVERSATIONAL_PREFIXES = (
    "can you tell me more about ",
    "tell me more about ",
    "please explain ",
    "explain ",
    "describe ",
    "summarize ",
    "what does ",
    "what can you tell me about ",
)
RISK_HEADING_GENERIC_PREFIX = "we face "
RISK_HEADING_WORD_FRAGMENT = r"[A-Za-z0-9,;:'’\-()&/ ]"
RISK_HEADING_BODY_START_FRAGMENT = (
    r"(?:"
    r"Our\s+[a-z][A-Za-z0-9'’\-]*"
    r"|We\s+[a-z][A-Za-z0-9'’\-]*"
    r"|This\s+[a-z][A-Za-z0-9'’\-]*"
    r"|If\s+[a-z][A-Za-z0-9'’\-]*"
    r")"
)
RISK_HEADING_FRAGMENT = (
    r"(?:"
    r"[A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+?(?:Could Harm Our Business|May Harm Our Business|May Adversely Affect Our Business|Could Adversely Affect Our Business|Could Negatively Affect Our Business)"
    r"|Risks Related to [A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+?"
    r"|We Are Subject to [A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+?"
    r"|We Face Risks Related to [A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+?"
    r"|We Face [A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+?"
    r"|Our [A-Z]" + RISK_HEADING_WORD_FRAGMENT + r"+? Risks?"
    r")"
)
RISK_HEADING_EMBEDDED_RE = re.compile(
    rf"^(?P<heading>{RISK_HEADING_FRAGMENT})\s+(?P<body>{RISK_HEADING_BODY_START_FRAGMENT}.*)$"
)
RISK_HEADING_SECTION_RE = re.compile(
    rf"(?P<heading>{RISK_HEADING_FRAGMENT})\s+"
    rf"(?P<body>{RISK_HEADING_BODY_START_FRAGMENT}.*?)"
    rf"(?=(?:{RISK_HEADING_FRAGMENT})\s+{RISK_HEADING_BODY_START_FRAGMENT}|$)"
)
YEAR_RE = re.compile(r"\b(2015|2016|2017|2018|2019)\b")
LOWERCASE_CONNECTORS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "with",
}


def normalize_text_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _title_case_ratio(text: str) -> tuple[int, int]:
    words = [word.strip(".,;:()[]{}\"'") for word in text.split()]
    significant = [word for word in words if word and word.casefold() not in LOWERCASE_CONNECTORS]
    capitalized = sum(1 for word in significant if word[:1].isupper())
    return capitalized, len(significant)


def looks_like_risk_heading(text: str) -> bool:
    normalized = normalize_text_line(text)
    if not normalized:
        return False
    words = normalized.split()
    if len(words) < 3 or len(words) > 30:
        return False
    if YEAR_RE.search(normalized):
        return False
    if normalized.endswith("."):
        return False

    lowered = normalized.casefold()
    if any(lowered.startswith(prefix) for prefix in CONVERSATIONAL_PREFIXES):
        return False
    if lowered.startswith("risks related to "):
        return True
    if lowered.startswith("we are subject to ") and len(words) >= 5:
        return True
    if lowered.startswith("we face risks related to ") and len(words) >= 5:
        return True
    if lowered.startswith("our ") and " risk" in lowered and len(words) <= 16:
        capitalized, significant = _title_case_ratio(normalized)
        return significant >= 3 and capitalized >= max(3, significant - 1)
    if lowered.startswith(RISK_HEADING_GENERIC_PREFIX) and len(words) <= 12:
        capitalized, significant = _title_case_ratio(normalized)
        return significant >= 3 and capitalized >= max(3, significant - 1)

    lowercase_words = sum(1 for word in words if word.islower())
    return lowercase_words >= 2 and not normalized.startswith("We ")


def split_embedded_risk_heading(text: str) -> tuple[str, str] | None:
    normalized = normalize_text_line(text)
    if not normalized or len(normalized.split()) < 8:
        return None
    match = RISK_HEADING_EMBEDDED_RE.match(normalized)
    if not match:
        return None
    heading = normalize_text_line(match.group("heading"))
    body = normalize_text_line(match.group("body"))
    if looks_like_risk_heading(heading) and body:
        return heading, body
    return None


def extract_risk_sections_from_text(text: str) -> list[tuple[str, str]]:
    normalized = normalize_text_line(re.sub(r"(?<=[a-z\)])(?=[A-Z])", " ", text))
    if not normalized:
        return []
    sections: list[tuple[str, str]] = []
    for match in RISK_HEADING_SECTION_RE.finditer(normalized):
        heading = normalize_text_line(match.group("heading"))
        body = normalize_text_line(match.group("body"))
        if heading and body:
            candidate = (heading, body)
            if candidate not in sections:
                sections.append(candidate)
    return sections


def question_references_risk_heading(question: str) -> bool:
    lowered = normalize_text_line(question).casefold()
    if not lowered:
        return False
    if any(lowered.startswith(prefix) for prefix in RISK_HEADING_PREFIXES):
        return True
    if "subject us to" in lowered and " risk" in lowered:
        return True
    if re.search(r"\bwe face [a-z]", lowered):
        return True
    if re.search(r"\bwe are subject to [a-z]", lowered):
        return True
    return any(ending.casefold() in lowered for ending in RISK_HEADING_ENDINGS)

def extract_risk_heading_reference(question: str) -> str | None:
    normalized = normalize_text_line(question).strip("?.! ")
    if not normalized:
        return None
    for pattern in QUESTION_PREFIX_PATTERNS:
        match = pattern.match(normalized)
        if not match:
            continue
        candidate = normalize_text_line(match.group("heading")).strip("?.! ")
        if looks_like_risk_heading(candidate):
            return candidate
    if looks_like_risk_heading(normalized):
        return normalized
    return None
