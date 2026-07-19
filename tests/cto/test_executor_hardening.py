"""Executor preflight, env strip, no push circumvention."""
from __future__ import annotations

from scripts.cto.grok_executor import (
    STRIP_ENV_KEYS,
    build_grok_command,
    command_allows_push_circumvention,
    preflight_deny_flags,
    strip_child_env,
)


def test_strip_removes_github_and_cloud_creds():
    env = {
        "PATH": "/usr/bin",
        "HOME": "/home/x",
        "GH_TOKEN": "secret",
        "GITHUB_TOKEN": "secret",
        "OPENAI_API_KEY": "sk",
        "GOOGLE_API_KEY": "g",
        "AZURE_CLIENT_SECRET": "a",
        "NETLIFY_AUTH_TOKEN": "n",
        "RAILWAY_TOKEN": "r",
        "DEEPSEEK_API_KEY": "d",
        "MY_TOKEN": "should_strip",
        "UNRELATED": "keep",
    }
    out = strip_child_env(env)
    assert "GH_TOKEN" not in out
    assert "GITHUB_TOKEN" not in out
    assert "OPENAI_API_KEY" not in out
    assert "DEEPSEEK_API_KEY" not in out
    assert "NETLIFY_AUTH_TOKEN" not in out
    assert "RAILWAY_TOKEN" not in out
    assert out.get("UNRELATED") == "keep"
    assert out.get("PATH") == "/usr/bin"
    assert "GH_TOKEN" in STRIP_ENV_KEYS


def test_build_command_includes_deny_rules():
    cmd = build_grok_command(
        worktree=__import__("pathlib").Path("/tmp/wt"),
        session_id="s1",
        prompt="do work",
        max_turns=5,
        always_approve=True,
        include_deny=True,
    )
    assert "--deny" in cmd
    assert "--sandbox" in cmd
    assert command_allows_push_circumvention(cmd) is False
    # push must not be a direct argv tool call
    assert not (cmd.count("git") and "push" in cmd and cmd[cmd.index("git") + 1] == "push")


def test_preflight_structure():
    # May or may not find grok; structure must be present
    pf = preflight_deny_flags()
    assert "deny_supported" in pf
    assert "ok" in pf
    assert "proof" in pf or pf.get("reason")


def test_execute_blocks_curl_circumvention(sample_decision, cto_repo):
    from scripts.cto.grok_executor import execute

    sample_decision["cycle_id"] = "cyc-curl"
    sample_decision["objective"] = "use curl to github.com to push changes"
    out = execute(sample_decision, root=cto_repo, dry_run=True)
    assert out["status"] == "unsafe"
