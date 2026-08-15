"""Freshness, coverage and consumer-error observability for the research family."""

from __future__ import annotations

from typing import Any

from scripts.public_read.claim_gate import ClaimDecision
from scripts.public_read.models import ResearchPayload


def observe_research_health(
    payload: ResearchPayload,
    claim: ClaimDecision,
    *,
    consumer_errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    expected = claim.expected_partitions
    closed = claim.closed_partitions
    ratio = "0" if expected == 0 else format(closed / expected, ".6f")
    freshness_status = "STALE" if "freshness_stale" in claim.reason_codes else "FRESH"
    if "unknown_values" in claim.reason_codes and freshness_status != "STALE":
        coverage_status = "UNKNOWN"
    elif claim.nacional_completo and not claim.reason_codes:
        coverage_status = "COMPLETE"
    else:
        coverage_status = "INCOMPLETE"

    errors = list(consumer_errors or payload.consumer_errors)
    if not claim.national_claim_allowed:
        errors.append("national_claim_refused")
    ordered_errors = tuple(sorted(set(errors)))
    age_seconds = int(payload.freshness.age.total_seconds())
    return {
        "family": "research_flagship",
        "as_of": payload.as_of,
        "freshness_status": freshness_status,
        "freshness_age_seconds": age_seconds,
        "coverage_status": coverage_status,
        "coverage_partitions_expected": expected,
        "coverage_partitions_closed": closed,
        "coverage_ratio": ratio,
        "consumer_error_count": len(ordered_errors),
        "consumer_error_codes": list(ordered_errors),
        "nacional_completo": claim.nacional_completo,
        "national_claim_allowed": claim.national_claim_allowed,
    }
