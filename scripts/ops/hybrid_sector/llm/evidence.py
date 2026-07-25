"""Evidence validation — invented evidence invalidates decision → REVIEW."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    t = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Structured refs require an explicit locator (id/page), not free prose.
# Examples OK: "TR:12 | pavimentação", "edital #2024-01 — drenagem", "p.3: obra civil"
# "documento secreto inventado" is NOT a structured ref.
_STRUCTURED_REF = re.compile(
    r"^(?:"
    r"doc(?:umento)?|edital|tr|etp|anexo|pagina|página|p"
    r")\b\s*[:#.]?\s*"
    r"(?P<loc>\d+|[A-Za-z0-9._-]{2,})"
    r"(?:\s*[|—:-]\s*(?P<quote>.+))?$",
    re.I,
)


def evidence_is_valid(evidence: str, source_text: str, *, max_len: int = 240) -> bool:
    """True if evidence is literal substring of source or structured doc reference."""
    if not evidence or not str(evidence).strip():
        return False
    ev = str(evidence).strip()
    if len(ev) > max_len:
        return False
    m = _STRUCTURED_REF.match(ev)
    if m:
        quote = (m.group("quote") or "").strip()
        loc = (m.group("loc") or "").strip()
        # Locator must look like an id/page, not a Portuguese prose word alone
        if re.fullmatch(r"[A-Za-zÀ-ÿ]{6,}", loc):
            # long alphabetic token without digits — treat as prose, not locator
            return _norm(ev) in _norm(source_text)
        if quote:
            return _norm(quote) in _norm(source_text)
        # bare "TR:12" / "p.3" style
        return len(ev) < 40 and len(ev.split()) <= 3
    return _norm(ev) in _norm(source_text)


def validate_evidence_list(
    evidence: Iterable[str],
    source_text: str,
    *,
    max_len: int = 240,
) -> tuple[list[str], list[str]]:
    """Return (valid, invented)."""
    valid: list[str] = []
    invented: list[str] = []
    for e in evidence or []:
        if evidence_is_valid(str(e), source_text, max_len=max_len):
            valid.append(str(e))
        else:
            invented.append(str(e))
    return valid, invented
