"""Fail-closed soak tracker — no false green, UTC days, no doc-date freshness."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.ops import campaign_soak_tracker as soak


def test_health_ok_requires_success_and_run_id() -> None:
    obs = {
        "failed_critical_units": 0,
        "contracts_timer": "active",
        "contracts_timer_enabled": "enabled",
        "last_contracts_result": "success",
        "last_contracts_exec": "0",
        "run_id": "contracts-90d-abc",
        "contracts_freshness_hours": 12.0,
        "automatic_execution": True,
    }
    ok, reasons = soak._compute_health_ok(obs)
    assert ok is True
    assert reasons == []


def test_health_false_when_timer_failed_or_no_run_id() -> None:
    obs = {
        "failed_critical_units": 1,
        "contracts_timer": "inactive",
        "contracts_timer_enabled": "disabled",
        "last_contracts_result": "exit-code",
        "last_contracts_exec": "1",
        "run_id": None,
        "contracts_freshness_hours": None,
        "automatic_execution": True,
    }
    ok, reasons = soak._compute_health_ok(obs)
    assert ok is False
    assert "failed_critical_units" in reasons
    assert "missing_run_id" in reasons
    assert "missing_contracts_freshness" in reasons


def test_manual_execution_not_health_ok() -> None:
    obs = {
        "failed_critical_units": 0,
        "contracts_timer": "active",
        "contracts_timer_enabled": "enabled",
        "last_contracts_result": "success",
        "last_contracts_exec": "0",
        "run_id": "r1",
        "contracts_freshness_hours": 1.0,
        "automatic_execution": False,
    }
    ok, reasons = soak._compute_health_ok(obs)
    assert ok is False
    assert "manual_execution_not_automation" in reasons


def test_observe_uses_utc_and_does_not_mark_complete_without_7_days(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(soak, "_ROOT", tmp_path)
    monkeypatch.setattr(soak, "_is_vps_host", lambda: True)

    measure_out = (
        "failed_units=0\n"
        "failed_critical=0\n"
        "health_timer=active\n"
        "contracts_timer=active\n"
        "contracts_timer_enabled=enabled\n"
        "last_contracts_result=success\n"
        "last_contracts_exec=0\n"
        "host=testhost\n"
        "deployed_sha=abc\n"
        "contracts_count=10\n"
        "contracts_ingest_age_hours=5.0\n"
        "contracts_run_id=run-xyz\n"
    )
    monkeypatch.setattr(soak, "_measure_runtime", lambda: (0, measure_out))
    # Avoid writing under /var/lib
    monkeypatch.setattr(soak, "_is_vps_host", lambda: False)
    monkeypatch.setattr(soak, "_ssh", lambda cmd: (0, ""))

    rollup = soak.observe(dsn=None, campaign="TEST-SOAK")
    assert rollup["calendar"] == "UTC"
    assert rollup["complete"] is False
    day = datetime.now(UTC).date().isoformat()
    day_file = tmp_path / "artifacts" / "campaigns" / "TEST-SOAK" / "soak" / f"{day}.json"
    assert day_file.is_file()
    doc = json.loads(day_file.read_text(encoding="utf-8"))
    assert doc["day_utc"] == day
    assert doc["observations"][0]["run_id"] == "run-xyz"
    assert doc["observations"][0]["freshness_basis"].startswith("ingestion_runs")
    assert "data_publicacao" not in doc["observations"][0].get("freshness_source", "")


def test_stale_freshness_fails_health() -> None:
    obs = {
        "failed_critical_units": 0,
        "contracts_timer": "active",
        "contracts_timer_enabled": "enabled",
        "last_contracts_result": "success",
        "last_contracts_exec": "0",
        "run_id": "r1",
        "contracts_freshness_hours": 200.0,
        "automatic_execution": True,
    }
    ok, reasons = soak._compute_health_ok(obs)
    assert ok is False
    assert any("contracts_stale" in r for r in reasons)
