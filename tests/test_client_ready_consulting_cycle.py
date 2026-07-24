"""Tests for CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 integrated entry point.

Drives real shipped functions — no reimplementation of isolation/terminal logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.client_ready_consulting_cycle import (
    CAMPAIGN_ID,
    decide_terminal,
    isolation_guard,
    main,
)

ROOT = Path(__file__).resolve().parents[1]


def test_isolation_rejects_ec_prod() -> None:
    with pytest.raises(SystemExit) as ei:
        isolation_guard("postgresql://u:p@ec-prod:5432/extra_prod")
    payload = json.loads(str(ei.value))
    assert payload["status"] == "FAIL"
    assert payload["isolation"]["ok"] is False


def test_isolation_rejects_port_5432() -> None:
    with pytest.raises(SystemExit):
        isolation_guard("postgresql://test:test@127.0.0.1:5432/anything")


def test_isolation_rejects_opt_path_in_dsn() -> None:
    with pytest.raises(SystemExit):
        isolation_guard("postgresql://test:test@127.0.0.1:5436//opt/extra-consultoria")


def test_isolation_accepts_campaign_local_dsn() -> None:
    r = isolation_guard("postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc")
    assert r["ok"] is True
    assert r["production_touched"] is False
    assert r["soak_touched"] is False
    assert r["production_touched"] is not None
    assert r["soak_touched"] is not None


def test_decide_terminal_blocked_without_human_accept() -> None:
    isolation = {"ok": True, "production_touched": False, "soak_touched": False}
    migrations = {"idempotent": True}
    snapshot = {"ok": True}
    pack = {"reconcile": {"status": "PASS"}}
    linkage = {"status": "completed"}
    monthly = {"mode": "LIVE_ISOLATED", "live_recurrence": True}
    acceptance = {"status": "PENDING_HUMAN"}
    term, blockers = decide_terminal(
        isolation=isolation,
        migrations=migrations,
        snapshot=snapshot,
        pack=pack,
        linkage=linkage,
        monthly=monthly,
        acceptance=acceptance,
        failures=[],
    )
    assert term == "BLOCKED"
    assert any("PENDING_HUMAN" in b for b in blockers)


def test_decide_terminal_fail_on_reconcile() -> None:
    term, _ = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "FAIL"}},
        linkage={"status": "completed"},
        monthly={"mode": "LIVE_ISOLATED"},
        acceptance={"status": "ACCEPTED", "accepted_by": "Tiago"},
        failures=[],
    )
    assert term == "FAIL"


def test_decide_terminal_pass_only_with_accept_and_live_recurrence() -> None:
    term, blockers = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack={"reconcile": {"status": "PASS"}},
        linkage={"status": "completed"},
        monthly={"mode": "LIVE_ISOLATED", "live_recurrence": True},
        acceptance={"status": "ACCEPTED", "accepted_by": "Tiago Sasaki"},
        failures=[],
    )
    assert term == "PASS"
    assert blockers == []


def test_cli_guard_exit_codes() -> None:
    assert main(["guard", "--dsn", "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc"]) == 0
    assert main(["guard", "--dsn", "postgresql://u:p@ec-prod/db"]) == 3


def test_makefile_targets_registered() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    for t in (
        "client-ready-consulting-cycle",
        "campaign-gate-client-ready-recurring-consulting-cycle",
        "release-candidate-client-ready-recurring-consulting-cycle",
        "verify-client-ready-recurring-consulting-cycle-isolated",
        "dod-audit-client-ready-recurring-consulting-cycle",
    ):
        assert t in mk


def test_orchestrator_module_importable() -> None:
    assert CAMPAIGN_ID == "CLIENT-READY-RECURRING-CONSULTING-CYCLE-01"
    assert (ROOT / "scripts/ops/client_ready_consulting_cycle.py").is_file()
    assert (ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql").is_file()
    assert (ROOT / "db/migrations/061_canonical_entity_linkage.sql").is_file()


def test_terminal_status_vocabulary_only_three() -> None:
    """Global status must be exactly PASS|BLOCKED|FAIL — no alternate terminals."""
    src = (ROOT / "scripts/ops/client_ready_consulting_cycle.py").read_text(encoding="utf-8")
    for banned in (
        "TECHNICAL_PASS",
        "READY_FOR_REVIEW",
        "MOSTLY_PASS",
        "CONDITIONAL_PASS",
        "BLOCKED_HUMAN",
    ):
        # may appear in comments/docs of other campaigns; orchestrator decide path must not return them
        assert f'return "{banned}"' not in src
