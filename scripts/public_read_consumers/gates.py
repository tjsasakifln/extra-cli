"""Pure freshness, coverage, claim, suppression and live-label gates."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

MAX_AGE_HOURS = 48
FRESHNESS_POLICY = "contracts-freshness-slo-v1"

REASON_FIXTURE_AS_LIVE = "fixture_as_live"
REASON_STALE = "stale_evidence"
REASON_COVERAGE = "coverage_insufficient"
REASON_NEEDS_DATA = "NEEDS_DATA"
REASON_NATIONAL_CLAIM = "national_claim_blocked"
REASON_EXTRA_1093 = "inconsistent_denominator_commercial_universe"
REASON_TYPOLOGY = "typology_failed"
REASON_DENOMINATOR = "denominator_failed"
REASON_LIVE_ABSENT = "official_live_absent"
REASON_GATE_FAILED = "gate_failed"
REASON_UNKNOWN_INPUT = "input_unknown"
REASON_FORBIDDEN_FIELD = "unauthorized_field"
REASON_LKG_EXPIRED = "lkg_expired"
REASON_SELECT_ONLY = "write_sql_refused"

DATA_READY = "DATA_READY"
DATA_HOLD = "DATA_HOLD"
DATA_REJECT = "DATA_REJECT"
NEEDS_DATA = "NEEDS_DATA"


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def expires_at(source_as_of: str | None, *, max_age_hours: int = MAX_AGE_HOURS) -> str | None:
    parsed = parse_datetime(source_as_of)
    if parsed is None:
        return None
    return (parsed + timedelta(hours=max_age_hours)).isoformat()


def is_stale(*, generated_at: str, source_as_of: str | None, max_age_hours: int = MAX_AGE_HOURS) -> bool:
    generated = parse_datetime(generated_at)
    source = parse_datetime(source_as_of)
    if generated is None or source is None:
        return True
    return generated - source > timedelta(hours=max_age_hours)


def freshness_block(
    *,
    generated_at: str,
    source_as_of: str | None,
    stale: bool | None = None,
    max_age_hours: int = MAX_AGE_HOURS,
    invalidation_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    computed = is_stale(generated_at=generated_at, source_as_of=source_as_of, max_age_hours=max_age_hours)
    stale_flag = computed if stale is None else bool(stale) or computed
    return {
        "generated_at": generated_at,
        "source_as_of": source_as_of,
        "expires_at": expires_at(source_as_of, max_age_hours=max_age_hours),
        "max_age_hours": max_age_hours,
        "policy": FRESHNESS_POLICY,
        "stale": stale_flag,
        "invalidation_keys": list(invalidation_keys),
    }


def is_fixture_catalog(payload: dict[str, Any]) -> bool:
    mode = str(payload.get("catalog_mode") or "fixture").strip() or "fixture"
    if mode in {"fixture", "offline_catalog"}:
        return True
    if payload.get("test_only") is True or payload.get("never_index") is True:
        return True
    if str(payload.get("producer_status") or "") == "CONTRACT_FIXTURE":
        return True
    if payload.get("official_live") is False:
        return True
    schema = str(payload.get("schema") or "").lower()
    return "fixture" in schema


def claimed_live(payload: dict[str, Any]) -> bool:
    return bool(payload.get("claimed_live") or payload.get("official_live"))


def fixture_as_live_violation(payload: dict[str, Any]) -> bool:
    reasons = payload.get("reason_codes") or ()
    if REASON_FIXTURE_AS_LIVE in reasons:
        return True
    return claimed_live(payload) and is_fixture_catalog(payload)


def refuse_fixture_as_live(payload: dict[str, Any]) -> list[str]:
    if fixture_as_live_violation(payload):
        return [REASON_FIXTURE_AS_LIVE]
    return []


def extra_1093_used(payload: dict[str, Any]) -> bool:
    kind = str(payload.get("denominator_kind") or payload.get("denominator") or "")
    if payload.get("use_extra_1093_as_denominator") is True:
        return True
    return "1093" in kind or kind == "extra_commercial_1093"


def evaluate_claim_authorization(claim: dict[str, Any] | None, *, geography: str | None) -> dict[str, Any]:
    raw = dict(claim or {})
    reasons: list[str] = []
    extra = extra_1093_used(raw) or extra_1093_used({"denominator_kind": raw.get("denominator_kind")})
    nacional_completo = bool(raw.get("nacional_completo"))
    allowed = bool(raw.get("national_claim_allowed")) and nacional_completo and not extra
    if extra:
        reasons.append(REASON_EXTRA_1093)
        allowed = False
    if str(geography or "").upper() in {"BR", "BRASIL", "NACIONAL"} and not allowed:
        reasons.append(REASON_NATIONAL_CLAIM)
        allowed = False
    if not nacional_completo:
        reasons.append("national_denominator_incomplete")
        allowed = False
    if raw.get("producer_status") == "CONTRACT_FIXTURE" and raw.get("official_live") is True:
        reasons.append(REASON_FIXTURE_AS_LIVE)
        allowed = False
    return {
        "national_claim_allowed": allowed,
        "nacional_completo": nacional_completo and allowed,
        "reason_codes": reasons,
        "gate": raw.get("schema") or "national_universe/1.0",
        "issue": "#302",
        "producer_status": raw.get("producer_status") or "CONTRACT_FIXTURE",
        "official_live": bool(raw.get("official_live")) and not extra,
        "commercial_universe_used_as_denominator": extra,
    }


def coverage_ok(coverage: dict[str, Any] | None, *, min_n: int = 1) -> bool:
    if not isinstance(coverage, dict):
        return False
    if coverage.get("status") in {"INCOMPLETE", "UNKNOWN", "FAILED"}:
        return False
    n = coverage.get("n")
    if n is None:
        n = coverage.get("usable_n")
    if n is None:
        return False
    try:
        return int(n) >= min_n
    except (TypeError, ValueError):
        return False


def unknown_remains_unknown(value: Any) -> Any:
    if value is None or value == "" or value == "UNKNOWN":
        return None
    return value


def lkg_usable(snapshot: dict[str, Any] | None, *, now: str) -> bool:
    if not isinstance(snapshot, dict):
        return False
    if not snapshot.get("last_known_good"):
        return False
    expires = snapshot.get("lkg_expires_at") or snapshot.get("expires_at")
    parsed_expires = parse_datetime(str(expires) if expires else None)
    parsed_now = parse_datetime(now)
    if parsed_expires is None or parsed_now is None:
        return False
    return parsed_now <= parsed_expires
