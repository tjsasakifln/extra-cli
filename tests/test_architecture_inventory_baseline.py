"""Smoke tests for architecture baseline inventory (ARCH-RESET PR A)."""
from __future__ import annotations

from pathlib import Path

from scripts.architecture.inventory_baseline import build_baseline


def test_build_baseline_has_canonical_weekly_and_sha() -> None:
    root = Path(__file__).resolve().parents[1]
    baseline = build_baseline(root)
    assert baseline["main_sha"]
    assert baseline["main_short"]
    assert baseline["product_entrypoints"]["extra-weekly"]["class"] == "canonical"
    assert baseline["metrics"]["py_scripts_files"] >= 1
    assert baseline["metrics"]["orchestrators_listed"] >= 1
    assert baseline["claims"]["LOCAL_READY"] == "NOT_CLAIMED"
    assert baseline["claims"]["operational_coverage_95"] == "NOT_CLAIMED"
