"""Sanitization of PII and sensitive tokens for versionable reports/logs."""

from __future__ import annotations

import re
from typing import Any

# CPF: 000.000.000-00 or 11 digits in isolation contexts
_CPF_DOTTED = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CPF_RAW = re.compile(r"(?<!\d)\d{11}(?!\d)")
_RG = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b")
_PHONE = re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?\d{4,5}[-\s]?\d{4}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_BANK = re.compile(r"\b(?:ag[eê]ncia|conta|banco)\s*[:#]?\s*\d[\d\-\s/]{3,}\b", re.I)
_PASSWORD = re.compile(r"(?i)(senha|password|token|api[_-]?key)\s*[:=]\s*\S+")
# Only flag substantive signature payloads — not status enums like PRESENT/ABSENT
_SIGNATURE_MARK = re.compile(
    r"(?i)(assinatura\s*(digital|eletr[oô]nica)?\s*[:=]\s*(?!present\b|absent\b|sim\b|n[aã]o\b|yes\b|no\b|signature_present\b|signature_not_found\b)\S.+|signature\s*[:=]\s*(?!present\b|absent\b)\S.+)"
)


def mask_cpf(text: str) -> str:
    text = _CPF_DOTTED.sub("***.***.***-**", text)
    # Only mask 11-digit sequences that look like CPF in labeled contexts
    text = re.sub(
        r"(?i)(cpf\s*[:#]?\s*)\d{11}",
        r"\1***********",
        text,
    )
    return text


def sanitize_text(text: str | None) -> str:
    if text is None:
        return ""
    s = str(text)
    s = mask_cpf(s)
    s = _RG.sub("[RG-REDACTED]", s)
    s = _EMAIL.sub("[EMAIL-REDACTED]", s)
    s = _PHONE.sub("[PHONE-REDACTED]", s)
    s = _BANK.sub("[BANK-REDACTED]", s)
    s = _PASSWORD.sub(r"\1=[REDACTED]", s)
    s = _SIGNATURE_MARK.sub("[SIGNATURE-REDACTED]", s)
    return s


def sanitize_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in {
                "cpf",
                "rg",
                "assinatura",
                "signature",
                "password",
                "token",
                "senha",
                "personal_email",
                "home_address",
                "conta_bancaria",
            }:
                out[k] = "[REDACTED]"
            else:
                out[k] = sanitize_obj(v)
        return out
    if isinstance(obj, list):
        return [sanitize_obj(x) for x in obj]
    return obj


def contains_critical_pii(text: str) -> list[str]:
    """Return list of PII pattern names found (for privacy gate)."""
    hits: list[str] = []
    if _CPF_DOTTED.search(text) or re.search(r"(?i)cpf\s*[:#]?\s*\d{11}", text):
        hits.append("cpf")
    if _SIGNATURE_MARK.search(text):
        hits.append("signature")
    if re.search(r"(?i)(senha|password|token)\s*[:=]\s*\S+", text):
        hits.append("secret")
    return hits
