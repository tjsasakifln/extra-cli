"""Outcome reconciliation and drift suspension — real shipped functions."""

from __future__ import annotations

import json

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.predictive.claims import ClaimRegistry
from scripts.predictive.drift import apply_drift_to_claims, evaluate_outcomes_drift
from scripts.predictive.outcomes import (
    build_winners_index,
    resolve_competitive_winner_prediction,
    resolve_demand_prediction,
    resolve_predictions,
)
from scripts.predictive.weekly_section import build_weekly_predictive_section


def test_resolve_demand_positive_with_event():
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "pred_test_1",
        "target_name": "demand_30d",
        "entity_id": "111",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.4,
        "probability": 0.4,
    }
    events = {"111": [as_of + timedelta(days=10)]}
    out = resolve_demand_prediction(pred, events)
    assert out is not None
    assert out.label_value == 1.0
    assert out.outcome_quality == "ok"
    assert out.outcome_source == "observed_aec_event"
    assert out.brier_component is not None


def test_resolve_demand_negative_requires_coverage():
    """Empty events without coverage must NOT become label 0.0."""
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "pred_no_cov",
        "target_name": "demand_30d",
        "entity_id": "ghost_ente",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.2,
        "probability": 0.2,
    }
    # No events at all for entity → no weak nearby coverage either
    out = resolve_demand_prediction(pred, {})
    assert out is not None  # window elapsed (2024 << now)
    assert out.label_value is None
    assert out.outcome_quality == "rejected_invalid_negative"
    assert out.outcome_source == "insufficient_coverage"
    assert out.brier_component is None
    assert out.is_scorable is False


def test_resolve_demand_negative_with_explicit_coverage():
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "pred_cov",
        "target_name": "demand_30d",
        "entity_id": "covered",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.3,
        "coverage_ok": True,
    }
    out = resolve_demand_prediction(pred, {"covered": []})
    assert out is not None
    assert out.label_value == 0.0
    assert out.outcome_quality == "ok"
    assert out.outcome_source == "coverage_confirmed_absence"
    assert out.is_scorable is True


def test_resolve_demand_negative_with_weak_nearby_coverage():
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "pred_weak",
        "target_name": "demand_30d",
        "entity_id": "active_ente",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.25,
    }
    # Event before as_of (history) within 180d → weak coverage; no event in window → negative ok
    events = {"active_ente": [as_of - timedelta(days=30)]}
    out = resolve_demand_prediction(pred, events)
    assert out is not None
    assert out.label_value == 0.0
    assert out.outcome_quality == "ok"


def test_resolve_immature_returns_none():
    as_of = datetime.now(timezone.utc).replace(microsecond=0)
    pred = {
        "prediction_id": "pred_immature",
        "target_name": "demand_30d",
        "entity_id": "222",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.5,
        "coverage_ok": True,
    }
    out = resolve_demand_prediction(pred, {"222": []})
    assert out is None


def test_p2a_resolve_winner_match():
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "p2a_1",
        "target_name": "competitive_winner_p2a",
        "procurement_id": "C-100",
        "supplier_id": "SUP-A",
        "entity_id": "ORG-1",
        "as_of_at": as_of.isoformat(),
        "score": 0.7,
        "probability": 0.7,
    }
    winners = {
        "C-100": {
            "winner_id": "SUP-A",
            "event_at": as_of + timedelta(days=5),
        }
    }
    out = resolve_competitive_winner_prediction(pred, winners)
    assert out is not None
    assert out.label_value == 1.0
    assert out.outcome_quality == "ok"
    assert out.outcome_source == "observed_winner"
    assert out.is_scorable is True


def test_p2a_resolve_non_winner():
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "p2a_2",
        "target_name": "competitive_winner_p2a",
        "procurement_id": "C-200",
        "supplier_id": "SUP-B",
        "as_of_at": as_of.isoformat(),
        "score": 0.4,
    }
    winners = {
        "C-200": {
            "winner_id": "SUP-A",
            "event_at": as_of + timedelta(days=2),
        }
    }
    out = resolve_competitive_winner_prediction(pred, winners)
    assert out is not None
    assert out.label_value == 0.0
    assert out.outcome_quality == "ok"


