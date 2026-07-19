"""Live cycles must not use --skip-tests (BLOCKED_UNVERIFIED)."""
from __future__ import annotations

from argparse import Namespace

from scripts.cto.cli import EXIT_BLOCKED, _block_live_skip_tests, _run_cycle_from_decision
from scripts.cto.config import load_config
from scripts.cto.state_machine import StateMachine


def test_block_live_skip_tests_returns_exit_blocked(cto_repo, monkeypatch):
    monkeypatch.chdir(cto_repo)
    # Point repo_root to fixture if needed via paths — StateMachine uses root arg
    sm = StateMachine(cto_repo)
    report: dict = {"steps": [], "ok": False}
    args = Namespace(skip_tests=True, dry_run=False, mock=False)
    code = _block_live_skip_tests(args=args, sm=sm, report=report, cycle_id="cyc-skip")
    assert code == EXIT_BLOCKED
    assert report["outcome"] == "blocked_unverified"
    assert report["terminal_status"] == "BLOCKED"
    assert "BLOCKED_UNVERIFIED" in report["error"]
    assert sm.load().status == "BLOCKED"


def test_block_skip_tests_allowed_on_dry_run(cto_repo):
    sm = StateMachine(cto_repo)
    report: dict = {"steps": [], "ok": False}
    args = Namespace(skip_tests=True, dry_run=True, mock=False)
    code = _block_live_skip_tests(args=args, sm=sm, report=report)
    assert code is None


def test_run_cycle_live_skip_tests_never_accepts(sample_decision, cto_repo, monkeypatch):
    """Full cycle path with live --skip-tests must not ACCEPT or publish."""
    sm = StateMachine(cto_repo)
    cfg = load_config(cto_repo)
    sample_decision["cycle_id"] = "cyc-live-skip"
    args = Namespace(
        skip_tests=True,
        dry_run=False,
        mock=True,
        skip_publish=False,
        skip_push=False,
    )
    report: dict = {"steps": [], "ok": False, "operational_success": False}
    code = _run_cycle_from_decision(
        root=cto_repo,
        cfg=cfg,
        sm=sm,
        decision=sample_decision,
        args=args,
        report=report,
        start_phase="PREPARING",
    )
    assert code == EXIT_BLOCKED
    assert report.get("skip_tests_blocked") is True
    # No ACCEPT path
    assert report.get("review", {}).get("verdict") != "ACCEPT"
    assert "publication" not in report or not report.get("publication")
    # No execute step completed after block (blocked before execute)
    assert not any(s.get("step") == "publish" for s in report.get("steps") or [])
