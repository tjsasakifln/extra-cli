"""Tests for ARCH-RESET E/G/H/J spike runners (no production deps required beyond existing)."""
from __future__ import annotations

from pathlib import Path

from scripts.architecture.spike_eghj_benchmarks import (
    spike_e_dbt,
    spike_h_identity,
)


def test_spike_e_rejects_dbt_without_experiment() -> None:
    r = spike_e_dbt()
    assert r["decision"] == "REJECTED_WITHOUT_EXPERIMENT"
    assert r["experiment_run"] is False
    assert r["corpus_opportunities"] == 0
    assert r["production_dep_added"] is False
    assert r.get("honest") is True


def test_spike_h_deterministic_root_guard() -> None:
    r = spike_h_identity()
    assert r["decision"] == "REJECTED_SPIKE_FOR_NOW"
    assert r["deterministic_proof"]["rejects_conflicting_root"] is True
    assert r["production_dep_added"] is False


def test_spike_script_exists() -> None:
    p = Path("scripts/architecture/spike_eghj_benchmarks.py")
    assert p.is_file()
