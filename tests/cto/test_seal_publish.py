"""Sealed commit publish path — no git add -A after review."""
from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.cto.publisher import publish_after_accept
from scripts.cto.seal import assert_publishable_seal, build_seal, git_head


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_seal_requires_clean_tree(cto_repo):
    sample = cto_repo / "docs" / "ops" / "cto-autopilot"
    sample.mkdir(parents=True, exist_ok=True)
    f = sample / "seal-probe.txt"
    f.write_text("x\n", encoding="utf-8")
    _git(cto_repo, "add", str(f.relative_to(cto_repo)))
    _git(cto_repo, "commit", "-m", "seal probe")
    seal = build_seal(
        worktree=cto_repo,
        cycle_id="cyc-seal-1",
        decision_id="dec-1",
        verification_result="PASS",
        root=cto_repo,
    )
    assert seal["commit_sha"] == git_head(cto_repo)
    assert seal["worktree_clean"] is True
    assert seal["publishable"] is True


def test_assert_publishable_fails_on_dirty(cto_repo):
    seal = build_seal(
        worktree=cto_repo,
        cycle_id="cyc-seal-dirty",
        decision_id="dec-2",
        verification_result="PASS",
        root=cto_repo,
    )
    # dirty after seal
    (cto_repo / "dirty-after-seal.txt").write_text("nope\n", encoding="utf-8")
    check = assert_publishable_seal(worktree=cto_repo, seal=seal)
    assert check["ok"] is False
    assert any("dirty" in e for e in check["errors"])


def test_assert_publishable_fails_on_non_pass_seal(cto_repo):
    seal = build_seal(
        worktree=cto_repo,
        cycle_id="cyc-seal-fail",
        decision_id="dec-3",
        verification_result="FAIL",
        root=cto_repo,
    )
    check = assert_publishable_seal(
        worktree=cto_repo,
        seal=seal,
        verification={"result": "FAIL"},
    )
    assert check["ok"] is False


def test_publisher_refuses_dirty_after_review(cto_repo):
    decision = {
        "cycle_id": "cyc-pub-dirty",
        "decision_id": "dec-pub",
        "work_id": "w-test",
        "objective": "test",
    }
    (cto_repo / "post-review.txt").write_text("dirty\n", encoding="utf-8")
    seal = {
        "commit_sha": git_head(cto_repo),
        "tree_hash": "deadbeef",
        "verification_result": "PASS",
        "publishable": True,
        "base_commit": None,
    }
    out = publish_after_accept(
        decision=decision,
        worktree=cto_repo,
        root=cto_repo,
        dry_run=False,
        skip_push=True,
        verification={"result": "PASS", "seal": seal},
        review={"verdict": "ACCEPT"},
    )
    assert out["ok"] is False
    assert "dirty" in (out.get("error") or "").lower()


def test_publisher_refuses_non_pass_verification(cto_repo):
    decision = {
        "cycle_id": "cyc-pub-fail",
        "decision_id": "dec-pub2",
        "work_id": "w-test",
        "objective": "test",
    }
    out = publish_after_accept(
        decision=decision,
        worktree=cto_repo,
        root=cto_repo,
        dry_run=False,
        skip_push=True,
        verification={"result": "FAIL"},
        review={"verdict": "ACCEPT"},
    )
    assert out["ok"] is False
    assert out["status"] == "BLOCKED"
