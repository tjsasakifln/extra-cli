"""Tests for OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 structural gate."""

from __future__ import annotations

from pathlib import Path

from scripts.ops.campaign_open_tenders_gate import CAMPAIGN, run_gate
from scripts.ops.snapshot_integrity import measure_snapshot_integrity


ROOT = Path(__file__).resolve().parents[1]


def test_campaign_gate_passes_on_repo() -> None:
    report = run_gate(ROOT)
    fails = [c for c in report["checks"] if c["status"] == "FAIL"]
    assert report["ok"] is True, fails
    assert report["campaign_id"] == CAMPAIGN


def test_baseline_artifact_exists() -> None:
    p = ROOT / "artifacts" / "campaigns" / CAMPAIGN / "baseline.json"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01" in text
    assert "chosen_canonical_path" in text


def test_systemd_extra_weekly_units() -> None:
    svc = ROOT / "deploy" / "systemd" / "extra-weekly.service"
    tmr = ROOT / "deploy" / "systemd" / "extra-weekly.timer"
    assert svc.is_file()
    assert tmr.is_file()
    body = svc.read_text(encoding="utf-8")
    assert "scripts.ops.weekly_cycle" in body
    assert "Conflicts=" in body  # single-writer vs concurrent PNCP crawls
    assert "OnCalendar=" in tmr.read_text(encoding="utf-8")


def test_ciga_sla_aligned_to_dod_24h() -> None:
    import yaml

    policy = yaml.safe_load(
        (ROOT / "config" / "source_applicability.yaml").read_text(encoding="utf-8")
    )
    ciga = policy["sources"]["ciga_ckan"]
    assert int(ciga["sla_hours"]) <= 24


def test_snapshot_integrity_fail_closed_without_dsn_shape() -> None:
    """Module exposes measure API; empty/require_non_empty documented."""
    import inspect

    sig = inspect.signature(measure_snapshot_integrity)
    assert "require_non_empty" in sig.parameters
