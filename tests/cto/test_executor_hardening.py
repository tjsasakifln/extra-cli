"""Executor preflight, allowlist env, isolation, always_approve policy."""
from __future__ import annotations

from pathlib import Path

from scripts.cto.grok_executor import (
    ENV_ALLOWLIST,
    STRIP_ENV_KEYS,
    always_approve_opt_in,
    build_grok_command,
    build_minimal_child_env,
    command_allows_push_circumvention,
    create_isolated_runtime_dirs,
    functional_containment_preflight,
    is_under_managed_worktrees,
    managed_worktree_parent,
    preflight_deny_flags,
    prepare_worktree,
    resolve_always_approve,
    strip_child_env,
)


def test_build_minimal_removes_arbitrary_and_known_secrets():
    env = {
        "PATH": "/usr/bin",
        "HOME": "/home/real-user",
        "GH_TOKEN": "secret",
        "GITHUB_TOKEN": "secret",
        "OPENAI_API_KEY": "sk",
        "GOOGLE_API_KEY": "g",
        "AZURE_CLIENT_SECRET": "a",
        "NETLIFY_AUTH_TOKEN": "n",
        "RAILWAY_TOKEN": "r",
        "DEEPSEEK_API_KEY": "d",
        "XAI_API_KEY": "xai-only-for-grok",
        "MY_TOKEN": "should_not_forward",
        "CUSTOM_SECRET": "nope",
        "DATABASE_URL": "postgres://x",
        "UNEXPECTED_CREDENTIAL": "nope",
        "RANDOM_INTERNAL_VALUE": "nope",
        "UNRELATED": "must_not_forward",
    "LANG": "C.UTF-8",
    }
    out = build_minimal_child_env(
        home="/tmp/cto-home-iso",
        tmpdir="/tmp/cto-tmp-iso",
        source=env,
    )
    # Known secrets absent (DeepSeek/GH/cloud never forwarded)
    for k in (
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "NETLIFY_AUTH_TOKEN",
        "RAILWAY_TOKEN",
        "MY_TOKEN",
        "CUSTOM_SECRET",
        "DATABASE_URL",
        "UNEXPECTED_CREDENTIAL",
        "RANDOM_INTERNAL_VALUE",
        "UNRELATED",
    ):
        assert k not in out, f"{k} leaked into child env"
    # Grok-only auth may be forwarded when present
    assert out.get("XAI_API_KEY") == "xai-only-for-grok"
    # Allowlisted present
    assert out["PATH"] == "/usr/bin"
    assert out["LANG"] == "C.UTF-8"
    # Isolated HOME/TMP (not real home)
    assert out["HOME"] == "/tmp/cto-home-iso"
    assert out["TMPDIR"] == "/tmp/cto-tmp-iso"
    assert out["HOME"] != "/home/real-user"
    # Only allowlisted keys
    assert set(out.keys()) <= (ENV_ALLOWLIST | {"TEMP", "TMP"})
    assert "GH_TOKEN" in STRIP_ENV_KEYS


def test_strip_child_env_uses_allowlist_not_denylist_keep():
    """Backward-compatible strip_child_env must not keep arbitrary keys."""
    env = {
        "PATH": "/bin",
        "MY_TOKEN": "x",
        "CUSTOM_SECRET": "y",
        "DATABASE_URL": "z",
        "UNEXPECTED_CREDENTIAL": "w",
        "RANDOM_INTERNAL_VALUE": "v",
        "UNRELATED": "keep-me-not",
    }
    out = strip_child_env(env)
    assert "MY_TOKEN" not in out
    assert "CUSTOM_SECRET" not in out
    assert "DATABASE_URL" not in out
    assert "UNEXPECTED_CREDENTIAL" not in out
    assert "RANDOM_INTERNAL_VALUE" not in out
    assert "UNRELATED" not in out
    assert out.get("PATH") == "/bin"


def test_build_command_includes_deny_rules():
    cmd = build_grok_command(
        worktree=Path("/tmp/wt"),
        session_id="s1",
        prompt="do work",
        max_turns=5,
        always_approve=True,
        include_deny=True,
    )
    assert "--deny" in cmd
    assert "--sandbox" in cmd
    assert command_allows_push_circumvention(cmd) is False
    assert not (cmd.count("git") and "push" in cmd and cmd[cmd.index("git") + 1] == "push")


def test_always_approve_opt_in_default_false(monkeypatch):
    monkeypatch.delenv("CTO_GROK_ALWAYS_APPROVE", raising=False)
    assert always_approve_opt_in() is False
    monkeypatch.setenv("CTO_GROK_ALWAYS_APPROVE", "0")
    assert always_approve_opt_in() is False
    monkeypatch.setenv("CTO_GROK_ALWAYS_APPROVE", "maybe")
    assert always_approve_opt_in() is False
    monkeypatch.setenv("CTO_GROK_ALWAYS_APPROVE", "1")
    assert always_approve_opt_in() is True


