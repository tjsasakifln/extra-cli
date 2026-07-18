"""DoD §23 alert stack — destination, context, dedup, webhook fail, fallback."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.ops.alert_pipeline import (
    AlertEvent,
    destinations_configured,
    dispatch_alert,
    should_suppress,
    status_report,
    probe_webhook_detectable,
)


def test_status_capabilities() -> None:
    s = status_report()
    caps = s["capabilities"]
    assert caps["destination_configured"] is True
    assert caps["storm_control"] is True
    assert caps["rate_limit_or_dedup"] is True
    assert caps["webhook_failure_detectable"] is True
    assert caps["fallback_persistent"] is True
    assert caps["actionable_context"] is True


def test_actionable_context_on_event() -> None:
    ev = AlertEvent(
        title="disk full",
        body="disk 95%",
        next_action="Free space under /var/lib/postgresql",
        run_id="run-1",
        entity_id="host",
    )
    txt = ev.with_context()
    assert "next_action:" in txt
    assert "run_id: run-1" in txt
    assert "fingerprint:" in txt


def test_dedup_and_fallback(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    state = tmp_path / "state.json"
    ev = AlertEvent(
        title="same",
        body="x",
        severity="warning",
        source="t",
        next_action="check",
    )
    r1 = dispatch_alert(ev, dry_run=True, ledger_path=ledger, state_path=state)
    assert r1["suppressed"] is False
    assert r1["fallback_ledger"]
    assert ledger.is_file()
    r2 = dispatch_alert(ev, dry_run=True, ledger_path=ledger, state_path=state)
    assert r2["suppressed"] is True
    suppress, reason = should_suppress(ev, state_path=state)
    assert suppress is True
    assert "dedup" in reason


def test_webhook_failure_detectable_dry() -> None:
    r = probe_webhook_detectable("https://example.invalid/hook", dry_run=True)
    assert r["detectable_failure"] is True
    assert r["success"] is True  # dry_run path


def test_cli_self_check() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.ops.alert_pipeline", "--self-check"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    body = json.loads(r.stdout)
    assert body["ok"] is True
    assert body["second_suppressed"] is True


def test_destinations_probe_does_not_require_secrets() -> None:
    d = destinations_configured()
    assert "any" in d
    assert "env_keys_present" in d
