"""Golden path live steps: coverage + snapshot + freshness source filter."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from scripts.freshness_gate import CRITICAL_SOURCES, _selected_critical_sources
from scripts.golden_path import run_coverage_calculation, run_snapshot_reconciliation


def test_freshness_sources_env_filter(monkeypatch) -> None:
    monkeypatch.setenv("FRESHNESS_SOURCES", "pncp")
    selected = _selected_critical_sources()
    assert all(s.source_name == "pncp" for s in selected)
    assert len(selected) == 1
    monkeypatch.delenv("FRESHNESS_SOURCES", raising=False)
    assert len(_selected_critical_sources()) == len(CRITICAL_SOURCES)


def test_coverage_step_records_result(tmp_path, monkeypatch) -> None:
    # offline path still produces a StepRecord
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    step = run_coverage_calculation(os.environ["LOCAL_DATALAKE_DSN"])
    assert step.step == "coverage_calculation"
    assert step.status in {"pass", "fail"}
    assert step.duration_ms >= 0


def test_snapshot_step_handles_missing_tables() -> None:
    # With broken DSN, returns fail StepRecord without raising
    step = run_snapshot_reconciliation("postgresql://nope:nope@127.0.0.1:1/none")
    assert step.step == "snapshot_reconciliation"
    assert step.status == "fail"