def test_p2a_immature_no_outcome():
    pred = {
        "prediction_id": "p2a_imm",
        "target_name": "competitive_winner_p2a",
        "procurement_id": "C-MISSING",
        "supplier_id": "SUP-A",
        "as_of_at": "2024-01-01T00:00:00+00:00",
        "score": 0.5,
    }
    out = resolve_competitive_winner_prediction(pred, {})
    assert out is None


def test_p2a_rejects_outcome_before_as_of():
    as_of = datetime(2024, 6, 10, tzinfo=timezone.utc)
    pred = {
        "prediction_id": "p2a_leak",
        "target_name": "competitive_winner_p2a",
        "procurement_id": "C-300",
        "supplier_id": "SUP-A",
        "as_of_at": as_of.isoformat(),
        "score": 0.5,
    }
    winners = {
        "C-300": {
            "winner_id": "SUP-A",
            "event_at": as_of - timedelta(days=1),  # before as_of
        }
    }
    out = resolve_competitive_winner_prediction(pred, winners)
    assert out is not None
    assert out.label_value is None
    assert out.outcome_quality == "rejected_invalid"


def test_resolve_predictions_routes_p2a_and_demand():
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    preds = [
        {
            "prediction_id": "d1",
            "target_name": "demand_30d",
            "entity_id": "E_DEMAND_ONLY",
            "as_of_at": as_of.isoformat(),
            "horizon": "30d",
            "score": 0.5,
            "coverage_ok": True,
        },
        {
            "prediction_id": "c1",
            "target_name": "competitive_winner_p2a",
            "procurement_id": "P1",
            "supplier_id": "S1",
            "entity_id": "E_P2A",
            "as_of_at": as_of.isoformat(),
            "score": 0.6,
        },
    ]
    # Contract only for P2A entity — demand entity has coverage_ok flag, no events
    contracts = [
        {
            "contrato_id": "P1",
            "fornecedor_cnpj": "S1",
            "orgao_cnpj": "E_P2A",
            "objeto_contrato": "Obra de reforma predial",
            "data_assinatura": as_of + timedelta(days=3),
            "valor_total": 1000,
        }
    ]
    outs = resolve_predictions(preds, contracts=contracts)
    by_id = {o.prediction_id: o for o in outs}
    assert "d1" in by_id
    assert by_id["d1"].label_value == 0.0  # coverage_ok, no event in window
    assert by_id["d1"].outcome_source == "coverage_confirmed_absence"
    assert "c1" in by_id
    assert by_id["c1"].label_value == 1.0


def test_build_winners_index():
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    contracts = [
        {
            "contrato_id": "X1",
            "fornecedor_cnpj": "W1",
            "orgao_cnpj": "O1",
            "objeto_contrato": "Construcao de escola",
            "data_publicacao": as_of,
            "valor_total": 10,
        }
    ]
    idx = build_winners_index(contracts)
    assert "X1" in idx
    assert idx["X1"]["winner_id"] == "W1"


def test_drift_ignores_rejected_invalid_negatives():
    predictions = []
    outcomes = []
    for i in range(40):
        pid = f"p{i}"
        predictions.append(
            {
                "prediction_id": pid,
                "target_name": "demand_30d",
                "score": 0.5,
                "probability": 0.5,
            }
        )
        # All rejected — must not count toward n_outcomes gate
        outcomes.append(
            {
                "prediction_id": pid,
                "label_value": None,
                "outcome_quality": "rejected_invalid_negative",
            }
        )
    report = evaluate_outcomes_drift(
        outcomes, predictions, target_name="demand_30d", min_outcomes=30
    )
    assert report.decision == "insufficient_data"
    assert report.n_outcomes == 0


