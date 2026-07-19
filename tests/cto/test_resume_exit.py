"""Resume continues mid-cycle; exit codes distinguish terminal states."""
from __future__ import annotations

import json
from argparse import Namespace

from scripts.cto.cli import (
    EXIT_BLOCKED,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_WAITING_HUMAN,
    exit_code_for_status,
)
from scripts.cto.paths import cycles_dir, decision_path
from scripts.cto.state_machine import StateMachine


def test_exit_codes_not_generic_success():
    assert exit_code_for_status("WAITING_HUMAN") == EXIT_WAITING_HUMAN
    assert exit_code_for_status("BLOCKED") == EXIT_BLOCKED
    assert exit_code_for_status("FAILED") == EXIT_FAILED
    assert exit_code_for_status("DONE") == EXIT_OK
    assert EXIT_WAITING_HUMAN != EXIT_OK
    assert EXIT_BLOCKED != EXIT_OK


def test_resume_from_executing(cto_repo, sample_decision, monkeypatch):
    root = cto_repo
    # point repo_root to cto_repo
    monkeypatch.setattr("scripts.cto.cli.repo_root", lambda: root)
    monkeypatch.setattr("scripts.cto.paths.repo_root", lambda: root)
    monkeypatch.setattr("scripts.cto.state_machine.repo_root", lambda: root, raising=False)

    from scripts.cto import paths as paths_mod

    monkeypatch.setattr(paths_mod, "repo_root", lambda: root)

    cycle_id = "cyc-resume-exec"
    sample_decision["cycle_id"] = cycle_id
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "decision.json").write_text(
        json.dumps(sample_decision), encoding="utf-8"
    )
    decision_path(root).parent.mkdir(parents=True, exist_ok=True)
    decision_path(root).write_text(json.dumps(sample_decision), encoding="utf-8")

    sm = StateMachine(root)
    sm.save(sm.load())  # ensure path
    st = sm.load()
    st.status = "EXECUTING"
    st.cycle_id = cycle_id
    st.decision_id = sample_decision["decision_id"]
    sm.save(st)

    # Mock executor/verify/review/publish to avoid network
    def fake_execute(decision, **kwargs):
        return {
            "status": "mock_completed",
            "exit_code": 0,
            "worktree": str(root),
            "cycle_id": cycle_id,
            "session_id": "sess",
        }

    def fake_verify(**kwargs):
        return {
            "result": "PASS",
            "failed_criteria": [],
            "repair_hints": [],
            "criterion_matrix": [{"criterion": "x", "status": "PASS", "evidence": "t"}],
            "diff": {"sha256": "0", "text": "", "truncated": False, "char_len": 0},
            "files": {"modified": ["a.py"]},
            "checks": [],
        }

    def fake_review(**kwargs):
        return {
            "schema_version": "1.0",
            "review_id": "r1",
            "cycle_id": cycle_id,
            "decision_id": sample_decision["decision_id"],
            "verdict": "ACCEPT",
            "summary": "ok",
            "failed_criteria": [],
            "repair_instructions": [],
            "confidence": 0.9,
            "human_gate": {"required": False, "reason": None},
        }

    def fake_publish(**kwargs):
        return {
            "ok": True,
            "status": "WAITING_HUMAN",
            "pr": {"number": 99, "url": "https://example/pr/99"},
            "commit": "abc",
            "merge": False,
        }

    monkeypatch.setattr("scripts.cto.cli.grok_execute", fake_execute)
    monkeypatch.setattr("scripts.cto.cli.verify", fake_verify)
    monkeypatch.setattr("scripts.cto.cli.review_execution", fake_review)
    monkeypatch.setattr("scripts.cto.cli.publish_after_accept", fake_publish)
    monkeypatch.setattr("scripts.cto.cli.update_issue_for_cycle", lambda **k: {"ok": True})
    monkeypatch.setattr("scripts.cto.cli.refresh_executive", lambda r: {"ok": True})
    monkeypatch.setattr("scripts.cto.cli.record_usage", lambda **k: None)
    monkeypatch.setattr("scripts.cto.cli.append_ledger", lambda *a, **k: None)
    monkeypatch.setattr("scripts.cto.cli.load_config", lambda r=None: __import__(
        "scripts.cto.config", fromlist=["load_config"]
    ).load_config(root))

    from scripts.cto.cli import cmd_resume

    args = Namespace(
        dry_run=True,
        mock=True,
        skip_tests=True,
        skip_publish=False,
        skip_push=True,
    )
    code = cmd_resume(args)
    assert code == EXIT_WAITING_HUMAN
    assert sm.load().status == "WAITING_HUMAN"
    assert (cdir / "decision.json").is_file()


def test_resume_from_reviewing(cto_repo, sample_decision, monkeypatch):
    root = cto_repo
    monkeypatch.setattr("scripts.cto.cli.repo_root", lambda: root)
    from scripts.cto import paths as paths_mod

    monkeypatch.setattr(paths_mod, "repo_root", lambda: root)

    cycle_id = "cyc-resume-rev"
    sample_decision["cycle_id"] = cycle_id
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "decision.json").write_text(json.dumps(sample_decision), encoding="utf-8")
    (cdir / "execution.json").write_text(
        json.dumps({"status": "mock_completed", "exit_code": 0, "worktree": str(root)}),
        encoding="utf-8",
    )
    (cdir / "verification.json").write_text(
        json.dumps(
            {
                "result": "PASS",
                "failed_criteria": [],
                "criterion_matrix": [{"criterion": "t", "status": "PASS", "evidence": "e"}],
                "diff": {"sha256": "0"},
                "files": {"modified": []},
                "checks": [],
            }
        ),
        encoding="utf-8",
    )
    decision_path(root).parent.mkdir(parents=True, exist_ok=True)
    decision_path(root).write_text(json.dumps(sample_decision), encoding="utf-8")

    sm = StateMachine(root)
    st = sm.load()
    st.status = "REVIEWING"
    st.cycle_id = cycle_id
    sm.save(st)

    monkeypatch.setattr(
        "scripts.cto.cli.review_execution",
        lambda **k: {
            "schema_version": "1.0",
            "review_id": "r2",
            "cycle_id": cycle_id,
            "decision_id": sample_decision["decision_id"],
            "verdict": "ESCALATE",
            "summary": "need human",
            "failed_criteria": [],
            "repair_instructions": [],
            "confidence": 0.5,
            "human_gate": {"required": True, "reason": "test"},
        },
    )
    monkeypatch.setattr("scripts.cto.cli.update_issue_for_cycle", lambda **k: {"ok": True})
    monkeypatch.setattr("scripts.cto.cli.refresh_executive", lambda r: {"ok": True})
    monkeypatch.setattr("scripts.cto.cli.record_usage", lambda **k: None)
    monkeypatch.setattr("scripts.cto.cli.append_ledger", lambda *a, **k: None)
    monkeypatch.setattr(
        "scripts.cto.cli.load_config",
        lambda r=None: __import__("scripts.cto.config", fromlist=["load_config"]).load_config(root),
    )

    from scripts.cto.cli import cmd_resume

    args = Namespace(dry_run=True, mock=True, skip_tests=True, skip_publish=True, skip_push=True)
    code = cmd_resume(args)
    assert code == EXIT_WAITING_HUMAN
    assert sm.load().cycle_id == cycle_id
