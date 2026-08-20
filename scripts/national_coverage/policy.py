"""Fail-closed policy for the national coverage denominator.

Extra's 1.093 commercial universe, row counts, and absence of consultation
never authorize a national claim and never become ZERO_CONFIRMED.
"""

from __future__ import annotations

from scripts.national_contract_truth.national_universe import EXTRA_COMMERCIAL_DENOMINATOR
from scripts.national_coverage.models import (
    FORBIDDEN_NATIONAL_SOURCES,
    NationalCoverageError,
    OfficialStatus,
    PublishingOrg,
    UniverseKind,
)

REASON_EXTRA_1093 = "extra_1093_refused_as_national_denominator"
REASON_FORBIDDEN_SOURCE = "forbidden_national_source"
REASON_ABSENCE_IS_NOT_ZERO = "absence_is_not_zero"
REASON_OBSERVED_CANNOT_AUTHORIZE = "observed_corpus_cannot_authorize_national"
REASON_OFFICIAL_BLOCKED = "official_denominator_blocked"
REASON_UNCLOSED = "partitions_not_closed"
REASON_PARTIAL_SCOPE = "partial_does_not_authorize_national"
REASON_NOT_MEASURED = "coverage_not_measured"
REASON_ROW_COUNT = "row_count_is_not_completeness"


def normalize_org_id(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return digits
    return value.strip()


def assert_not_extra_1093(
    *,
    source: str,
    orgs: tuple[PublishingOrg, ...],
    universe_kind: UniverseKind,
) -> None:
    source_key = source.strip().lower()
    if source_key in FORBIDDEN_NATIONAL_SOURCES and universe_kind == "OFFICIAL":
        raise NationalCoverageError(f"{REASON_FORBIDDEN_SOURCE}:{source}")
    if universe_kind == "OFFICIAL" and len(orgs) == EXTRA_COMMERCIAL_DENOMINATOR:
        raise NationalCoverageError(f"{REASON_EXTRA_1093}:catalog_size={EXTRA_COMMERCIAL_DENOMINATOR}")


def extra_1093_attempted(*, source: str, org_count: int, universe_kind: UniverseKind) -> bool:
    if universe_kind != "OFFICIAL":
        return False
    source_key = source.strip().lower()
    if source_key in FORBIDDEN_NATIONAL_SOURCES:
        return True
    return org_count == EXTRA_COMMERCIAL_DENOMINATOR


def refuse_unconsulted_as_zero(status: str, *, queried: bool, evidence_ref: str | None) -> None:
    if status != "ZERO_CONFIRMED":
        return
    if not queried:
        raise NationalCoverageError(f"{REASON_ABSENCE_IS_NOT_ZERO}:unconsulted")
    if not evidence_ref:
        raise NationalCoverageError(f"{REASON_ABSENCE_IS_NOT_ZERO}:missing_evidence")


def official_denominator_is_valid(
    *,
    universe_kind: UniverseKind,
    official_status: OfficialStatus,
    expected_partitions: int,
    extra_1093: bool,
) -> bool:
    return universe_kind == "OFFICIAL" and official_status == "AVAILABLE" and expected_partitions > 0 and not extra_1093