def test_drift_suspends_on_forced_decision(tmp_path):
    predictions = []
    outcomes = []
    for i in range(40):
        pid = f"p{i}"
        label = 1.0 if i % 2 == 0 else 0.0
        predictions.append(
            {
                "prediction_id": pid,
                "target_name": "demand_30d",
                "score": 0.9,
                "probability": 0.9,
            }
        )
        outcomes.append(
            {
                "prediction_id": pid,
                "label_value": label,
                "outcome_quality": "ok",
            }
        )
    report = evaluate_outcomes_drift(
        outcomes, predictions, target_name="demand_30d", min_outcomes=30
    )
    assert report.n_outcomes >= 30

    reg = ClaimRegistry(path=tmp_path / "claims.json")
    reg.set_state("PREDICTIVE_DEMAND_FORECAST_AVAILABLE", "IMPLEMENTED", force=True)
    reg.set_state(
        "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "HISTORICAL_BACKTEST_PROVEN",
        force=True,
    )
    report.decision = "suspend_drift"
    report.reasons = ["test_force"]
    action = apply_drift_to_claims(report, registry=reg)
    assert action.get("applied") is True
    assert reg.get("PREDICTIVE_DEMAND_FORECAST_AVAILABLE").state == "SUSPENDED_DRIFT"


def test_weekly_predictive_section_honest():
    section = build_weekly_predictive_section()
    assert section["section"] == "predictive_intelligence"
    assert "claims" in section
    assert section["win_probability"]["included"] is False or section["claims"][
        "extra_win"
    ]["prediction_allowed"] is True
    assert section["claims"]["fully_proven"]["state"] != "PRODUCTION_AVAILABLE"
    # No SHADOW/PRODUCTION without evidence path
    for key in ("demand", "competitive_p2a", "winning_discount"):
        st = section["claims"][key]["state"]
        assert st not in {"PRODUCTION_AVAILABLE"}


def test_default_link_status_model_only_vs_commercial():
    from scripts.predictive.outcomes import (
        LINK_STATUS_NOT_APPLICABLE,
        LINK_STATUS_UNLINKED_LEGACY,
        default_link_status_for_source,
    )

    assert default_link_status_for_source("observed_aec_event") == LINK_STATUS_NOT_APPLICABLE
    assert default_link_status_for_source("coverage_confirmed_absence") == LINK_STATUS_NOT_APPLICABLE
    assert default_link_status_for_source("observed_winner") == LINK_STATUS_UNLINKED_LEGACY


def test_persist_outcomes_records_link_status(tmp_path):
    from scripts.predictive.outcomes import (
        LINK_STATUS_NOT_APPLICABLE,
        LINK_STATUS_UNLINKED_LEGACY,
        ResolvedOutcome,
        persist_outcomes,
    )

    ledger = tmp_path / "outcomes.jsonl"
    outcomes = [
        ResolvedOutcome(
            outcome_id="out_model",
            prediction_id="pred_model",
            observed_at="2024-01-15T00:00:00+00:00",
            label_value=1.0,
            outcome_source="observed_aec_event",
            outcome_quality="ok",
            error_abs=0.1,
            brier_component=0.01,
        ),
        ResolvedOutcome(
            outcome_id="out_win",
            prediction_id="pred_win",
            observed_at="2024-01-15T00:00:00+00:00",
            label_value=1.0,
            outcome_source="observed_winner",
            outcome_quality="ok",
            error_abs=0.0,
            brier_component=0.0,
            metadata={"procurement_id": "PROC-1"},
        ),
    ]
    result = persist_outcomes(outcomes, ledger_path=ledger, dsn=None)
    assert result["written"] == 2
    lines = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    by_pred = {r["prediction_id"]: r for r in lines}
    assert by_pred["pred_model"]["link_status"] == LINK_STATUS_NOT_APPLICABLE
    assert by_pred["pred_win"]["link_status"] == LINK_STATUS_UNLINKED_LEGACY
    assert by_pred["pred_win"].get("dm_outcome_event_id") in (None, "")


def test_migration_069_declares_dm_outcome_link():
    sql = (Path(__file__).resolve().parents[2] / "db/migrations/069_predictive_intelligence.sql").read_text(
        encoding="utf-8"
    )
    assert "dm_outcome_event_id" in sql
    assert "LINKED_DM" in sql
    assert "UNLINKED_LEGACY" in sql
    assert "fk_predictive_outcomes_dm_outcome" in sql
    assert "dm_outcome_events" in sql
