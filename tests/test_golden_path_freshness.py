"""DoD §12.1 — golden path executes freshness gate (not mere function presence)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import (
    FreshnessRecord,
    assert_freshness_gate_executed,
    run_freshness_gate,
)


def test_help_documents_execute_freshness_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-freshness-only" in (r.stdout + r.stderr)


def test_assert_freshness_requires_structure() -> None:
    ok, d = assert_freshness_gate_executed(None)
    assert ok is False

    ok, d = assert_freshness_gate_executed(FreshnessRecord(status="skipped"))
    assert ok is False

    ok, d = assert_freshness_gate_executed(
        FreshnessRecord(status="fail", details={"overall": {"failing_sources": ["contracts"]}})
    )
    assert ok is True
    assert d["status"] == "fail"
    assert "contracts" in d["failing_sources"]

    ok, d = assert_freshness_gate_executed(
        FreshnessRecord(
            status="pass",
            details={"critical_sources": [{"source": "pncp"}], "overall": {"failing_sources": []}},
        )
    )
    assert ok is True


def test_run_freshness_gate_invokes_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prove subprocess to freshness_gate.py, not just import of helper."""
    import scripts.golden_path as gp

    calls: list[list[str]] = []
    out_dir = tmp_path / "readiness"
    out_dir.mkdir()
    gate_json = out_dir / "freshness-gate.json"
    gate_json.write_text(
        json.dumps(
            {
                "overall": {"all_critical_sources_fresh": False, "failing_sources": ["contracts"]},
                "critical_sources": [{"source": "pncp", "freshness_status": "fresh"}],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))

        class R:
            returncode = 2
            stdout = ""
            stderr = "stale"

        return R()

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    monkeypatch.setattr(gp, "_OUTPUT_DIR", tmp_path)
    rec = run_freshness_gate("postgresql://test@localhost/db")
    assert calls, "freshness_gate.py must be invoked"
    assert any("freshness_gate.py" in str(c) for c in calls[0])
    assert rec.status == "fail"
    ok, details = assert_freshness_gate_executed(rec)
    assert ok is True
    assert "contracts" in details["failing_sources"]
