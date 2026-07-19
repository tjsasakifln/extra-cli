"""Verifier matrix, UNPROVEN blocks PASS, executor fail, secrets, escape."""
from __future__ import annotations

from scripts.cto.verifier import capture_working_tree, verify


def test_criterion_matrix_present(cto_repo, sample_decision):
    sample_decision["cycle_id"] = "cyc-matrix"
    out = verify(
        decision=sample_decision,
        root=cto_repo,
        skip_tests=True,
        execution={"status": "mock_completed", "exit_code": 0},
    )
    assert "criterion_matrix" in out
    assert out["criterion_matrix"]
    assert all(m["status"] in {"PASS", "FAIL", "UNPROVEN"} for m in out["criterion_matrix"])
    assert "diff" in out
    assert "sha256" in out["diff"]
    assert "files" in out
    assert "staged" in out["files"]


def test_unproven_blocks_pass(cto_repo, sample_decision):
    sample_decision["cycle_id"] = "cyc-unproven"
    sample_decision["required_evidence"] = ["definitely-missing-evidence-xyz.log"]
    out = verify(
        decision=sample_decision,
        root=cto_repo,
        skip_tests=False,  # strict
        execution={"status": "completed", "exit_code": 0},
    )
    # missing evidence + empty tests → cannot PASS
    assert out["result"] != "PASS"
    assert any(
        m["status"] == "UNPROVEN" for m in out["criterion_matrix"]
    ) or any("UNPROVEN" in f for f in out["failed_criteria"])


def test_executor_fail_blocks_pass(cto_repo, sample_decision):
    # make a modification so path scope ok
    p = cto_repo / "scripts" / "cto" / "x.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# x\n", encoding="utf-8")
    sample_decision["cycle_id"] = "cyc-exec-fail"
    sample_decision["allowed_paths"] = ["scripts/cto/**"]
    out = verify(
        decision=sample_decision,
        root=cto_repo,
        skip_tests=True,
        execution={"status": "failed", "exit_code": 1},
    )
    assert out["result"] != "PASS"
    assert any("executor" in f.lower() for f in out["failed_criteria"]) or any(
        m["criterion"] == "executor_status" and m["status"] == "FAIL"
        for m in out["criterion_matrix"]
    )


def test_untracked_secret_scan(cto_repo, sample_decision):
    secret = cto_repo / "leaked.env"
    secret.write_text("API_KEY=supersecretvalue12345\n", encoding="utf-8")
    sample_decision["cycle_id"] = "cyc-secret"
    sample_decision["allowed_paths"] = ["**"]
    out = verify(
        decision=sample_decision,
        root=cto_repo,
        skip_tests=True,
        execution={"status": "mock_completed", "exit_code": 0},
    )
    assert out["result"] == "UNSAFE" or any("secret" in f.lower() for f in out["failed_criteria"])


def test_capture_working_tree_inventory(cto_repo):
    (cto_repo / "new_untracked.txt").write_text("hi\n", encoding="utf-8")
    tree = capture_working_tree(cto_repo)
    assert "untracked" in tree
    assert "diff" in tree
    assert tree["diff"]["sha256"]
    assert any("new_untracked.txt" in u for u in tree["untracked"])
