"""Partition statuses through the shipped assigner."""

from __future__ import annotations

import pytest

from scripts.national_coverage.models import (
    ConsultedPartitions,
    CoverageRequest,
    NationalCoverageError,
    PublishingOrg,
)
from scripts.national_coverage.partitions import assign_partition_statuses, expected_queried_closed
from scripts.national_coverage.policy import refuse_unconsulted_as_zero
from scripts.national_coverage.universe import build_official_universe


def _universe():
    return build_official_universe(
        source="pncp",
        source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="raw",
        orgs=(
            PublishingOrg("org-a", "A", 1, "SC"),
            PublishingOrg("org-b", "B", 1, "SP"),
            PublishingOrg("org-c", "C", 1, "RS"),
        ),
    )


def test_found_zero_blocked_failed_and_unconsulted() -> None:
    universe = _universe()
    request = CoverageRequest("BR", "2026", "pncp", "publishing_org")
    partitions = assign_partition_statuses(
        universe,
        ConsultedPartitions(
            found=frozenset({"org-a"}),
            zero_confirmed={"org-b": "raw:empty"},
            failed={"org-c": "http_500"},
            queried=frozenset({"org-a", "org-b", "org-c"}),
        ),
        request,
    )
    by_id = {part.partition_id: part for part in partitions}
    assert by_id["org-a"].status == "FOUND"
    assert by_id["org-b"].status == "ZERO_CONFIRMED"
    assert by_id["org-c"].status == "FAILED"
    expected, queried, closed = expected_queried_closed(partitions)
    assert expected == 3
    assert queried == 3
    assert closed == 2


def test_unconsulted_is_blocked_not_zero() -> None:
    universe = _universe()
    request = CoverageRequest("BR", "2026", "pncp", "publishing_org")
    partitions = assign_partition_statuses(
        universe,
        ConsultedPartitions(found=frozenset({"org-a"}), queried=frozenset({"org-a"})),
        request,
    )
    by_id = {part.partition_id: part for part in partitions}
    assert by_id["org-b"].status == "BLOCKED"
    assert by_id["org-b"].queried is False
    assert by_id["org-b"].reason == "not_consulted_this_run"
    assert by_id["org-c"].status == "BLOCKED"
    with pytest.raises(NationalCoverageError, match="absence_is_not_zero"):
        refuse_unconsulted_as_zero("ZERO_CONFIRMED", queried=False, evidence_ref="nope")
    with pytest.raises(NationalCoverageError, match="absence_is_not_zero"):
        refuse_unconsulted_as_zero("ZERO_CONFIRMED", queried=True, evidence_ref=None)


def test_scoped_geography_marks_other_ufs_not_applicable() -> None:
    universe = _universe()
    request = CoverageRequest("SC", "2026", "pncp", "publishing_org")
    partitions = assign_partition_statuses(
        universe,
        ConsultedPartitions(found=frozenset({"org-a"}), queried=frozenset({"org-a"})),
        request,
    )
    by_id = {part.partition_id: part for part in partitions}
    assert by_id["org-a"].status == "FOUND"
    assert by_id["org-b"].status == "NOT_APPLICABLE"
    assert by_id["org-c"].status == "NOT_APPLICABLE"
    expected, _queried, closed = expected_queried_closed(partitions)
    assert expected == 1
    assert closed == 1
