"""Partition closer: UNKNOWN is not zero; ZERO needs pagination proof."""

from __future__ import annotations

from scripts.national_claims.models import OrgSpec, PartitionRecord
from scripts.national_claims.partitions import (
    counts_close,
    normalize_partition,
    reconcile_claim_partitions,
)
from scripts.national_claims.universe import build_national_universe


def _universe():
    return build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=(
            OrgSpec("org-a", "A"),
            OrgSpec("org-b", "B"),
        ),
        method_version="pncp-orgaos-publicantes-v1",
    )


def test_unknown_does_not_become_zero() -> None:
    record = normalize_partition(
        PartitionRecord(
            partition_id="org-b",
            expected=True,
            attempted=False,
            status="ZERO_CONFIRMED",
            records=0,
        )
    )
    assert record.status == "UNKNOWN"
    assert record.records is None
    assert record.status != "ZERO_CONFIRMED"


def test_legacy_not_consulted_blocked_is_unknown() -> None:
    record = normalize_partition(
        PartitionRecord(
            partition_id="org-b",
            expected=True,
            attempted=True,
            status="BLOCKED",
            evidence_ref="not_consulted_this_run",
            reason="not_consulted_this_run",
        )
    )
    assert record.status == "UNKNOWN"
    assert record.attempted is False


def test_zero_confirmed_rejected_without_pagination_proof() -> None:
    record = normalize_partition(
        PartitionRecord(
            partition_id="org-b",
            expected=True,
            attempted=True,
            status="ZERO_CONFIRMED",
            records=0,
            request_complete=False,
            pagination_complete=False,
            evidence_ref="raw:empty",
        )
    )
    assert record.status == "UNKNOWN"
    assert record.reason == "zero_without_pagination_proof"


def test_zero_confirmed_accepted_with_complete_request_and_pagination() -> None:
    record = normalize_partition(
        PartitionRecord(
            partition_id="org-b",
            expected=True,
            attempted=True,
            status="ZERO_CONFIRMED",
            records=0,
            request_complete=True,
            pagination_complete=True,
            evidence_ref="raw:empty",
        )
    )
    assert record.status == "ZERO_CONFIRMED"


def test_partitions_close_expected_attempted_closed() -> None:
    universe = _universe()
    reconciliation = reconcile_claim_partitions(
        universe,
        (
            PartitionRecord(
                "org-a",
                True,
                True,
                "FOUND",
                pages_fetched=1,
                pages_expected=1,
                records=2,
                pagination_complete=True,
                request_complete=True,
                evidence_ref="raw:a",
            ),
            PartitionRecord(
                "org-b",
                True,
                True,
                "ZERO_CONFIRMED",
                pages_fetched=1,
                pages_expected=1,
                records=0,
                pagination_complete=True,
                request_complete=True,
                evidence_ref="raw:b",
            ),
        ),
    )
    assert counts_close(reconciliation)
    assert reconciliation.expected == 2
    assert reconciliation.attempted == 2
    assert reconciliation.closed == 2
    assert sum(reconciliation.by_status.values()) == reconciliation.expected


def test_missing_execution_is_counted_unknown_not_zero() -> None:
    universe = _universe()
    reconciliation = reconcile_claim_partitions(
        universe,
        (
            PartitionRecord(
                "org-a",
                True,
                True,
                "FOUND",
                request_complete=True,
                pagination_complete=True,
                evidence_ref="raw:a",
            ),
        ),
    )
    assert reconciliation.by_status["UNKNOWN"] == 1
    assert reconciliation.by_status["ZERO_CONFIRMED"] == 0
    assert reconciliation.closed == 1
    assert reconciliation.expected == 2
    assert any("missing_partition:org-b" in item for item in reconciliation.blockers)
