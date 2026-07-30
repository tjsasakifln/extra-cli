"""Prove controller accept is fail-closed without evidence (governance).

These tests drive the shipped dod_controller gates — not POLICY dict flags alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import tools.dod_controller as dc


def test_accept_fails_without_evidence_pack(tmp_path: Path, monkeypatch) -> None:
    """Accept must fail when evidence pack/criteria/verify are missing."""
    item_id = "DOD-test-no-evidence-item"
    item = {
        "id": item_id,
        "text": "synthetic",
        "state": "VERIFIED",
        "dod_checked": False,
        "section": "test",
        "location": {"start_line": 1},
        "history": [],
        "evidence": [],
        "tests": ["tests/test_dod_controller_evidence_gates.py"],
        "acceptance_commands": [],
    }
    manifest = {"items": [item]}

    monkeypatch.setattr(dc, "load_manifest", lambda: manifest)
    monkeypatch.setattr(dc, "save_manifest", lambda m: None)
    monkeypatch.setattr(dc, "find_item", lambda m, i: item if i == item_id else None)
    monkeypatch.setattr(dc, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(dc, "_git_branch", lambda: "main")
    monkeypatch.setattr(dc, "_git_head", lambda: "abc123")
    monkeypatch.setattr(dc, "append_log", lambda *a, **k: None)
    monkeypatch.setattr(dc, "emit", lambda *a, **k: None)
    monkeypatch.setattr(dc, "audit_evidence_paths", lambda it: {"status": "n/a"})

    args = SimpleNamespace(
        item_id=item_id,
        json=True,
        pr=None,
        update_dod=False,
        allow_non_main=False,
        allow_missing_evidence=False,
        force=False,
        force_from_state=False,
        skip_ci_gate=False,
        skip_full_suite_gate=False,
        skip_review_gate=False,
        skip_divergence_check=True,
        skip_independent_review=False,
    )
    rc = dc.cmd_accept(args)
    assert rc == 1
    assert item["state"] == "VERIFIED"  # not flipped to ACCEPTED


def test_accept_fails_when_verify_result_not_ok(tmp_path: Path, monkeypatch) -> None:
    item_id = "DOD-test-bad-verify"
    pack = tmp_path / "evidence" / item_id
    pack.mkdir(parents=True)
    (pack / "acceptance_criteria.md").write_text("criteria\n", encoding="utf-8")
    (pack / "verify_result.json").write_text(
        json.dumps({"ok": False, "head_sha": "abc123", "commands": []}),
        encoding="utf-8",
    )
    (pack / "independent_review.md").write_text("review\n", encoding="utf-8")
    (pack / "review_status.json").write_text(
        json.dumps({"pending_changes_requested": False}), encoding="utf-8"
    )
    (pack / "ci_status.json").write_text(
        json.dumps(
            {
                "conclusion": "success",
                "head_sha": "abc123",
                "mandatory_jobs_skipped": [],
            }
        ),
        encoding="utf-8",
    )

    item = {
        "id": item_id,
        "text": "synthetic",
        "state": "VERIFIED",
        "dod_checked": False,
        "section": "test",
        "location": {"start_line": 1},
        "history": [],
        "evidence": [],
        "tests": [],
        "acceptance_commands": [],
    }
    manifest = {"items": [item]}
    monkeypatch.setattr(dc, "load_manifest", lambda: manifest)
    monkeypatch.setattr(dc, "save_manifest", lambda m: None)
    monkeypatch.setattr(dc, "find_item", lambda m, i: item if i == item_id else None)
    monkeypatch.setattr(dc, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(dc, "_git_branch", lambda: "main")
    monkeypatch.setattr(dc, "_git_head", lambda: "abc123")
    monkeypatch.setattr(dc, "append_log", lambda *a, **k: None)
    monkeypatch.setattr(dc, "emit", lambda *a, **k: None)
    monkeypatch.setattr(dc, "audit_evidence_paths", lambda it: {"status": "ok"})
    monkeypatch.setattr(dc, "item_requires_full_suite", lambda it: False)

    args = SimpleNamespace(
        item_id=item_id,
        json=True,
        pr=None,
        update_dod=False,
        allow_non_main=False,
        allow_missing_evidence=False,
        force=False,
        force_from_state=False,
        skip_ci_gate=False,
        skip_full_suite_gate=False,
        skip_review_gate=False,
        skip_divergence_check=True,
        skip_independent_review=False,
    )
    rc = dc.cmd_accept(args)
    assert rc == 1
    assert item["state"] == "VERIFIED"


def test_trivial_command_is_rejected_by_is_trivial() -> None:
    assert dc.is_trivial_command("true") is True
    assert dc.is_trivial_command("echo ok") is True
    assert dc.is_trivial_command("python3 -m pytest tests/test_x.py") is False
