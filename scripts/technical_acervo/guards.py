"""Guardrails: PII, overclaim, CAO misuse."""

from __future__ import annotations

import re
from typing import Any

# CPF pattern (###.###.###-## or 11 digits) — must not appear in acervo blobs.
CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
# Real birth-date assignments only (not meta-notes about omission).
BIRTH_RE = re.compile(
    r"(?:data\s+de\s+nascimento|birth[_\s-]?date)\s*[:=]\s*\d{2}[/-]\d{2}[/-]\d{4}"
    r"|\bnascido\s+em\s+\d{2}[/-]\d{2}[/-]\d{4}",
    re.I,
)

FORBIDDEN_OVERCLAIM = (
    re.compile(r"\bhabilitad[oa]\s+juridicamente\b", re.I),
    re.compile(r"\batende\s+integralmente\s+ao\s+edital\b", re.I),
    re.compile(r"\bprova\s+irrestrita\s+de\s+capacidade\s+operacional\b", re.I),
)


def scan_text_for_pii(text: str) -> list[str]:
    issues: list[str] = []
    # Avoid flagging CREA/ART/CAT long numbers: CPF is specifically 11 digits with optional mask
    for m in CPF_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 11:
            # Skip if looks like part of certificate (CAT numbers are longer or different)
            issues.append(f"possible_cpf:{m.group(0)}")
    if BIRTH_RE.search(text or ""):
        issues.append("possible_birth_date")
    return issues


def scan_store_for_pii(store: Any) -> dict[str, Any]:
    """Scan professionals and chunks for forbidden personal data."""
    issues: list[str] = []
    for prof in store.professionals:
        # Allowed: name, title, crea, rnp. Forbidden keys:
        for key in ("cpf", "birth_date", "data_nascimento", "documento_pessoal"):
            if prof.get(key):
                issues.append(f"professional_field:{key}")
        blob = " ".join(str(v) for k, v in prof.items() if k not in ("id", "linked_document_ids"))
        issues.extend(scan_text_for_pii(blob))
    # Chunks
    from scripts.technical_acervo.search import build_search_chunks

    for ch in build_search_chunks(store):
        issues.extend(scan_text_for_pii(ch.get("text") or ""))
    return {"ok": not issues, "issues": issues}


def assert_response_has_provenance(item: dict[str, Any]) -> list[str]:
    """Every acervo answer should carry document/number/art/qty/unit/source/page."""
    missing: list[str] = []
    # accept alternate keys
    doc = item.get("document") or item.get("document_type")
    num = item.get("number") or item.get("certificate_number")
    art = item.get("art") or item.get("art_number")
    qty = item.get("quantity")
    unit = item.get("unit")
    src = item.get("source") or item.get("source_file")
    page = item.get("page") if item.get("page") is not None else item.get("source_page")
    if not doc:
        missing.append("document")
    if not num:
        missing.append("number")
    # ART may be null only for pure CAO header answers without art context — still prefer present
    if art is None and (doc or "").upper() != "CAO":
        missing.append("art")
    if qty is None and item.get("service"):
        missing.append("quantity")
    if unit is None and item.get("service"):
        missing.append("unit")
    if not src:
        missing.append("source")
    if page is None:
        missing.append("page")
    return missing


def cao_guard_notes(doc: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if (doc.get("document_type") or "").upper() != "CAO":
        return notes
    if doc.get("current_status") == "expired":
        notes.append(
            f"CAO vencida desde {doc.get('valid_until')} — não apresentar como prova atual de habilitação."
        )
    for r in doc.get("restrictions") or []:
        notes.append(r)
    for flag in doc.get("review_flags") or []:
        if isinstance(flag, dict) and flag.get("flag") == "source_filename_date_conflicts_with_document_content":
            notes.append(flag.get("reason") or flag["flag"])
    return notes
