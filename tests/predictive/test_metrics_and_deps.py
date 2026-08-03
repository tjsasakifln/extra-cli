"""Behavioral tests for metrics, dependency contract, and claim honesty edges."""

from __future__ import annotations

import importlib
import math
from pathlib import Path

import pytest

from scripts.predictive.metrics import (
    MIN_BSS,
    brier_score,
    brier_skill_score,
    classification_report,
    evaluate_classification_gates,
    expected_calibration_error,
    log_loss,
    precision_recall_at_threshold,
)


ROOT = Path(__file__).resolve().parents[2]


def test_numpy_and_sklearn_declared_in_requirements():
    """Predictive stack declared in requirements-predictive.txt and pulled by requirements.txt."""
    pred_req = ROOT / "requirements-predictive.txt"
    assert pred_req.is_file(), "requirements-predictive.txt must exist"
    pred_text = pred_req.read_text(encoding="utf-8")
    pred_lines = [
        ln.strip()
        for ln in pred_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    joined = "\n".join(pred_lines).lower()
    assert "numpy" in joined, "numpy must be in requirements-predictive.txt"
    assert "scikit-learn" in joined or "sklearn" in joined
    root_req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "requirements-predictive" in root_req or "numpy" in root_req.lower()

def test_metrics_module_imports_cleanly():
    mod = importlib.import_module("scripts.predictive.metrics")
    assert callable(mod.brier_score)
    assert callable(mod.brier_skill_score)
    assert callable(mod.expected_calibration_error)


def test_models_module_imports_sklearn_stack():
    mod = importlib.import_module("scripts.predictive.models")
    assert hasattr(mod, "fit_logistic")
    # real train path uses sklearn
    fitted = mod.fit_logistic([[0.0], [1.0], [0.0], [1.0]], [0.0, 1.0, 0.0, 1.0], ["f"])
    proba = list(fitted.predict_proba([[0.0], [1.0]]))
    assert len(proba) == 2
    assert 0.0 <= proba[0] <= 1.0
    assert 0.0 <= proba[1] <= 1.0


def test_brier_score_perfect_and_worst():
    y = [0.0, 1.0, 0.0, 1.0]
    assert brier_score(y, [0.0, 1.0, 0.0, 1.0]) == pytest.approx(0.0, abs=1e-12)
    worst = brier_score(y, [1.0, 0.0, 1.0, 0.0])
    assert worst == pytest.approx(1.0, abs=1e-6)


def test_brier_skill_score_vs_prevalence():
    y = [0.0, 0.0, 0.0, 1.0]
    # constant prevalence baseline
    base = [0.25, 0.25, 0.25, 0.25]
    perfect = [0.0, 0.0, 0.0, 1.0]
    bss = brier_skill_score(y, perfect, base)
    assert bss == pytest.approx(1.0, abs=1e-9)
    zero = brier_skill_score(y, base, base)
    assert zero == pytest.approx(0.0, abs=1e-9)


def test_brier_skill_score_zero_baseline_denominator():
    y = [0.0, 1.0]
    # baseline perfect → bs_ref ~ 0
    assert brier_skill_score(y, [0.0, 1.0], [0.0, 1.0]) == 0.0
    assert brier_skill_score(y, [1.0, 0.0], [0.0, 1.0]) == -1.0


def test_expected_calibration_error_perfect_and_empty():
    y = [0.0, 0.0, 1.0, 1.0]
    p = [0.0, 0.0, 1.0, 1.0]
    assert expected_calibration_error(y, p, n_bins=4) == pytest.approx(0.0, abs=1e-9)
    assert expected_calibration_error([], [], n_bins=10) == 1.0


def test_classification_report_empty_population():
    rep = classification_report([], [])
    assert rep["n"] == 0
    assert rep["n_positives"] == 0
    assert rep["prevalence"] == 0.0


def test_classification_report_no_positives():
    y = [0.0, 0.0, 0.0, 0.0]
    p = [0.1, 0.2, 0.3, 0.4]
    rep = classification_report(y, p)
    assert rep["n_positives"] == 0
    assert math.isnan(rep["roc_auc"]) or rep["roc_auc"] != rep["roc_auc"]


def test_classification_report_no_negatives():
    y = [1.0, 1.0, 1.0, 1.0]
    p = [0.6, 0.7, 0.8, 0.9]
    rep = classification_report(y, p)
    assert rep["n_positives"] == 4
    assert math.isnan(rep["roc_auc"]) or rep["roc_auc"] != rep["roc_auc"]


def test_log_loss_finite_for_clipped_extremes():
    y = [0.0, 1.0]
    # near-certain wrong and right predictions must not explode
    val = log_loss(y, [1e-20, 1.0 - 1e-20])
    assert math.isfinite(val)
    assert val >= 0.0


def test_precision_recall_zero_division_safe():
    y = [0.0, 0.0]
    p = [0.1, 0.2]
    out = precision_recall_at_threshold(y, p, threshold=0.5)
    assert out["precision"] == 0.0
    assert out["recall"] == 0.0
    assert out["f1"] == 0.0


def test_gates_do_not_pass_below_bss_threshold():
    """Thresholds are fixed; a strong-looking but sub-BSS result must fail."""
    metrics = {
        "n": 5000,
        "n_positives": 500,
        "brier_skill_score": MIN_BSS - 0.001,
        "log_loss": 0.4,
        "log_loss_baseline": 0.5,
        "ece": 0.01,
        "lift_top10": 2.0,
    }
    gate = evaluate_classification_gates(metrics)
    assert gate["passed"] is False
    assert any("BSS" in r for r in gate["reasons"])


def test_gates_never_auto_promote_on_table_existence_alone():
    """Mere presence of volume without quality stays blocked or failed."""
    metrics = {
        "n": 50,
        "n_positives": 5,
        "brier_skill_score": 0.5,
        "log_loss": 0.1,
        "log_loss_baseline": 0.5,
        "ece": 0.01,
        "lift_top10": 3.0,
    }
    gate = evaluate_classification_gates(metrics)
    assert gate["passed"] is False
    assert gate["data_blocked"] is True


def test_no_migration_collision_with_decision_memory():
    mig_dir = ROOT / "db" / "migrations"
    predictive = list(mig_dir.glob("*predictive_intelligence.sql"))
    decision = list(mig_dir.glob("*decision_outcome_memory.sql"))
    assert len(predictive) == 1
    pred_num = predictive[0].name.split("_", 1)[0]
    assert pred_num == "069", f"predictive must be 069, got {predictive[0].name}"
    # After consolidation, Decision Memory 068 coexists on main
    if decision:
        dec_num = decision[0].name.split("_", 1)[0]
        assert dec_num == "068", f"decision memory must be 068, got {decision[0].name}"
        assert dec_num != pred_num
    same_num = list(mig_dir.glob(f"{pred_num}_*.sql"))
    assert len(same_num) == 1

def test_heuristic_bid_score_not_serialized_as_probability():
    from scripts.lib.bid_simulator import METHOD_UNVALIDATED_HEURISTIC, simulate_bid

    result = simulate_bid({"valor_estimado": 100_000.0, "objeto": "obra de engenharia"})
    assert result.method == METHOD_UNVALIDATED_HEURISTIC
    assert result.prediction_claim_allowed is False
    assert hasattr(result, "heuristic_scenario_score")
    export = result.to_export_dict()
    assert export["method"] == METHOD_UNVALIDATED_HEURISTIC
    assert export["prediction_claim_allowed"] is False
    assert "heuristic_scenario_score" in export
    assert "p_vitoria_pct" not in export
    assert "probabilidade_vitoria" not in export
    assert export.get("is_calibrated_probability") is False
    assert export.get("is_optimal_bid") is False
    # limitations may mention forbidden vocabulary as a non-claim; score keys must not
    assert not any(k.startswith("p_") and "vitoria" in k for k in export)
