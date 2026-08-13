"""Claim registry, leakage fail-closed, labels, PIT dataset unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.predictive.backtest import run_classification_backtest
from scripts.predictive.claims import ClaimRegistry
from scripts.predictive.dataset import (
    build_competitive_winner_dataset,
    build_demand_dataset,
    build_discount_dataset,
)
from scripts.predictive.labels import demand_label, is_aec_object, winner_label, winning_discount
from scripts.predictive.leakage import assert_no_leakage, audit_examples
from scripts.predictive.metrics import classification_report, evaluate_classification_gates
from scripts.predictive.profile_calibration import personalization_blockers


def test_claim_registry_seven_claims(tmp_path):
    path = tmp_path / "claims.json"
    reg = ClaimRegistry(path=path)
    assert len(reg.all()) == 7
    assert reg.commercial_recommendation() == "CLAIM_FORBIDDEN"
    reg.set_state("PREDICTIVE_DEMAND_FORECAST_AVAILABLE", "IMPLEMENTED", force=True)
    reg.set_state(
        "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "HISTORICAL_BACKTEST_PROVEN",
        evidence={"bss": 0.2},
        force=True,
    )
    reg.save()
    reg2 = ClaimRegistry(path=path)
    assert reg2.get("PREDICTIVE_DEMAND_FORECAST_AVAILABLE").state == "HISTORICAL_BACKTEST_PROVEN"
    assert reg2.get("PREDICTIVE_INTELLIGENCE_FULLY_PROVEN").state != "PRODUCTION_AVAILABLE"
    assert not reg2.prediction_allowed("PREDICTIVE_DEMAND_FORECAST_AVAILABLE")


def test_fully_proven_requires_market_trio_production(tmp_path):
    reg = ClaimRegistry(path=tmp_path / "c.json")
    for cid in (
        "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
        "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
    ):
        reg.set_state(cid, "PRODUCTION_AVAILABLE", force=True, evidence={"prospective_calibrated": True})
    reg._refresh_derived()
    assert reg.get("PREDICTIVE_INTELLIGENCE_FULLY_PROVEN").state == "PRODUCTION_AVAILABLE"
    assert reg.commercial_recommendation() == "CLAIM_ALLOWED"


def test_invalid_demand_negative_rejected():
    as_of = datetime(2024, 1, 1, tzinfo=UTC)
    lab = demand_label(
        as_of=as_of,
        horizon_days=30,
        future_aec_events=[],
        coverage_ok=False,
    )
    assert lab.label_value is None
    assert lab.label_quality == "rejected_invalid_negative"


def test_valid_demand_negative_with_coverage():
    as_of = datetime(2024, 1, 1, tzinfo=UTC)
    lab = demand_label(
        as_of=as_of,
        horizon_days=30,
        future_aec_events=[],
        coverage_ok=True,
    )
    assert lab.label_value == 0.0


def test_winner_not_in_candidate_rejected():
    lab = winner_label(supplier_id="A", winner_id="B", in_candidate_set=False)
    assert lab.label_value is None


def test_discount_semantics_reject_paid():
    d, meta = winning_discount(
        estimated_value=100.0,
        outcome_value=90.0,
        estimated_value_semantics="valor_estimado",
        outcome_value_semantics="valor_pago",
        same_process=True,
    )
    assert d is None
    assert meta["block"] == "paid_value_forbidden"


def test_leakage_fail_closed_winner_feature():
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    bad = {
        "example_id": "x1",
        "as_of_at": as_of.isoformat(),
        "label_window_start": as_of.isoformat(),
        "label_window_end": (as_of + timedelta(days=30)).isoformat(),
        "features_json": {"winner_id": 1.0, "n_contracts_30d": 2.0},
        "source_max_event_at": as_of.isoformat(),
    }
    with pytest.raises(RuntimeError, match="LEAKAGE"):
        assert_no_leakage([bad])


def test_leakage_fail_closed_future_event():
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    bad = {
        "example_id": "x2",
        "as_of_at": as_of.isoformat(),
        "label_window_start": as_of.isoformat(),
        "features_json": {"n_contracts_30d": 1.0},
        "feature_events": {"n_contracts_30d": (as_of + timedelta(days=5)).isoformat()},
        "source_max_event_at": (as_of + timedelta(days=5)).isoformat(),
    }
    report = audit_examples([bad])
    assert report.ok is False


def test_demand_dataset_pit_and_no_leak():
    base = datetime(2022, 1, 1, tzinfo=UTC)
    contracts = []
    for i in range(24):
        contracts.append(
            {
                "orgao_cnpj": "12345678000199",
                "objeto_contrato": "Construcao de edificio escolar",
                "data_publicacao": base + timedelta(days=30 * i),
                "valor_total": 100000 + i * 1000,
                "fornecedor_cnpj": f"{i:014d}",
                "contrato_id": f"c{i}",
            }
        )
    # second ente quieter
    for i in range(12):
        contracts.append(
            {
                "orgao_cnpj": "99888777000166",
                "objeto_contrato": "Pavimentacao asfaltica urbana",
                "data_publicacao": base + timedelta(days=60 * i),
                "valor_total": 50000,
                "fornecedor_cnpj": "111",
                "contrato_id": f"d{i}",
            }
        )
    ds = build_demand_dataset(contracts, horizon_days=30, require_coverage=True)
    assert ds.examples, "expected some examples"
    assert_no_leakage(ds.examples)
    # all features event_at <= as_of checked via leakage
    for ex in ds.examples:
        assert ex["label_quality"] == "ok"
        assert "features_json" in ex


def test_competitive_dataset_builds():
    base = datetime(2021, 1, 1, tzinfo=UTC)
    contracts = []
    for i in range(40):
        contracts.append(
            {
                "orgao_cnpj": "12345678000199",
                "objeto_contrato": "Obra de reforma predial",
                "data_assinatura": base + timedelta(days=20 * i),
                "valor_total": 200000,
                "fornecedor_cnpj": f"{(i % 5):014d}",
                "contrato_id": f"w{i}",
            }
        )
    ds = build_competitive_winner_dataset(contracts, min_history_days=60)
    assert ds.examples
    assert any(e["label_value"] == 1 for e in ds.examples)
    assert any(e["label_value"] == 0 for e in ds.examples)
    assert_no_leakage(ds.examples)


def test_discount_dataset_data_blocked_when_empty():
    ds = build_discount_dataset([])
    assert ds.status == "data_blocked"
    assert not ds.examples


def test_backtest_runs_on_synthetic_demand():
    base = datetime(2020, 1, 1, tzinfo=UTC)
    contracts = []
    for ente in range(5):
        for i in range(36):
            contracts.append(
                {
                    "orgao_cnpj": f"{ente:014d}",
                    "objeto_contrato": "Construcao de predio publico",
                    "data_publicacao": base + timedelta(days=30 * i + ente),
                    "valor_total": 100000,
                    "fornecedor_cnpj": "1",
                    "contrato_id": f"{ente}-{i}",
                }
            )
    ds = build_demand_dataset(contracts, horizon_days=30)
    bt = run_classification_backtest(ds.examples, target_name="demand_30d", n_folds=2)
    assert bt.task == "classification"
    assert bt.claim_recommendation in {
        "DATA_BLOCKED",
        "BACKTEST_FAILED",
        "HISTORICAL_BACKTEST_PROVEN",
    }
    # With synthetic small n, expect DATA_BLOCKED or BACKTEST_FAILED — not silent PRODUCTION
    assert bt.claim_recommendation != "PRODUCTION_AVAILABLE"


def test_extra_profile_blockers():
    blockers = personalization_blockers("extra_construtora")
    assert blockers["personalization_allowed"] is False
    assert any(m["field"] == "margem_minima" for m in blockers["missing_critical"])


def test_is_aec_object():
    assert is_aec_object("Construcao de escola municipal")
    assert not is_aec_object("Aquisicao de medicamentos hospitalares")


def test_gates_data_blocked_small_n():
    metrics = classification_report([0, 1, 0, 1], [0.2, 0.8, 0.3, 0.7])
    gate = evaluate_classification_gates(metrics)
    assert gate["data_blocked"] is True
    assert gate["passed"] is False
