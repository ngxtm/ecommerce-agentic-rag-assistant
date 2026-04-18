from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


SSN_LAST4_PATTERN = re.compile(r"\b\d{4}\b")
DATE_PATTERNS = (
    re.compile(r"\b\d{2}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
)


def redact_pii(text: str) -> str:
    redacted = text
    for pattern in DATE_PATTERNS:
        redacted = pattern.sub("[REDACTED_DATE]", redacted)
    redacted = SSN_LAST4_PATTERN.sub("[REDACTED_4_DIGITS]", redacted)
    return redacted


def contains_possible_pii(text: str) -> bool:
    if any(pattern.search(text) for pattern in DATE_PATTERNS):
        return True
    return SSN_LAST4_PATTERN.search(text) is not None


def build_log_event(event_type: str, **fields: Any) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
    }
    for key, value in fields.items():
        if value is not None:
            event[key] = value
    return event
