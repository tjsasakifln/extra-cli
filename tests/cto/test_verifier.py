from pathlib import Path

from scripts.cto.verifier import verify


def test_verifier_pass_noop_scope(cto_repo, sample_decision):
    # No modifications — EXECUTE becomes INCOMPLETE
    sample_decision["cycle_id"] = "cyc-ver-1"
    out = verify(decision=sample_decision, root=cto_repo, skip_tests=True)
    assert out["result"] in {"INCOMPLETE", "PASS", "FAIL"}
    assert "result" in out


def test_verifier_detects_dod_unauthorized(cto_repo, sample_decision):
    dod = cto_repo / "DOD.md"
    dod.write_text(dod.read_text(encoding="utf-8") + "\n- [x] sneaky\n", encoding="utf-8")
    sample_decision["allowed_paths"] = ["scripts/cto/**"]
    sample_decision["cycle_id"] = "cyc-ver-dod"
    out = verify(decision=sample_decision, root=cto_repo, skip_tests=True)
    assert out["result"] == "UNSAFE"
    assert any("DOD.md" in f for f in out["failed_criteria"])


def test_verifier_main_forbidden(cto_repo, sample_decision, monkeypatch):
    import subprocess

    subprocess.run(["git", "branch", "-M", "main"], cwd=cto_repo, check=True, capture_output=True)
    sample_decision["cycle_id"] = "cyc-ver-main"
    out = verify(decision=sample_decision, root=cto_repo, skip_tests=True)
    assert out["result"] == "UNSAFE"
    assert any("main" in f for f in out["failed_criteria"])


def test_verifier_rejects_unsafe_test_command(cto_repo, sample_decision):
    sample_decision["test_commands"] = ["pytest; rm -rf /"]
    sample_decision["cycle_id"] = "cyc-ver-cmd"
    # leave feature branch
    import subprocess

    subprocess.run(["git", "branch", "-M", "feat/x"], cwd=cto_repo, check=True, capture_output=True)
    out = verify(decision=sample_decision, root=cto_repo, skip_tests=False)
    assert out["result"] == "UNSAFE"
