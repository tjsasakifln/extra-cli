"""PII / CNPJ scanners for public fixtures. Fictional placeholders are allowed."""

from __future__ import annotations

import re
from typing import Any

from scripts.bid_readiness_public.forbidden import walk_strings

# Documented fictional placeholders used in committed public fixtures only.
FICTIONAL_CNPJ_DIGITS = frozenset(
    {
        "00000000000000",
        "12345678000199",
    }
)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)(?:9?\d{4}[-\s]?\d{4})\b")
CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
CNPJ_FORMATTED = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CNPJ_DIGITS = re.compile(r"\b\d{14}\b")
SIGNATURE_HINT = re.compile(r"\b(assinatura\s+digital|certificado\s+icp-brasil)\b", re.IGNORECASE)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


_SHA256_HEX = re.compile(r"\b[a-fA-F0-9]{64}\b")


def scan_text_for_pii(text: str) -> list[str]:
    hits: list[str] = []
    blob = text or ""
    stripped = _SHA256_HEX.sub("", blob)
    for match in EMAIL_RE.finditer(stripped):
        hits.append(f"email:{match.group(0)}")
    for match in PHONE_RE.finditer(stripped):
        hits.append(f"phone:{match.group(0)}")
    for match in CPF_RE.finditer(stripped):
        digits = _digits(match.group(0))
        if len(digits) == 11:
            hits.append(f"cpf:{match.group(0)}")
    for match in CNPJ_FORMATTED.finditer(stripped):
        digits = _digits(match.group(0))
        if digits not in FICTIONAL_CNPJ_DIGITS:
            hits.append(f"cnpj:{match.group(0)}")
    for match in CNPJ_DIGITS.finditer(stripped):
        digits = match.group(0)
        if digits not in FICTIONAL_CNPJ_DIGITS:
            hits.append(f"cnpj_digits:{digits}")
    if SIGNATURE_HINT.search(stripped):
        hits.append("signature_hint")
    return hits


def scan_payload_for_pii(payload: Any) -> list[str]:
    hits: list[str] = []
    for text in walk_strings(payload):
        hits.extend(scan_text_for_pii(text))
    return hits
