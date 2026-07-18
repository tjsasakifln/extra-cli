"""Capability inventory for DoD §2.1 objectives."""
from __future__ import annotations

from scripts.ops.capability_inventory import inventory


def test_inventory_has_objectives() -> None:
    data = inventory()
    assert data["ok"] is True
    assert data["counts"]["total"] >= 6
    assert data["counts"]["not_ready"] >= 1  # monitoring incomplete


def test_no_false_ready_while_coverage_gap() -> None:
    data = inventory()
    # At least one objective must remain NOT_READY while coverage is incomplete
    assert any(o["status"] == "NOT_READY" for o in data["objectives"])
