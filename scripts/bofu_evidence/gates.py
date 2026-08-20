"""Fail-closed gates for public-read-bofu-evidence/1.0."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.bofu_evidence.hashutil import canonical_dumps
from scripts.bofu_evidence.models import (
    COMPARABLE_PERTINENT_FAMILIES,
    COMPARABLE_UNIT,
    FORBIDDEN_FIELDS,
    FORBIDDEN_TOKENS,
    NEGATIVE_ABSENCE_MARKERS,
    UNIT_PROMOTION_UNITS,
)


def parse_iso(value: str) -> datetime:
    text = (value or "").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _walk_keys(node: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            keys.append(str(key))
            keys.extend(_walk_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.extend(_walk_keys(item))
    return keys


def _blob(node: Any) -> str:
    if isinstance(node, str):
        return node
    return canonical_dumps(node)


def _claims_and_calcs(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return list(draft.get("claims") or []) + list(draft.get("calculations") or [])


def _has_national_attempt(draft: dict[str, Any]) -> bool:
    if draft.get("national") is True:
        return True
    scope = (draft.get("coverage") or {}).get("kind")
    if str(scope).upper() in {"BR", "BRASIL", "NACIONAL", "NATIONAL"}:
        return True
    blob = _blob(draft).lower()
    if "nacional completo" in blob or "nacional_completo" in blob:
        return True
    for item in _claims_and_calcs(draft):
        if str(item.get("scope") or "").upper() in {"BR", "NATIONAL", "NACIONAL"}:
            return True
    return False


def _has_unit_promotion(draft: dict[str, Any]) -> bool:
    blob = _blob(draft).lower()
    if "custo/km" in blob or "custo por km" in blob or "cost per km" in blob:
        return True
    for item in _claims_and_calcs(draft):
        unit = str(item.get("unit") or "")
        if unit in UNIT_PROMOTION_UNITS:
            return True
        if unit and unit != COMPARABLE_UNIT and "BRL_TOTAL" in _blob(item):
            return True
    return False


def _has_negative_absence_fact(draft: dict[str, Any]) -> bool:
    for item in _claims_and_calcs(draft):
        if item.get("epistemic_class") != "FACT":
            continue
        statement = str(item.get("statement") or "").lower()
        if any(marker in statement for marker in NEGATIVE_ABSENCE_MARKERS):
            return True
    return False


def _missing_evidence(draft: dict[str, Any]) -> bool:
    for item in _claims_and_calcs(draft):
        if item.get("epistemic_class") in {"FACT", "CALCULATION"} and not item.get("evidence_refs"):
            return True
    return False


def _forbidden_hits(draft: dict[str, Any]) -> list[str]:
    keys = set(_walk_keys(draft))
    hits = [field for field in FORBIDDEN_FIELDS if field in keys]
    blob = _blob(draft)
    for token in FORBIDDEN_TOKENS:
        if token in blob:
            hits.append(token)
    return hits


def _comparable_misattached(draft: dict[str, Any]) -> bool:
    family = draft.get("family")
    attached = bool(draft.get("comparable_attached"))
    if not attached:
        return False
    return family not in COMPARABLE_PERTINENT_FAMILIES


def evaluate_gates(
    draft: dict[str, Any],
    *,
    national_coverage: dict[str, Any],
    now: str,
    as_of_source: str,
) -> dict[str, Any]:
    """Pure gate. publication/index/national stay false even on READY."""
    reject: list[str] = []
    hold: list[str] = []

    if as_of_source == "missing":
        reject.append("as_of_missing")
    if as_of_source == "wall_clock":
        hold.append("as_of_wall_clock")

    expires = draft.get("expires_at") or draft.get("expires")
    if expires and now:
        if parse_iso(now) > parse_iso(str(expires)):
            hold.append("freshness_expired")

    authorized = bool(national_coverage.get("national_claim_authorized"))
    verdict = str(national_coverage.get("verdict") or "")
    if (not authorized or verdict in {"PARTIAL", "BLOCKED", "NOT_MEASURED"}) and _has_national_attempt(draft):
        hold.append("national_claim_blocked")

    if _has_unit_promotion(draft):
        hold.append("unit_promotion_blocked")

    if _comparable_misattached(draft):
        hold.append("comparable_not_pertinent")

    if _has_negative_absence_fact(draft):
        reject.append("negative_absence_fact")

    if _missing_evidence(draft):
        reject.append("missing_evidence_ref")

    forbidden = _forbidden_hits(draft)
    if forbidden:
        reject.append("prohibited_field")

    seen: set[str] = set()
    reject_codes: list[str] = []
    for code in reject:
        if code not in seen:
            seen.add(code)
            reject_codes.append(code)
    hold_codes: list[str] = []
    for code in hold:
        if code not in seen and code not in hold_codes:
            hold_codes.append(code)

    if reject_codes:
        state = "REJECT"
        reason_codes = reject_codes
    elif hold_codes:
        state = "HOLD"
        reason_codes = hold_codes
    else:
        state = "READY"
        reason_codes = []

    return {
        "state": state,
        "reason_codes": reason_codes,
        "reject_codes": reject_codes,
        "hold_codes": hold_codes,
        "publication": False,
        "index": False,
        "national": False,
    }
