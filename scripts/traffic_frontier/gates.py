"""Hard gates for the traffic-opportunity frontier.

Score cannot promote a failing item to READY. Coverage failures HOLD;
claim / doorway / clone / generic failures REJECT.
"""

from __future__ import annotations

import re
from typing import Any

STATES = ("READY", "HOLD_FOR_DATA", "REJECT")

_UF_RE = re.compile(
    r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b",
    re.IGNORECASE,
)
_CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_NATIONAL_SCOPE = frozenset({"BR", "BRASIL", "NACIONAL", "NATIONAL"})
_THIN_COVERAGE = frozenset(
    {
        "pending",
        "partial",
        "error",
        "blocked",
        "never_checked",
        "unknown",
        "success_zero",
    }
)


def intellectual_fingerprint(text: str) -> str:
    """Normalize a question so UF/CNPJ swaps collapse to the same idea."""
    lowered = (text or "").strip().lower()
    lowered = _CNPJ_RE.sub("<cnpj>", lowered)
    lowered = _UF_RE.sub("<uf>", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def is_national_scope(geographic_scope: Any) -> bool:
    if geographic_scope is None:
        return False
    if isinstance(geographic_scope, str):
        return geographic_scope.strip().upper() in _NATIONAL_SCOPE
    if isinstance(geographic_scope, dict):
        kind = str(geographic_scope.get("kind") or "").upper()
        label = str(geographic_scope.get("label") or "").upper()
        codes = [str(code).upper() for code in (geographic_scope.get("codes") or [])]
        if kind in _NATIONAL_SCOPE or label in _NATIONAL_SCOPE:
            return True
        return any(code in _NATIONAL_SCOPE for code in codes)
    return False


def evaluate_hard_gates(record: dict[str, Any]) -> dict[str, Any]:
    """Pure gate over a frozen candidate/opportunity record."""
    reject: list[str] = []
    hold: list[str] = []

    question = str(record.get("question") or "").strip()
    if len(question) < 24 or not question.endswith("?"):
        reject.append("unclear_question")
    if record.get("generic_no_edge"):
        reject.append("generic_no_edge")

    if not record.get("independent_utility"):
        reject.append("no_independent_utility")
    if not record.get("method_reproducible"):
        reject.append("unreproducible_method")
    if record.get("is_doorway"):
        reject.append("doorway")

    if record.get("is_duplicate") or record.get("duplicate_of"):
        reject.append("duplicate_asset")
    if record.get("merge_into"):
        reject.append("duplicate_asset")

    if record.get("is_geo_clone") or record.get("clone_of"):
        reject.append("uf_cnpj_clone")

    if record.get("unsupported_legal_claim") or record.get("unsupported_economic_claim"):
        reject.append("unsupported_claim")

    nacional_completo = bool(record.get("nacional_completo"))
    # Lying that a recorte (UF / Extra 1093 / 4-UF) *is* Brasil → REJECT.
    # An honest BR question with incomplete denominator → HOLD (never READY).
    if record.get("nacionaliza_recorte"):
        reject.append("nacionalizacao_recorte")
    if is_national_scope(record.get("geographic_scope")) and not nacional_completo:
        hold.append("national_denominator_incomplete")
    if record.get("claims_national") and not nacional_completo and not record.get("nacionaliza_recorte"):
        hold.append("national_denominator_incomplete")

    coverage_state = str(record.get("coverage_state") or record.get("coverage", {}).get("state") or "")
    stale = bool(record.get("freshness_stale") or (record.get("coverage") or {}).get("stale"))
    complete = record.get("coverage_complete")
    if complete is None:
        complete = (record.get("coverage") or {}).get("complete_for_scope")
    record_count = int(record.get("record_count") or (record.get("coverage") or {}).get("record_count") or 0)
    coverage_kind = str(record.get("coverage_kind") or (record.get("coverage") or {}).get("kind") or "")
    method_coverage = coverage_kind == "method"

    if stale:
        hold.append("coverage_stale")
    if coverage_state in _THIN_COVERAGE:
        hold.append("coverage_incomplete")
    if complete is False:
        hold.append("coverage_incomplete")
    if not method_coverage and coverage_state == "success_with_data" and record_count < 8:
        hold.append("coverage_incomplete")
    if coverage_state == "stale":
        hold.append("coverage_stale")

    cta = str(record.get("suggested_cta") or record.get("cta") or "").strip()
    cta_connected = record.get("cta_connected")
    if cta_connected is None:
        cta_connected = bool(cta) and bool(record.get("offer_bridge"))
    if not cta or not cta_connected:
        reject.append("disconnected_cta")

    # Dedup reject codes, preserve order
    seen: set[str] = set()
    reject_codes = []
    for code in reject:
        if code not in seen:
            seen.add(code)
            reject_codes.append(code)
    hold_codes = []
    for code in hold:
        if code not in seen and code not in hold_codes:
            hold_codes.append(code)

    if reject_codes:
        state = "REJECT"
        reason_codes = reject_codes
    elif hold_codes:
        state = "HOLD_FOR_DATA"
        reason_codes = hold_codes
    else:
        state = "READY"
        reason_codes = []

    return {
        "state": state,
        "reason_codes": reason_codes,
        "reject_codes": reject_codes,
        "hold_codes": hold_codes,
        "merge_into": record.get("merge_into") or record.get("duplicate_of"),
        "fingerprint": intellectual_fingerprint(question),
    }
