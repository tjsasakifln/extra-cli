"""Migrations presence, CLI smoke, immutability SQL, facade entrypoints."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_migration_069_exists_and_has_required_tables():
    path = ROOT / "db" / "migrations" / "069_predictive_intelligence.sql"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    for table in (
        "predictive_dataset_runs",
        "predictive_training_examples",
        "predictive_models",
        "predictive_model_metrics",
        "predictive_model_artifacts",
        "predictive_predictions",
        "predictive_prediction_explanations",
        "predictive_outcomes",
        "predictive_drift_runs",
        "predictive_claim_states",
    ):
        assert table in text
    assert "predictive_predictions_immutability" in text
    assert "immutable" in text.lower()


def test_facade_claims_cli():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.predictive", "claims"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert "claims" in data
    assert "PREDICTIVE_DEMAND_FORECAST_AVAILABLE" in data["claims"]
    assert data["commercial_recommendation"] in {
        "CLAIM_FORBIDDEN",
        "PARTIAL_CLAIM_ALLOWED",
        "CLAIM_ALLOWED",
    }


def test_facade_predict_honest_block():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.predictive",
            "predict",
            "--target",
            "demand_30d",
            "--entity",
            "00000000000000",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["prediction_allowed"] is False
    assert data["claim_state"] != "PRODUCTION_AVAILABLE" or data["prediction_allowed"]


def test_profile_calibration_cli():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.predictive.profile_calibration",
            "--client",
            "extra_construtora",
            "blockers",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["personalization_allowed"] is False
    assert data["missing_critical"]


def test_workspace_predictive_status():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.workspace", "predictive-status", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert "claims" in data
    assert data["commercial_recommendation"] in {
        "CLAIM_FORBIDDEN",
        "PARTIAL_CLAIM_ALLOWED",
        "CLAIM_ALLOWED",
    }


def test_workspace_forecast_win_blocked():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.workspace",
            "forecast",
            "win",
            "OPP-1",
            "--client",
            "extra_construtora",
            "--json",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["prediction_allowed"] is False
    assert data.get("nomenclature_if_market_only") == "CALIBRATED_MARKET_WIN_LIKELIHOOD"


def test_approve_refuses_without_prospective():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.predictive", "approve", "--target", "demand_30d"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    data = json.loads(proc.stdout)
    assert data.get("approved") is False
