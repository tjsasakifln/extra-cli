"""Split private envelope vs redacted public fixture. No real PII in public copy."""

from __future__ import annotations

import re
from typing import Any

from scripts.bid_readiness_public.hashing import attach_hash
from scripts.bid_readiness_public.models import SCHEMA_VERSION
from scripts.bid_readiness_public.pii import scan_payload_for_pii
from scripts.bid_readiness_public.validators import EnvelopeValidationError, refuse_envelope

REDACTED_CNPJ = "[REDACTED_CNPJ]"
REDACTED_CPF = "[REDACTED_CPF]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_SIGNATURE = "[REDACTED_SIGNATURE]"

CNPJ_FORMATTED = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CNPJ_DIGITS = re.compile(r"\b\d{14}\b")
CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)(?:9?\d{4}[-\s]?\d{4})\b")
SIGNATURE_HINT = re.compile(r"\b(assinatura\s+digital|certificado\s+icp-brasil)\b", re.IGNORECASE)
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")


def _redact_chunk(chunk: str) -> str:
    chunk = CNPJ_FORMATTED.sub(REDACTED_CNPJ, chunk)
    chunk = CNPJ_DIGITS.sub(REDACTED_CNPJ, chunk)
    chunk = CPF_RE.sub(REDACTED_CPF, chunk)
    chunk = EMAIL_RE.sub(REDACTED_EMAIL, chunk)
    chunk = PHONE_RE.sub(REDACTED_PHONE, chunk)
    return SIGNATURE_HINT.sub(REDACTED_SIGNATURE, chunk)


def redact_text(text: str) -> str:
    pieces: list[str] = []
    last = 0
    blob = str(text)
    for match in SHA256_RE.finditer(blob):
        pieces.append(_redact_chunk(blob[last : match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(_redact_chunk(blob[last:]))
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
    """Re-redact an explicitly redacted fixture and verify it before export."""
    refuse_envelope(payload)
    if payload.get("source_access") != "redacted_fixture":
        raise EnvelopeValidationError("public_export_requires_redacted_fixture")
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
    public = attach_hash(copied)
    pii_hits = scan_payload_for_pii(public)
    if pii_hits:
        raise EnvelopeValidationError("public_fixture_contains_pii:" + ";".join(sorted(set(pii_hits))))
    refuse_envelope(public)
    return public
