"""Publisher is separate from Grok executor; no auto-merge."""
from __future__ import annotations

import inspect

import scripts.cto.grok_executor as grok_executor
import scripts.cto.publisher as publisher
from scripts.cto.publisher import MERGE_AUTHORITY, publish_after_accept


def test_publisher_owns_push_not_executor():
    assert publisher.publisher_invokes_push() is True
    src = inspect.getsource(grok_executor.execute)
    assert "git push" not in src or "never" in src.lower() or "unsafe" in src
    # execute must not call push_branch
    assert "push_branch" not in src
    assert "publish_after_accept" not in src


def test_publish_dry_run_waiting_human(cto_repo, sample_decision):
    sample_decision["cycle_id"] = "cyc-pub-1"
    # create a fake dirty file so ensure_commit has something
    f = cto_repo / "scripts" / "cto" / "demo.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("demo\n", encoding="utf-8")
    out = publish_after_accept(
        decision=sample_decision,
        worktree=cto_repo,
        root=cto_repo,
        dry_run=True,
        skip_push=True,
    )
    assert out["status"] == "WAITING_HUMAN"
    assert out["merge"] is False
    assert out["merge_authority"] == MERGE_AUTHORITY
    assert out["human_gate"]["required"] is True
    assert "Tiago" in (out["human_gate"]["reason"] or MERGE_AUTHORITY)


def test_no_merge_in_publisher_source():
    src = inspect.getsource(publisher)
    # should not call gh pr merge
    assert "pr merge" not in src
    assert "auto_merge" in src  # documented false
