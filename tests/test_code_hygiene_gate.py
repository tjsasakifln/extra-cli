"""Tests for DoD §27 code hygiene gate."""
from __future__ import annotations

from scripts.ops.code_hygiene_gate import run_gate, inventory_dry_run, check_metric_definitions


def test_run_gate_ok():
    r = run_gate()
    assert r["metric_definitions"]["ok"] is True
    assert r["todos"]["ok"] is True
    assert r["dry_run"]["ok"] is True
    assert r["destructive_safety"]["ok"] is True
    assert r["legacy_removal_plan"]["ok"] is True
    assert r["summary"]["ok"] is True


def test_metric_definitions_complete():
    m = check_metric_definitions()
    assert m["n_metrics"] >= 3
    assert m["all_required_fields"] is True


def test_dry_run_inventory():
    d = inventory_dry_run()
    assert d["missing_dry_run"] == []
