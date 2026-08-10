"""Coverage accounting must never report ratio > 1 or hide orphans."""

from __future__ import annotations

from scripts.confenge_target_fit.coverage import (
    build_coverage_snapshot,
    coverage_ratio,
    reconcile_accounting,
)


def test_coverage_ratio_clamped_at_one() -> None:
    r = coverage_ratio(materialized_company_count=511_646, canonical_company_count=511_645)
    assert r is not None
    assert 0.0 <= r <= 1.0
    assert r == 1.0


def test_coverage_ratio_zero_canonical() -> None:
    assert coverage_ratio(materialized_company_count=10, canonical_company_count=0) is None


def test_reconcile_accounting_orphan_fails_fully_reconciled() -> None:
    acc = reconcile_accounting(
        canonical_roots=100,
        materialized_roots=101,
        orphan_materialized_roots=1,
    )
    assert acc["coverage_ratio"] == 1.0
    assert acc["materialized_valid_roots"] == 100
    assert acc["orphan_materialized_roots"] == 1
    assert acc["invariants"]["orphan_materialized_roots_eq_0"] is False
    assert acc["FULLY_RECONCILED"] is False


def test_reconcile_accounting_closed_equation() -> None:
    acc = reconcile_accounting(
        canonical_roots=1000,
        materialized_roots=900,
        explicit_exclusions=50,
        exclusion_reason_counts={"INVALID_CNPJ": 50},
    )
    assert acc["unexplained_missing"] == 50
    assert acc["invariants"]["equation_closed"] is True
    assert acc["coverage_ratio"] == 0.9


def test_build_coverage_snapshot_never_ratio_gt_one() -> None:
    snap = build_coverage_snapshot(
        canonical_company_count=511_645,
        materialized_company_count=511_646,
        expected_company_roots=511_645,
        visited_company_roots=511_645,
        unexplained_missing=0,
        pagination_exhausted_normally=True,
        orphan_materialized_roots=1,
        last_full_reconcile_completed_at="2026-08-10T00:00:00+00:00",
    )
    assert snap["coverage_ratio"] is not None
    assert snap["coverage_ratio"] <= 1.0
    assert snap["orphan_materialized_roots"] == 1
    assert snap["FULL_NATIONAL_READY"] is False
    assert snap["FULLY_RECONCILED"] is False
