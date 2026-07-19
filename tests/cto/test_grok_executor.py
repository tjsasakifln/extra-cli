from scripts.cto.grok_executor import build_grok_command, execute


def test_build_command_has_sandbox_and_deny(tmp_path):
    cmd = build_grok_command(
        worktree=tmp_path,
        session_id="sess",
        prompt="do work",
        max_turns=5,
        always_approve=True,
    )
    assert "grok" in cmd[0]
    assert "--sandbox" in cmd
    assert "workspace" in cmd
    assert "--always-approve" in cmd
    assert "--deny" in cmd
    assert any("git push" in c for c in cmd)


def test_execute_dry_run(sample_decision, cto_repo):
    sample_decision["cycle_id"] = "cyc-exec-dry"
    out = execute(sample_decision, root=cto_repo, dry_run=True, mock=False)
    assert out["status"] == "dry_run"
    assert out["dry_run"] is True


def test_execute_skips_non_execute(sample_decision, cto_repo):
    sample_decision["decision"] = "NOOP"
    out = execute(sample_decision, root=cto_repo, dry_run=True)
    assert out["status"] == "skipped"


def test_execute_mock(sample_decision, cto_repo):
    sample_decision["cycle_id"] = "cyc-exec-mock"
    out = execute(sample_decision, root=cto_repo, dry_run=False, mock=True)
    assert out["status"] == "mock_completed"
