"""DoD §23 — ops gate monitor: freshness, coverage, backup, migrations, timers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.ops.ops_gate_monitor import (
    collect_report,
    monitor_coverage_by_capability,
    monitor_delayed_timers,
    monitor_last_backup,
    monitor_migration_failures,
)


def test_report_includes_all_five_checks() -> None:
    rep = collect_report()
    names = {c["name"] for c in rep["checks"]}
    assert "freshness_by_source" in names
    assert "coverage_by_capability" in names
    assert "last_valid_backup" in names
    assert "migration_failures" in names
    assert "delayed_timers" in names
    assert rep["monitored"]["freshness_by_source"] is True
    assert rep["overall"] in {"ok", "warn", "crit", "degraded", "unknown"}


def test_last_backup_sees_local_proof_if_present() -> None:
    r = monitor_last_backup()
    assert r["name"] == "last_valid_backup"
    assert r["metrics"]["monitored"] is True
    # Workspace may have proof dumps from campaign
    assert r["status"] in {"ok", "warn", "unknown", "crit"}


def test_coverage_capability_monitored() -> None:
    r = monitor_coverage_by_capability()
    assert r["metrics"]["monitored"] is True
    assert r["status"] in {"ok", "configured", "unknown"}


def test_migration_and_timers_monitored() -> None:
    m = monitor_migration_failures()
    assert m["metrics"]["monitored"] is True
    t = monitor_delayed_timers()
    assert t["metrics"]["monitored"] is True
    # repo has timer units
    assert t["metrics"].get("timer_count", 0) >= 1


def test_cli_json() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.ops.ops_gate_monitor", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode in {0, 1, 2}, r.stderr
    body = json.loads(r.stdout)
    assert len(body["checks"]) == 5
    assert "forbidden" in body["claims"]
