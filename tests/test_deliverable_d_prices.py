"""Tests for Deliverable D price reference panel."""
from __future__ import annotations

from scripts.ops.deliverable_d_prices import (
    ComparabilityRule,
    PriceObservation,
    audit_report,
    build_panel,
    fixture_report,
    flag_outliers,
)


def test_fixture_has_ok_and_insufficient() -> None:
    report = fixture_report()
    assert report.panels
    statuses = {p["status"] for p in report.panels}
    assert "OK" in statuses
    assert "INSUFFICIENT_SAMPLE" in statuses
    audited = audit_report(report)
    assert audited["ok"] is True
    assert audited["summary"]["fail"] == 0


def test_stats_and_outliers_not_hidden() -> None:
    obs = [
        PriceObservation(
            value=v,
            value_semantic="contratado",
            tipo_obra_servico="reforma_predial",
            unidade="m2",
            lote="u",
            porte="m",
            regiao="SC",
            periodo="2025-Q1",
        )
        for v in [10.0, 11.0, 12.0, 13.0, 14.0, 100.0]
    ]
    panel = build_panel(obs, ComparabilityRule(min_sample=5))
    assert panel.status == "OK"
    assert panel.n_observations == 6
    assert panel.median is not None
    assert panel.p25 is not None and panel.p75 is not None
    assert panel.min_value == 10.0
    assert panel.max_value == 100.0
    assert 100.0 in panel.outliers_flagged


def test_insufficient_sample_marked() -> None:
    obs = [
        PriceObservation(
            value=1.0,
            value_semantic="pago",
            tipo_obra_servico="x",
            unidade="un",
            lote="l",
            porte="p",
            regiao="r",
            periodo="2025-Q1",
        ),
        PriceObservation(
            value=2.0,
            value_semantic="pago",
            tipo_obra_servico="x",
            unidade="un",
            lote="l",
            porte="p",
            regiao="r",
            periodo="2025-Q1",
        ),
    ]
    panel = build_panel(obs, ComparabilityRule(min_sample=5))
    assert panel.status == "INSUFFICIENT_SAMPLE"


def test_temporal_when_multi_period() -> None:
    report = fixture_report()
    multi = [p for p in report.panels if p["temporal_evolution"]]
    assert multi, "fixture group A has two periods"


def test_no_preco_real_claim() -> None:
    report = fixture_report()
    assert any("preço real" in c.lower() for c in report.claims_forbidden)
    for p in report.panels:
        assert p["labels_forbidden_used"] == []


def test_invalid_semantic_raises() -> None:
    bad = PriceObservation(
        value=1.0,
        value_semantic="preco_real",  # forbidden
        tipo_obra_servico="x",
        unidade="u",
        lote="l",
        porte="p",
        regiao="r",
        periodo="2025-Q1",
    )
    try:
        build_panel([bad])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_outlier_flag_helper() -> None:
    flagged = flag_outliers([1, 2, 3, 4, 5, 100])
    assert 100 in flagged
