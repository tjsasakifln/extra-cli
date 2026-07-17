"""Unit tests: golden_path fail-closed evaluate_run_outcome (NEXT-30D)."""

from __future__ import annotations

from scripts.golden_path import (
    FreshnessRecord,
    ReportRecord,
    SourceRecord,
    evaluate_run_outcome,
)


def _src(name: str, status: str, fetched: int = 10) -> SourceRecord:
    return SourceRecord(
        name=name,
        status=status,
        duration_ms=1.0,
        attempts=1,
        metrics={"fetched": fetched},
    )


def test_strict_success_with_data_and_gates():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success"), _src("compras_gov", "success")],
        {"pcp", "compras_gov"},
        FreshnessRecord(status="pass"),
        [
            ReportRecord(type="excel", status="generated"),
            ReportRecord(type="pdf", status="generated"),
        ],
        strict=True,
    )
    assert overall == "success"
    assert code == 0


def test_strict_essential_fail_is_partial():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "fail"), _src("compras_gov", "success")],
        {"pcp", "compras_gov"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
        skip_reports=True,
    )
    assert overall == "partial"
    assert code == 2


def test_strict_empty_essential_zero_not_success():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success_zero", 0), _src("compras_gov", "success_zero", 0)],
        {"pcp", "compras_gov"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
        skip_reports=True,
    )
    assert overall == "empty"
    assert code == 1


def test_strict_allow_zero_success_zero():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success_zero", 0), _src("compras_gov", "success_zero", 0)],
        {"pcp", "compras_gov"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
        skip_reports=True,
        allow_zero=True,
    )
    assert overall == "success_zero"
    assert code == 0


def test_strict_freshness_fail_exit_3():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success")],
        {"pcp"},
        FreshnessRecord(status="fail"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
        skip_reports=True,
    )
    assert code == 3
    assert overall == "failed"


def test_strict_report_fail_exit_4():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success")],
        {"pcp"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="fail")],
        strict=True,
    )
    assert code == 4
    assert overall == "failed"


def test_strict_all_sources_fail():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "fail"), _src("pncp", "fail")],
        {"pcp"},
        FreshnessRecord(status="skipped"),
        [],
        strict=True,
        skip_freshness=True,
        skip_reports=True,
    )
    # essential fail takes precedence
    assert overall == "partial"
    assert code == 2


def test_strict_non_essential_fail_degraded():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success"), _src("pncp", "fail")],
        {"pcp"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
        skip_reports=True,
    )
    assert overall == "degraded"
    assert code == 5


def test_no_strict_legacy_success_with_essential_ok():
    overall, code = evaluate_run_outcome(
        [_src("pcp", "success"), _src("pncp", "fail")],
        {"pcp"},
        FreshnessRecord(status="fail"),
        [ReportRecord(type="excel", status="fail")],
        strict=False,
    )
    assert overall == "degraded"
    assert code == 0
