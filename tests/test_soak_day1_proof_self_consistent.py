"""Structural gate: committed soak day-1 day_doc must satisfy shipped pure health.

Proof theater ban: the committed artifact must be a full observe() day document
(observations[] + rollup), not a hand-sliced latest summary. This test loads
that day_doc and re-runs ``_compute_health_ok`` on the winning observation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.campaign_soak_tracker import (
    REQUIRED_HEALTH_KEYS,
    _compute_health_ok,
)

_DAYDOC = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "campaigns"
    / "EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01"
    / "proofs"
    / "soak-day1-daydoc.json"
)


def test_required_health_keys_nonempty() -> None:
    assert len(REQUIRED_HEALTH_KEYS) >= 10
    assert "automatic_execution" in REQUIRED_HEALTH_KEYS
    assert "contracts_coverage" in REQUIRED_HEALTH_KEYS
    assert "open_tenders_coverage" in REQUIRED_HEALTH_KEYS


def test_soak_day1_proof_is_self_consistent() -> None:
    """Committed day_doc is full observe output and pure function returns green."""
    if not _DAYDOC.is_file():
        pytest.fail(
            f"Missing full day_doc proof at {_DAYDOC}. "
            "Capture via: python -m scripts.ops.campaign_soak_tracker --automatic "
            "then copy artifacts/.../soak/YYYY-MM-DD.json to proofs/soak-day1-daydoc.json"
        )

    doc = json.loads(_DAYDOC.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert "observations" in doc, "day_doc must have observations[] (full observe shape)"
    assert "rollup" in doc, "day_doc must have rollup (full observe shape)"
    # Ban hand-sliced "latest" theater
    assert "latest" not in doc or "observations" in doc
    assert isinstance(doc["observations"], list) and len(doc["observations"]) >= 1

    # Winning observation: latest with health_ok True, else last
    winning = None
    for obs in reversed(doc["observations"]):
        if obs.get("health_ok") is True:
            winning = obs
            break
    if winning is None:
        winning = doc["observations"][-1]

    missing = sorted(REQUIRED_HEALTH_KEYS - set(winning.keys()))
    assert missing == [], f"winning observation missing required keys: {missing}"

    ok, reasons = _compute_health_ok(winning)
    assert ok is True, (
        f"shipped _compute_health_ok returned False on committed day_doc: {reasons}"
    )
    assert reasons == []
    assert winning.get("health_ok") is True
    assert doc["rollup"].get("health_ok") is True


def test_hand_sliced_summary_fails_pure_function() -> None:
    """Regression: partial 'latest' summary without required keys is not green."""
    theater = {
        "health_ok": True,
        "automatic_execution": True,
        "run_id": "x",
        "contracts_freshness_hours": 1.0,
        "open_tenders_freshness_hours": 1.0,
        "contracts_coverage": 1.0,
        "open_tenders_coverage": 1.0,
        "health_fail_reasons": [],
        # deliberately omit contracts_timer, last_contracts_result, etc.
    }
    ok, reasons = _compute_health_ok(theater)
    assert ok is False
    assert any("missing_required_keys" in r for r in reasons)
