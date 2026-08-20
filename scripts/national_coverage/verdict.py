"""Fail-closed coverage verdict. No opaque confidence score."""

from __future__ import annotations

from scripts.national_coverage.models import (
    CLOSED_PARTITION_STATUSES,
    CoverageRequest,
    PartitionState,
    VerdictToken,
    VersionedUniverse,
    is_national_geography,
)
from scripts.national_coverage.policy import (
    REASON_EXTRA_1093,
    REASON_NOT_MEASURED,
    REASON_OBSERVED_CANNOT_AUTHORIZE,
    REASON_OFFICIAL_BLOCKED,
    REASON_PARTIAL_SCOPE,
    REASON_UNCLOSED,
    extra_1093_attempted,
    official_denominator_is_valid,
)


def decide_verdict(
    *,
    universe: VersionedUniverse,
    partitions: tuple[PartitionState, ...],
    request: CoverageRequest,
    measured: bool,
) -> tuple[VerdictToken, bool, tuple[str, ...]]:
    reasons: list[str] = []
    extra_1093 = extra_1093_attempted(
        source=universe.official_source,
        org_count=len(universe.expected_orgs),
        universe_kind=universe.universe_kind,
    )
    if extra_1093:
        reasons.append(REASON_EXTRA_1093)
        return "BLOCKED", False, tuple(reasons)
    if not measured:
        reasons.append(REASON_NOT_MEASURED)
        return "NOT_MEASURED", False, tuple(reasons)

    national = is_national_geography(request.geography)
    expected = [part for part in partitions if part.expected]
    closed = [part for part in expected if part.status in CLOSED_PARTITION_STATUSES]
    unclosed = [part for part in expected if part.status not in CLOSED_PARTITION_STATUSES]

    if universe.universe_kind == "OBSERVED_CORPUS" or universe.official_status == "BLOCKED":
        reasons.append(REASON_OFFICIAL_BLOCKED)
        if universe.official_block_cause:
            reasons.append(f"official_block_cause:{universe.official_block_cause}")
        reasons.append(REASON_OBSERVED_CANNOT_AUTHORIZE)
        if universe.labeled_observed_corpus:
            reasons.append("denominator_labeled_observed_corpus")
        token: VerdictToken = "BLOCKED" if national else "PARTIAL"
        if not national:
            reasons.append(REASON_PARTIAL_SCOPE)
        return token, False, tuple(reasons)

    valid = official_denominator_is_valid(
        universe_kind=universe.universe_kind,
        official_status=universe.official_status,
        expected_partitions=len(expected),
        extra_1093=False,
    )
    if not valid:
        reasons.append(REASON_OFFICIAL_BLOCKED)
        return "BLOCKED", False, tuple(reasons)

    if unclosed:
        reasons.append(REASON_UNCLOSED)
        reasons.append(f"unclosed_count:{len(unclosed)}")
        if any(part.status == "BLOCKED" and not part.queried for part in unclosed):
            reasons.append("unconsulted_partitions_remain")
        if any(part.status == "FAILED" for part in unclosed):
            reasons.append("failed_partitions")
        if not national:
            reasons.append(REASON_PARTIAL_SCOPE)
        return "PARTIAL", False, tuple(reasons)

    if not national:
        reasons.append(REASON_PARTIAL_SCOPE)
        return "PARTIAL", False, tuple(reasons)

    if not closed:
        reasons.append(REASON_NOT_MEASURED)
        return "NOT_MEASURED", False, tuple(reasons)

    return "NATIONAL_CLAIM_AUTHORIZED", True, tuple(reasons)
