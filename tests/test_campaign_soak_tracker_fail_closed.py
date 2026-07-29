"""Fail-closed soak tracker — no false green, UTC days, coverage gates."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.ops import campaign_soak_tracker as soak


def _base_ok_obs(**overrides: object) -> dict:
    obs = {
        "failed_critical_units": 0,
        "contracts_timer": "active",
        "contracts_timer_enabled": "enabled",
        "last_contracts_result": "success",
        "last_contracts_exec": "0",
        "run_id": "contracts-90d-abc",
        "contracts_freshness_hours": 12.0,
        "contracts_coverage": 0.97,
        "editais_pncp_timer": "active",
        "editais_pncp_timer_enabled": "enabled",
        "editais_ciga_timer": "active",
        "editais_ciga_timer_enabled": "enabled",
        "open_tenders_freshness_hours": 6.0,
        "open_tenders_coverage": 0.96,
        "automatic_execution": True,
    }
    obs.update(overrides)
    return obs


def test_health_ok_requires_full_matrix() -> None:
    ok, reasons = soak._compute_health_ok(_base_ok_obs())
    assert ok is True
    assert reasons == []


def test_health_false_when_timer_failed_or_no_run_id() -> None:
    obs = _base_ok_obs(
        failed_critical_units=1,
        contracts_timer="inactive",
        contracts_timer_enabled="disabled",
        last_contracts_result="exit-code",
        last_contracts_exec="1",
        run_id=None,
        contracts_freshness_hours=None,
        contracts_coverage=None,
        open_tenders_coverage=None,
        open_tenders_freshness_hours=None,
        editais_pncp_timer="inactive",
        editais_pncp_timer_enabled="disabled",
        editais_ciga_timer="inactive",
        editais_ciga_timer_enabled="disabled",
    )
    ok, reasons = soak._compute_health_ok(obs)
    assert ok is False
    assert "failed_critical_units" in reasons
    assert "missing_run_id" in reasons
    assert "missing_contracts_freshness" in reasons
    assert "missing_contracts_coverage" in reasons
    assert "missing_open_tenders_coverage" in reasons
    assert "missing_open_tenders_freshness" in reasons


def test_manual_execution_not_health_ok() -> None:
    ok, reasons = soak._compute_health_ok(_base_ok_obs(automatic_execution=False))
    assert ok is False
    assert "manual_execution_not_automation" in reasons


def test_default_automatic_execution_is_false_without_systemd(monkeypatch) -> None:
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    monkeypatch.delenv("SOAK_AUTOMATIC", raising=False)
    assert soak._detect_automatic_execution() is False


def test_automatic_from_invocation_id(monkeypatch) -> None:
    monkeypatch.setenv("INVOCATION_ID", "abc-123")
    assert soak._detect_automatic_execution() is True


def test_coverage_below_95_fails_health() -> None:
    ok, reasons = soak._compute_health_ok(
        _base_ok_obs(contracts_coverage=0.90, open_tenders_coverage=0.94)
    )
    assert ok is False
    assert any("contracts_coverage_below_95" in r for r in reasons)
    assert any("open_tenders_coverage_below_95" in r for r in reasons)


def test_open_tenders_stale_fails_health() -> None:
    ok, reasons = soak._compute_health_ok(
        _base_ok_obs(open_tenders_freshness_hours=48.0)
    )
    assert ok is False
    assert any("open_tenders_stale" in r for r in reasons)


def test_editais_timer_family_required() -> None:
    ok, reasons = soak._compute_health_ok(
        _base_ok_obs(
            editais_pncp_timer="inactive",
            editais_ciga_timer_enabled="disabled",
        )
    )
    assert ok is False
    assert "editais_pncp_timer_not_active" in reasons
    assert "editais_ciga_timer_not_enabled" in reasons


def test_stale_contracts_freshness_fails_health() -> None:
    ok, reasons = soak._compute_health_ok(_base_ok_obs(contracts_freshness_hours=200.0))
    assert ok is False
    assert any("contracts_stale" in r for r in reasons)


def test_observe_cli_defaults_not_automatic(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(soak, "_ROOT", tmp_path)
    monkeypatch.setattr(soak, "_is_vps_host", lambda: False)
    monkeypatch.setattr(soak, "_ssh", lambda cmd: (0, ""))
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    monkeypatch.delenv("SOAK_AUTOMATIC", raising=False)

    dual = {
        "dual_gate_status": "PASS",
        "pipeline_success": True,
        "scope_complete": True,
        "capabilities": {
            "open_tenders": {
                "coverage_pct": 100.0,
                "covered_numerator": 1093,
                "applicable_denominator": 1093,
                "gate_status": "PASS",
            },
            "historical_contracts": {
                "coverage_pct": 100.0,
                "covered_numerator": 1093,
                "applicable_denominator": 1093,
                "gate_status": "PASS",
            },
        },
    }
    dual_path = (
        tmp_path
        / "output"
        / "coverage"
        / "dual-campaign-orrc-01"
        / "dual-capability-coverage-summary.json"
    )
    dual_path.parent.mkdir(parents=True)
    dual_path.write_text(json.dumps(dual), encoding="utf-8")

    measure_out = (
        "failed_units=0\n"
        "failed_critical=0\n"
        "health_timer=active\n"
        "contracts_timer=active\n"
        "contracts_timer_enabled=enabled\n"
        "last_contracts_result=success\n"
        "last_contracts_exec=0\n"
        "editais_pncp_timer=active\n"
        "editais_pncp_timer_enabled=enabled\n"
        "editais_ciga_timer=active\n"
        "editais_ciga_timer_enabled=enabled\n"
        "host=testhost\n"
        "deployed_sha=abc\n"
        "contracts_count=10\n"
        "contracts_ingest_age_hours=5.0\n"
        "editais_obs_age_hours=2.0\n"
        "contracts_run_id=run-xyz\n"
    )
    monkeypatch.setattr(soak, "_measure_runtime", lambda: (0, measure_out))

    rollup = soak.observe(dsn=None, campaign="TEST-SOAK", automatic=None)
    assert rollup["calendar"] == "UTC"
    assert rollup["complete"] is False
    assert "soak_epoch_started_at" in rollup
    day = datetime.now(UTC).date().isoformat()
    day_file = tmp_path / "artifacts" / "campaigns" / "TEST-SOAK" / "soak" / f"{day}.json"
    doc = json.loads(day_file.read_text(encoding="utf-8"))
    obs0 = doc["observations"][0]
    assert obs0["automatic_execution"] is False
    assert obs0["health_ok"] is False
    assert "manual_execution_not_automation" in obs0["health_fail_reasons"]
    # coverage was loaded from dual summary
    assert obs0["contracts_coverage"] == 1.0
    assert obs0["open_tenders_coverage"] == 1.0


def test_observe_automatic_green_when_all_gates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(soak, "_ROOT", tmp_path)
    monkeypatch.setattr(soak, "_is_vps_host", lambda: False)
    monkeypatch.setattr(soak, "_ssh", lambda cmd: (0, ""))
    dual = {
        "dual_gate_status": "PASS",
        "capabilities": {
            "open_tenders": {"coverage_pct": 100.0, "gate_status": "PASS"},
            "historical_contracts": {"coverage_pct": 100.0, "gate_status": "PASS"},
        },
    }
    dual_path = (
        tmp_path
        / "output"
        / "coverage"
        / "dual-campaign-orrc-01"
        / "dual-capability-coverage-summary.json"
    )
    dual_path.parent.mkdir(parents=True)
    dual_path.write_text(json.dumps(dual), encoding="utf-8")
    measure_out = (
        "failed_units=0\nfailed_critical=0\n"
        "contracts_timer=active\ncontracts_timer_enabled=enabled\n"
        "last_contracts_result=success\nlast_contracts_exec=0\n"
        "editais_pncp_timer=active\neditais_pncp_timer_enabled=enabled\n"
        "editais_ciga_timer=active\neditais_ciga_timer_enabled=enabled\n"
        "host=h\ndeployed_sha=sha\n"
        "contracts_ingest_age_hours=1.0\neditais_obs_age_hours=1.0\n"
        "contracts_run_id=run1\n"
    )
    monkeypatch.setattr(soak, "_measure_runtime", lambda: (0, measure_out))
    rollup = soak.observe(dsn=None, campaign="TEST-SOAK2", automatic=True)
    day = datetime.now(UTC).date().isoformat()
    day_file = (
        tmp_path / "artifacts" / "campaigns" / "TEST-SOAK2" / "soak" / f"{day}.json"
    )
    doc = json.loads(day_file.read_text(encoding="utf-8"))
    assert doc["observations"][0]["health_ok"] is True
    assert doc["rollup"]["health_ok"] is True
    assert rollup["complete"] is False  # only 1 day
