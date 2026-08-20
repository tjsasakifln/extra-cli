"""Split private envelope vs redacted public fixture. No real PII in public copy."""

from __future__ import annotations

import re
from typing import Any

from scripts.bid_readiness_public.hashing import attach_hash
from scripts.bid_readiness_public.models import SCHEMA_VERSION

REDACTED_CNPJ = "[REDACTED_CNPJ]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_NAME = "[REDACTED_NAME]"

CNPJ_FORMATTED = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CNPJ_DIGITS = re.compile(r"\b\d{14}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)(?:9?\d{4}[-\s]?\d{4})\b")
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


def redact_text(text: str) -> str:
    pieces: list[str] = []
    last = 0
    blob = str(text)
    for match in SHA256_RE.finditer(blob):
        chunk = blob[last : match.start()]
        chunk = CNPJ_FORMATTED.sub(REDACTED_CNPJ, chunk)
        chunk = EMAIL_RE.sub(REDACTED_EMAIL, chunk)
        chunk = PHONE_RE.sub(REDACTED_PHONE, chunk)
        chunk = CNPJ_DIGITS.sub(REDACTED_CNPJ, chunk)
        pieces.append(chunk)
        pieces.append(match.group(0))
        last = match.end()
    tail = blob[last:]
    tail = CNPJ_FORMATTED.sub(REDACTED_CNPJ, tail)
    tail = EMAIL_RE.sub(REDACTED_EMAIL, tail)
    tail = PHONE_RE.sub(REDACTED_PHONE, tail)
    tail = CNPJ_DIGITS.sub(REDACTED_CNPJ, tail)
    pieces.append(tail)
    return "".join(pieces)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value


def public_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy a private envelope with PII redacted, then re-hash the public body."""
    copied = redact_value(payload)
    if not isinstance(copied, dict):
        raise TypeError("envelope must be an object")
    copied["source_access"] = "redacted_fixture"
    copied["publication_authorization"] = False
    copied["index_authorization"] = False
    copied["human_review_required"] = True
    copied["not_legal_conclusion"] = True
    copied["schema_version"] = payload.get("schema_version") or SCHEMA_VERSION
    copied.pop("content_hash", None)
    return attach_hash(copied)
