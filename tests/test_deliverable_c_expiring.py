"""Tests for Deliverable C expiring contracts."""
from __future__ import annotations

from scripts.ops.deliverable_c_expiring import (
    WindowConfig,
    audit_report,
    build_row,
    fixture_report,
    select_expiring,
)


def test_fixture_in_window_and_excludes_missing() -> None:
    report = fixture_report("2026-07-18")
    assert report.status == "OK"
    assert report.excluded_no_vigencia >= 1
    assert all(r["termino_fonte"] and r["termino_verificado_em"] for r in report.rows)
    assert any(r["aditivos_aplicados"] for r in report.rows)
    assert any(r["termino_tipo"] == "ESTIMADO" for r in report.rows)
    assert any(r["termino_tipo"] == "CONTRATUAL" for r in report.rows)
    audited = audit_report(report)
    assert audited["ok"] is True


def test_missing_vigencia_excluded() -> None:
    cfg = WindowConfig(as_of="2026-07-18")
    row, reason = build_row({"orgao": "x", "vigencia_fim": None}, cfg)
    assert row is None
    assert reason == "missing_vigencia"


def test_missing_source_excluded() -> None:
    cfg = WindowConfig(as_of="2026-07-18")
    row, reason = build_row(
        {
            "orgao": "x",
            "vigencia_fim": "2026-11-18",
            "termino_fonte": "",
            "termino_verificado_em": "",
        },
        cfg,
    )
    assert row is None
    assert reason == "missing_source_or_verification"


def test_out_of_window() -> None:
    cfg = WindowConfig(as_of="2026-07-18", min_days=90, max_days=180)
    row, reason = build_row(
        {
            "orgao": "x",
            "vigencia_fim": "2026-08-01",  # ~14 days
            "termino_fonte": "pncp",
            "termino_verificado_em": "2026-07-18",
        },
        cfg,
    )
    assert row is None
    assert reason == "out_of_window"


def test_no_fabricated_relicitacao_pct() -> None:
    report = fixture_report()
    for r in report.rows:
        assert r["relicitacao"]["probability_pct"] is None
        assert r["relicitacao"]["fabricated_percent_forbidden"] is True
        assert r["confianca"]
        assert r["limitacoes"] is not None


def test_empty_candidates() -> None:
    report = select_expiring([], WindowConfig(as_of="2026-07-18"))
    assert report.status == "EMPTY"
    assert audit_report(report)["ok"] is True
