"""Fitness function automation tests."""
from __future__ import annotations

from scripts.architecture.fitness_check import (
    check_canonical_weekly_entrypoint,
    check_no_llm_in_coverage_freshness,
    run_all,
)


def test_canonical_weekly_entrypoint_on_main_tree() -> None:
    r = check_canonical_weekly_entrypoint()
    assert r["has_extra_weekly"] is True
    assert r["points_to_weekly_cycle"] is True
    assert r["ok"] is True


def test_no_llm_imports_in_coverage_freshness() -> None:
    r = check_no_llm_in_coverage_freshness()
    assert r["ok"] is True
    assert r["hits"] == []


def test_run_all_report_shape() -> None:
    report = run_all()
    assert "checks" in report
    assert len(report["checks"]) >= 3
    assert isinstance(report["ok"], bool)
