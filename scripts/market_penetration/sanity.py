"""Fail-closed sanity checks for the operational penetration snapshot."""

from __future__ import annotations

import re
from typing import Any

from scripts.market_penetration.facts import (
    PII_DIMENSION_KEYS,
    JoinResult,
    WarmblyFreshness,
)
from scripts.market_penetration.icp_denominator import (
    DEFAULT_RULES,
    STAGES,
    IcpRules,
    PenetrationError,
    classify_stage,
)

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def cumulative_from_exclusive(by_stage: dict[str, int]) -> dict[str, int]:
    """Cumulative funnel from exclusive #388 buckets. Later stages are subsets."""
    cumulative: dict[str, int] = {}
    running = 0
    for stage in reversed(STAGES):
        running += int(by_stage.get(stage) or 0)
        cumulative[stage] = running
    return cumulative


def _check_monotonic(by_stage: dict[str, int], explanations: tuple[str, ...]) -> dict[str, Any]:
    cumulative = cumulative_from_exclusive(by_stage)
    violations: list[str] = []
    previous: int | None = None
    previous_name = ""
    for stage in STAGES:
        value = cumulative[stage]
        if previous is not None and value > previous:
            violations.append(f"{stage}_cumulative={value}>{previous_name}={previous}")
        previous = value
        previous_name = stage
    icp = sum(int(by_stage.get(stage) or 0) for stage in STAGES)
    reachable = cumulative["ACTIONABLE_ROUTE"]
    contacted_plus = cumulative["CONTACTED"]
    if reachable > icp:
        violations.append(f"reachable={reachable}>icp={icp}")
    if contacted_plus > reachable:
        violations.append(f"contacted_plus={contacted_plus}>reachable={reachable}")
    if violations and not explanations:
        return {"name": "monotonic_stages", "passed": False, "detail": ";".join(violations)}
    if violations:
        return {
            "name": "monotonic_stages",
            "passed": True,
            "detail": "explained:" + ",".join(explanations) + ";" + ";".join(violations),
        }
    return {"name": "monotonic_stages", "passed": True, "detail": "cumulative_non_increasing"}


def _check_duplicates(join: JoinResult) -> dict[str, Any]:
    dupes = [issue for issue in join.issues if issue.kind == "duplicate_join"]
    if dupes:
        return {
            "name": "duplicate_joins",
            "passed": False,
            "detail": ",".join(f"{item.source}:{item.account_id}" for item in dupes),
        }
    return {"name": "duplicate_joins", "passed": True, "detail": "none"}


def _check_missing_ids(join: JoinResult) -> dict[str, Any]:
    missing = [issue for issue in join.issues if issue.kind == "missing_canonical_id"]
    if missing:
        return {
            "name": "missing_canonical_id",
            "passed": False,
            "detail": ",".join(f"{item.source}:{item.detail}" for item in missing),
        }
    return {"name": "missing_canonical_id", "passed": True, "detail": "none"}


def _check_stale_warmbly(freshness: WarmblyFreshness) -> dict[str, Any]:
    if freshness.stale:
        return {"name": "stale_warmbly_import", "passed": False, "detail": freshness.reason}
    return {"name": "stale_warmbly_import", "passed": True, "detail": freshness.reason}


def _unknown_expected(join: JoinResult, rules: IcpRules = DEFAULT_RULES) -> bool:
    return any(classify_stage(account.fact, rules) == "UNKNOWN" for account in join.accounts)


def _check_unknown_preserved(join: JoinResult, snapshot: dict[str, Any]) -> dict[str, Any]:
    unknown = int(snapshot.get("by_stage", {}).get("UNKNOWN") or 0)
    uncaptured = snapshot.get("uncaptured_account_ids") or []
    if _unknown_expected(join) and unknown == 0:
        return {
            "name": "unknown_preserved",
            "passed": False,
            "detail": "expected_UNKNOWN_dropped_or_recoded",
        }
    if unknown > 0 and not uncaptured:
        return {
            "name": "unknown_preserved",
            "passed": False,
            "detail": "UNKNOWN_not_queryable",
        }
    if unknown != int(snapshot.get("counts", {}).get("UNKNOWN") or 0):
        return {
            "name": "unknown_preserved",
            "passed": False,
            "detail": "UNKNOWN_count_mismatch",
        }
    return {
        "name": "unknown_preserved",
        "passed": True,
        "detail": f"UNKNOWN={unknown}",
    }


def collect_pii_hits(dimensions: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for name, rows in dimensions.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in row:
                if str(key).lower() in PII_DIMENSION_KEYS:
                    hits.append(f"{name}.{key}")
            value = str(row.get("value") or "")
            if _EMAIL_RE.search(value) or _PHONE_RE.search(value):
                hits.append(f"{name}.value")
    return hits


def _check_no_pii(dimensions: dict[str, Any]) -> dict[str, Any]:
    hits = collect_pii_hits(dimensions)
    if hits:
        return {"name": "aggregates_pii_free", "passed": False, "detail": ",".join(hits)}
    return {"name": "aggregates_pii_free", "passed": True, "detail": "no_pii_keys_or_values"}


def run_sanity(
    join: JoinResult,
    snapshot: dict[str, Any],
    dimensions: dict[str, Any],
    *,
    explanations: tuple[str, ...] = (),
    fail_closed: bool = True,
) -> list[dict[str, Any]]:
    checks = [
        _check_monotonic(snapshot.get("by_stage") or {}, explanations),
        _check_duplicates(join),
        _check_missing_ids(join),
        _check_stale_warmbly(join.warmbly_freshness),
        _check_unknown_preserved(join, snapshot),
        _check_no_pii(dimensions),
    ]
    failed = [check["name"] for check in checks if not check["passed"]]
    if fail_closed and failed:
        raise PenetrationError("sanity_failed:" + ",".join(failed))
    return checks