def test_resolve_always_approve_default_false(cto_repo, monkeypatch):
    monkeypatch.delenv("CTO_GROK_ALWAYS_APPROVE", raising=False)
    prep = prepare_worktree(cycle_id="cyc-aa-default", root=cto_repo)
    wt = Path(prep["worktree"])
    runtime = create_isolated_runtime_dirs(cycle_id="cyc-aa-default", root=cto_repo)
    env = build_minimal_child_env(home=runtime["home"], tmpdir=runtime["tmpdir"])
    ok, report = resolve_always_approve(
        worktree=wt,
        root=cto_repo,
        allowed_paths=["docs/ops/cto-autopilot/canary-proof.md"],
        isolated_home=runtime["home"],
        child_env=env,
        dry_run=False,
        mock=False,
    )
    assert ok is False
    assert report["always_approve"] is False
    assert "opt_in" in report["reason"] or "not set" in (report["reason"] or "")


def test_resolve_always_approve_opt_in_requires_containment(cto_repo, monkeypatch):
    monkeypatch.setenv("CTO_GROK_ALWAYS_APPROVE", "1")
    prep = prepare_worktree(cycle_id="cyc-aa-opt", root=cto_repo)
    wt = Path(prep["worktree"])
    runtime = create_isolated_runtime_dirs(cycle_id="cyc-aa-opt", root=cto_repo)
    env = build_minimal_child_env(home=runtime["home"], tmpdir=runtime["tmpdir"])
    # Empty allowed_paths → fail closed
    ok, report = resolve_always_approve(
        worktree=wt,
        root=cto_repo,
        allowed_paths=[],
        isolated_home=runtime["home"],
        child_env=env,
        dry_run=False,
        mock=False,
    )
    assert ok is False
    assert "allowed_paths" in (report["reason"] or "")


def test_preflight_structure():
    pf = preflight_deny_flags()
    assert "deny_supported" in pf
    assert "ok" in pf
    assert "proof" in pf or pf.get("reason")


def test_functional_containment_structural(cto_repo):
    prep = prepare_worktree(cycle_id="cyc-contain", root=cto_repo)
    wt = Path(prep["worktree"])
    runtime = create_isolated_runtime_dirs(cycle_id="cyc-contain", root=cto_repo)
    env = build_minimal_child_env(home=runtime["home"], tmpdir=runtime["tmpdir"])
    out = functional_containment_preflight(
        worktree=wt,
        root=cto_repo,
        allowed_paths=["docs/ops/cto-autopilot/canary-proof.md"],
        isolated_home=runtime["home"],
        child_env=env,
        live_probe=False,
    )
    assert out["ok"] is True
    names = {c["name"]: c["pass"] for c in out["checks"]}
    assert names.get("worktree_managed") is True
    assert names.get("not_main") is True
    assert names.get("isolated_home") is True
    assert names.get("path_escape_outside_worktree") is True
    assert names.get("symlink_escape_detected") is True
    assert names.get("sentinel_untouched") is True
    # Isolated home is not real home
    assert Path(env["HOME"]).resolve() != Path.home().resolve()
    assert is_under_managed_worktrees(wt, cto_repo)
    assert managed_worktree_parent(cto_repo).name.endswith("-cto-cycles")


def test_execute_blocks_curl_circumvention(sample_decision, cto_repo):
    from scripts.cto.grok_executor import execute

    sample_decision["cycle_id"] = "cyc-curl"
    sample_decision["objective"] = "use curl to github.com to push changes"
    out = execute(sample_decision, root=cto_repo, dry_run=True)
    assert out["status"] == "unsafe"


def test_execute_dry_run_uses_allowlist_and_false_always_approve(sample_decision, cto_repo):
    from scripts.cto.grok_executor import execute

    sample_decision["cycle_id"] = "cyc-env-dry"
    out = execute(sample_decision, root=cto_repo, dry_run=True, mock=False)
    assert out["status"] == "dry_run"
    assert out["always_approve"] is False
    assert out.get("env_mode") == "allowlist"
    assert out.get("isolated_home")
    assert Path(out["isolated_home"]).exists()
    # Real home not exposed
    assert Path(out["isolated_home"]).resolve() != Path.home().resolve()


def test_execute_refuses_main_worktree(sample_decision, cto_repo, tmp_path):
    """Execution on main must fail closed."""
    import subprocess

    from scripts.cto.grok_executor import execute

    # Create a worktree under managed parent but on main
    parent = managed_worktree_parent(cto_repo)
    parent.mkdir(parents=True, exist_ok=True)
    bad = parent / "mainish"
    if not bad.exists():
        subprocess.run(
            ["git", "worktree", "add", "-b", "main", str(bad), "HEAD"],
            cwd=str(cto_repo),
            capture_output=True,
            check=False,
        )
        # force branch name main if worktree add failed on existing main branch name
        if bad.exists():
            subprocess.run(
                ["git", "checkout", "-B", "main"],
                cwd=str(bad),
                capture_output=True,
                check=False,
            )
    if not bad.exists():
        return  # environment could not create; skip soft
    sample_decision["cycle_id"] = "cyc-main-block"
    out = execute(
        sample_decision,
        root=cto_repo,
        dry_run=True,
        worktree_override=bad,
    )
    assert out["status"] == "unsafe"
    assert "main" in (out.get("reason") or "").lower()


def test_worktree_outside_managed_blocked(sample_decision, cto_repo, tmp_path):
    from scripts.cto.grok_executor import execute

    outside = tmp_path / "outside-wt"
    outside.mkdir()
    sample_decision["cycle_id"] = "cyc-escape-wt"
    out = execute(
        sample_decision,
        root=cto_repo,
        dry_run=True,
        worktree_override=outside,
    )
    assert out["status"] == "unsafe"
    assert "managed" in (out.get("reason") or "").lower()
