"""Publisher is separate from Grok executor; no auto-merge; no dry-run queue pollution."""
from __future__ import annotations

import inspect

import scripts.cto.grok_executor as grok_executor
import scripts.cto.publisher as publisher
from scripts.cto.publisher import (
    MERGE_AUTHORITY,
    has_real_draft_pr,
    publish_after_accept,
    record_publication,
)
from scripts.cto.work_registry import load_registry, save_registry


def test_publisher_owns_push_not_executor():
    assert publisher.publisher_invokes_push() is True
    src = inspect.getsource(grok_executor.execute)
    assert "git push" not in src or "never" in src.lower() or "unsafe" in src
    assert "push_branch" not in src
    assert "publish_after_accept" not in src


def test_publish_dry_run_does_not_waiting_human_or_mutate(cto_repo, sample_decision):
    sample_decision["cycle_id"] = "cyc-pub-dry"
    sample_decision["work_id"] = "integrate-extra-ops-95"
    # seed registry item
    reg = {
        "schema_version": "1.0",
        "work_items": [
            {
                "work_id": "integrate-extra-ops-95",
                "state": "ready",
                "issue_number": 32,
                "evidence": [],
                "execution_history": [],
            }
        ],
    }
    save_registry(reg, cto_repo)
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
    assert out["status"] == "ACCEPTED_DRY_RUN"
    assert out["status"] != "WAITING_HUMAN"
    assert out["merge"] is False
    assert out["queue_mutated"] is False
    assert out["human_gate"]["required"] is False
    assert (out.get("pr") or {}).get("number") is None
    # registry must stay ready
    after = load_registry(cto_repo)
    item = after["work_items"][0]
    assert item["state"] == "ready"
    assert not any(
        (h.get("phase") == "published_draft_pr" and h.get("pr") is None)
        for h in (item.get("execution_history") or [])
    )


def test_record_publication_refuses_null_pr(cto_repo):
    reg = {
        "schema_version": "1.0",
        "work_items": [
            {
                "work_id": "x",
                "state": "ready",
                "issue_number": 1,
                "evidence": [],
                "execution_history": [],
            }
        ],
    }
    save_registry(reg, cto_repo)
    rec = record_publication(
        root=cto_repo,
        work_id="x",
        issue_number=1,
        cycle_id="c1",
        commit="abc",
        pr={"number": None, "url": None},
    )
    assert rec["skipped"] is True
    assert load_registry(cto_repo)["work_items"][0]["state"] == "ready"


def test_record_publication_requires_real_pr(cto_repo):
    reg = {
        "schema_version": "1.0",
        "work_items": [
            {
                "work_id": "x",
                "state": "ready",
                "issue_number": 1,
                "evidence": [],
                "execution_history": [],
            }
        ],
    }
    save_registry(reg, cto_repo)
    rec = record_publication(
        root=cto_repo,
        work_id="x",
        issue_number=1,
        cycle_id="c1",
        commit="abc",
        pr={"number": 99, "url": "https://example/pr/99"},
    )
    assert rec["ok"] is True
    item = load_registry(cto_repo)["work_items"][0]
    assert item["state"] == "human"
    assert any("draft_pr" in str(e) for e in item["evidence"])


def test_failed_pr_open_not_waiting_human(cto_repo, sample_decision, monkeypatch):
    sample_decision["cycle_id"] = "cyc-pub-fail"
    sample_decision["work_id"] = "y"
    reg = {
        "schema_version": "1.0",
        "work_items": [
            {
                "work_id": "y",
                "state": "ready",
                "issue_number": 2,
                "evidence": [],
                "execution_history": [],
            }
        ],
    }
    save_registry(reg, cto_repo)
    monkeypatch.setattr(
        publisher,
        "open_or_update_draft_pr",
        lambda *a, **k: {
            "ok": False,
            "number": None,
            "url": None,
            "stderr": "gh failed",
            "action": "create",
        },
    )
    monkeypatch.setattr(publisher, "push_branch", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(
        publisher,
        "ensure_commit",
        lambda *a, **k: {"committed": False, "commit": "deadbeef", "dry_run": False},
    )
    out = publish_after_accept(
        decision=sample_decision,
        worktree=cto_repo,
        root=cto_repo,
        dry_run=False,
        skip_push=False,
    )
    assert out["status"] == "FAILED"
    assert out["status"] != "WAITING_HUMAN"
    assert out["queue_mutated"] is False
    assert load_registry(cto_repo)["work_items"][0]["state"] == "ready"


def test_has_real_draft_pr():
    assert has_real_draft_pr({"number": 1, "url": "u"}) is True
    assert has_real_draft_pr({"number": None}) is False
    assert has_real_draft_pr({}) is False
    assert has_real_draft_pr(None) is False


def test_no_merge_in_publisher_source():
    src = inspect.getsource(publisher)
    assert "pr merge" not in src
    assert "auto_merge" in src
    assert MERGE_AUTHORITY == "Tiago"
