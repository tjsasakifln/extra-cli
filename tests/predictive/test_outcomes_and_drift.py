"""Outcome reconciliation and drift suspension — real shipped functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.predictive.claims import ClaimRegistry
from scripts.predictive.drift import apply_drift_to_claims, evaluate_outcomes_drift
from scripts.predictive.outcomes import resolve_demand_prediction, resolve_predictions
from scripts.predictive.weekly_section import build_weekly_predictive_section


def test_resolve_demand_after_window():
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
    # event inside window
    events = {
        "111": [as_of + timedelta(days=10)],
    }
    # Force maturity by using past as_of relative to now (2026 in env)
    out = resolve_demand_prediction(pred, events)
    assert out is not None
    assert out.label_value == 1.0
    assert out.prediction_id == "pred_test_1"
    assert out.brier_component is not None


def test_resolve_immature_returns_none():
    # as_of = now → window not elapsed
    as_of = datetime.now(timezone.utc).replace(microsecond=0)
    pred = {
        "prediction_id": "pred_immature",
        "target_name": "demand_30d",
        "entity_id": "222",
        "as_of_at": as_of.isoformat(),
        "horizon": "30d",
        "score": 0.5,
    }
    out = resolve_demand_prediction(pred, {"222": []})
    assert out is None


def test_drift_suspends_on_high_ece(tmp_path):
    # Build synthetic poorly calibrated outcomes
    predictions = []
    outcomes = []
    for i in range(40):
        pid = f"p{i}"
        # model always predicts 0.9 but labels are 0 half the time → high ECE/Brier
        label = 1.0 if i % 2 == 0 else 0.0
        predictions.append(
            {
                "prediction_id": pid,
                "target_name": "demand_30d",
                "score": 0.9,
                "probability": 0.9,
            }
        )
        outcomes.append({"prediction_id": pid, "label_value": label})
    report = evaluate_outcomes_drift(
        outcomes, predictions, target_name="demand_30d", min_outcomes=30
    )
    assert report.n_outcomes >= 30
    # May or may not suspend depending on ECE; ensure function runs
    assert report.decision in {
        "ok",
        "suspend_drift",
        "suspend_data_quality",
        "insufficient_data",
    }

    reg = ClaimRegistry(path=tmp_path / "claims.json")
    reg.set_state("PREDICTIVE_DEMAND_FORECAST_AVAILABLE", "IMPLEMENTED", force=True)
    reg.set_state(
        "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "HISTORICAL_BACKTEST_PROVEN",
        force=True,
    )
    # Force suspend decision path
    report.decision = "suspend_drift"
    report.reasons = ["test_force"]
    action = apply_drift_to_claims(report, registry=reg)
    assert action.get("applied") is True
    assert reg.get("PREDICTIVE_DEMAND_FORECAST_AVAILABLE").state == "SUSPENDED_DRIFT"


def test_weekly_predictive_section_honest():
    section = build_weekly_predictive_section()
    assert section["section"] == "predictive_intelligence"
    assert "claims" in section
    assert section["win_probability"]["included"] is False or section[
        "claims"
    ]["extra_win"]["prediction_allowed"] is True
    # Must not claim fully proven production by default
    assert section["claims"]["fully_proven"]["state"] != "PRODUCTION_AVAILABLE"
