"""Headless Grok command must use dontAsk + strict sandbox, not always-approve."""
from __future__ import annotations

from scripts.cto.grok_executor import build_grok_command


def test_operational_cmd_uses_dontask_strict():
    cmd = build_grok_command(
        worktree="/tmp/wt",
        session_id="00000000-0000-0000-0000-000000000001",
        prompt="do work",
        max_turns=10,
        always_approve=False,
    )
    assert "--no-auto-update" in cmd
    assert "--sandbox" in cmd
    assert "strict" in cmd
    assert "--permission-mode" in cmd
    assert "dontAsk" in cmd
    assert "--always-approve" not in cmd
    assert "--yolo" not in cmd
    assert "bypassPermissions" not in cmd
    assert "--deny" in cmd
    assert "--allow" in cmd


def test_always_approve_not_injected_unless_bypass_mode():
    cmd = build_grok_command(
        worktree="/tmp/wt",
        session_id="00000000-0000-0000-0000-000000000002",
        prompt="probe",
        max_turns=3,
        always_approve=True,
        permission_mode="dontAsk",
    )
    assert "--always-approve" not in cmd
