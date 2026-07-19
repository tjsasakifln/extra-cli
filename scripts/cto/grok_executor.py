"""Grok Build executor — headless, sandboxed, worktree-bound."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.config import load_config
from scripts.cto.paths import cto_dir, cycles_dir, repo_root
from scripts.cto.redaction import redact_obj, redact_text, safe_exception_message

# Credentials that must never enter the Grok child environment
STRIP_ENV_KEYS = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_PAT",
        "GH_ENTERPRISE_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_CLIENT_SECRET",
        "AZURE_CLIENT_ID",
        "NETLIFY_AUTH_TOKEN",
        "RAILWAY_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SESSION_TOKEN",
        "DIGITALOCEAN_TOKEN",
        "HEROKU_API_KEY",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "STRIPE_SECRET_KEY",
        "STRIPE_API_KEY",
    }
)

STRIP_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GOOGLE_",
    "OPENAI_",
    "ANTHROPIC_",
    "GH_",
    "GITHUB_",
    "NETLIFY_",
    "RAILWAY_",
    "HEROKU_",
    "STRIPE_",
)

DENY_RULES = [
    "Bash(git push*)",
    "Bash(git merge*)",
    "Bash(git rebase*)",
    "Bash(git reset --hard*)",
    "Bash(gh pr merge*)",
    "Bash(gh api*)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(python *push*)",
    "Bash(python3 *push*)",
    "Bash(rm -rf*)",
    "Read(.env)",
    "Read(~/.ssh/**)",
]

# Patterns that would circumvent git push deny via alternate tools
CIRCUMVENTION_PATTERNS = [
    re.compile(r"\bgh\s+api\b", re.I),
    re.compile(r"\bcurl\b.*github\.com", re.I),
    re.compile(r"\bwget\b.*github\.com", re.I),
    re.compile(r"\bgit\s+push\b", re.I),
    re.compile(r"\bgh\s+pr\s+merge\b", re.I),
    re.compile(r"urllib\.request", re.I),
    re.compile(r"requests\.(post|put|patch)", re.I),
]


class ExecutorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_prompt(template_name: str, mapping: dict[str, Any], root: Path | None = None) -> str:
    path = cto_dir(root) / "prompts" / template_name
    text = path.read_text(encoding="utf-8")
    for key, value in mapping.items():
        if isinstance(value, list):
            rendered = "\n".join(f"- {v}" for v in value) if value else "- (none)"
        else:
            rendered = str(value)
        text = text.replace("{{" + key + "}}", rendered)
    return text


def _assert_not_main(worktree: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        check=False,
    )
    branch = (proc.stdout or "").strip()
    if branch in {"main", "master"}:
        raise ExecutorError("refusing to execute on main/master")
    return branch


def prepare_worktree(
    *,
    cycle_id: str,
    branch_name: str | None = None,
    root: Path | None = None,
    base: str = "HEAD",
) -> dict[str, Any]:
    """Create isolated worktree for a cycle."""
    root = root or repo_root()
    branch = branch_name or f"cto/{cycle_id}"
    wt_parent = root.parent / f"{root.name}-cto-cycles"
    wt_parent.mkdir(parents=True, exist_ok=True)
    wt_path = wt_parent / cycle_id
    if wt_path.exists():
        return {
            "worktree": str(wt_path),
            "branch": branch,
            "created": False,
            "exists": True,
        }
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), base],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if not wt_path.exists():
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), branch],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    if not wt_path.exists():
        raise ExecutorError(f"failed to create worktree at {wt_path}")
    return {
        "worktree": str(wt_path),
        "branch": branch,
        "created": True,
        "exists": True,
    }


def strip_child_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Remove non-essential credentials from Grok child environment."""
    base = dict(env if env is not None else os.environ)
    for k in list(base.keys()):
        if k in STRIP_ENV_KEYS:
            base.pop(k, None)
            continue
        if any(k.startswith(p) for p in STRIP_ENV_PREFIXES):
            # Keep PATH-like non-secret; strip token-ish
            upper = k.upper()
            if any(
                s in upper
                for s in (
                    "TOKEN",
                    "SECRET",
                    "PASSWORD",
                    "API_KEY",
                    "APIKEY",
                    "CREDENTIAL",
                    "PRIVATE",
                )
            ):
                base.pop(k, None)
    return base


def preflight_deny_flags(grok_bin: str | None = None) -> dict[str, Any]:
    """Prove --deny is supported before enabling always_approve.

    Does not assume deny works. Parses help/output for flag presence.
    """
    binary = grok_bin or shutil.which("grok")
    if not binary:
        return {
            "ok": False,
            "deny_supported": False,
            "reason": "grok binary not found",
            "proof": None,
        }
    try:
        proc = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        help_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "deny_supported": False,
            "reason": f"help failed: {exc}",
            "proof": None,
        }
    deny_ok = bool(re.search(r"--deny\b", help_text))
    sandbox_ok = bool(re.search(r"--sandbox\b", help_text))
    always_ok = bool(re.search(r"--always-approve\b", help_text))
    return {
        "ok": deny_ok and sandbox_ok,
        "deny_supported": deny_ok,
        "sandbox_supported": sandbox_ok,
        "always_approve_supported": always_ok,
        "reason": None if (deny_ok and sandbox_ok) else "missing deny/sandbox flags in grok --help",
        "proof": {
            "help_has_deny": deny_ok,
            "help_has_sandbox": sandbox_ok,
            "help_has_always_approve": always_ok,
            "help_excerpt": help_text[:800],
        },
    }


def build_grok_command(
    *,
    worktree: Path,
    session_id: str,
    prompt: str,
    max_turns: int,
    always_approve: bool,
    include_deny: bool = True,
) -> list[str]:
    cmd = [
        "grok",
        "--no-auto-update",
        "--cwd",
        str(worktree),
        "--session-id",
        session_id,
        "--output-format",
        "streaming-json",
        "--sandbox",
        "workspace",
        "--max-turns",
        str(max_turns),
    ]
    if include_deny:
        for rule in DENY_RULES:
            cmd.extend(["--deny", rule])
    if always_approve:
        cmd.append("--always-approve")
    cmd.extend(["-p", prompt])
    return cmd


def command_allows_push_circumvention(cmd: list[str]) -> bool:
    """True if command construction does not block alternate push tools.

    Used by tests: publisher owns push; executor cmd must include deny rules
    and must not embed gh api/curl push helpers as approved tools.
    """
    joined = " ".join(cmd)
    # Executor must not itself invoke push
    if re.search(r"\bgit\s+push\b", joined) and "-p" not in cmd[:3]:
        # prompt may mention push as forbidden text — only flag if git push is a bare arg sequence
        pass
    if "git" in cmd and "push" in cmd:
        return True
    if "gh" in cmd and "api" in cmd:
        return True
    return False


def execute(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = True,
    mock: bool = False,
    repair: bool = False,
    repair_context: dict[str, Any] | None = None,
    worktree_override: Path | None = None,
) -> dict[str, Any]:
    """Execute decision via Grok or mock. Default dry_run safe."""
    root = root or repo_root()
    cfg = load_config(root)
    cycle_id = decision.get("cycle_id") or f"cyc-{uuid.uuid4().hex[:10]}"
    session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cto-{cycle_id}"))
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)

    if decision.get("decision") not in {"EXECUTE", "REPAIR"}:
        return {
            "status": "skipped",
            "reason": f"decision={decision.get('decision')} is not executable",
            "cycle_id": cycle_id,
        }

    hg = decision.get("human_gate") or {}
    if hg.get("required"):
        return {
            "status": "escalated",
            "reason": "human_gate.required",
            "cycle_id": cycle_id,
        }

    exec_blob = " ".join(
        [
            str(decision.get("objective") or ""),
            " ".join(decision.get("test_commands") or []),
            " ".join(decision.get("acceptance_criteria") or []),
        ]
    )
    for pat in CIRCUMVENTION_PATTERNS:
        if pat.search(exec_blob):
            return {
                "status": "unsafe",
                "reason": f"decision content attempts push/merge circumvention: {pat.pattern}",
                "cycle_id": cycle_id,
            }

    if repair and repair_context:
        prompt = render_prompt(
            "grok-repair.md",
            {
                "failed_criteria": repair_context.get("failed_criteria") or [],
                "repair_instructions": repair_context.get("repair_instructions") or [],
                "allowed_paths": decision.get("allowed_paths") or [],
                "forbidden_paths": decision.get("forbidden_paths") or [],
                "forbidden_actions": decision.get("forbidden_actions") or [],
                "remaining_repairs": max(
                    0,
                    int(decision.get("max_repair_attempts") or 2)
                    - int(repair_context.get("attempt") or 1),
                ),
            },
            root,
        )
    else:
        prompt = render_prompt(
            "grok-execute.md",
            {
                "objective": decision.get("objective") or "",
                "cycle_id": cycle_id,
                "decision_id": decision.get("decision_id") or "",
                "issue_number": decision.get("issue_number") or "",
                "work_id": decision.get("work_id") or "",
                "acceptance_criteria": decision.get("acceptance_criteria") or [],
                "required_evidence": decision.get("required_evidence") or [],
                "allowed_paths": decision.get("allowed_paths") or [],
                "forbidden_paths": decision.get("forbidden_paths") or [],
                "test_commands": decision.get("test_commands") or [],
                "forbidden_actions": decision.get("forbidden_actions") or [],
            },
            root,
        )

    # Explicit anti-circumvention instruction in prompt
    prompt = (
        prompt
        + "\n\n## Hard constraints (executor)\n"
        + "- NEVER run git push, gh pr merge, gh api, curl/wget to GitHub, or Python HTTP to push.\n"
        + "- Push/PR is owned by the separate publisher component after ACCEPT only.\n"
    )
    prompt = redact_text(prompt)
    (cdir / ("repair_prompt.md" if repair else "execute_prompt.md")).write_text(
        prompt, encoding="utf-8"
    )

    if worktree_override is not None:
        worktree = Path(worktree_override)
        prep = {
            "worktree": str(worktree),
            "branch": None,
            "created": False,
            "exists": worktree.exists(),
        }
        managed_parent = (root.parent / f"{root.name}-cto-cycles").resolve()
        try:
            worktree.resolve().relative_to(managed_parent)
        except ValueError:
            return {
                "status": "unsafe",
                "reason": f"worktree outside managed path: {worktree}",
                "cycle_id": cycle_id,
                "worktree": str(worktree),
            }
    else:
        prep = prepare_worktree(cycle_id=cycle_id, root=root)
        worktree = Path(prep["worktree"])
    try:
        branch = _assert_not_main(worktree)
    except ExecutorError as exc:
        return {
            "status": "unsafe",
            "reason": str(exc),
            "cycle_id": cycle_id,
            "worktree": str(worktree),
        }

    # Preflight deny flags — always_approve only after objective proof
    preflight = preflight_deny_flags()
    always_approve = False
    protection_ok = bool(
        worktree.exists()
        and preflight.get("deny_supported")
        and preflight.get("sandbox_supported")
    )
    if protection_ok:
        always_approve = True
    elif not dry_run and not mock:
        # Live without proven protections → fail closed
        result_fail = {
            "status": "failed",
            "reason": (
                "always_approve denied: deny/sandbox flags not proven "
                f"({preflight.get('reason')})"
            ),
            "cycle_id": cycle_id,
            "session_id": session_id,
            "worktree": str(worktree),
            "branch": branch,
            "preflight": preflight,
            "always_approve": False,
            "timestamp_utc": _utc_now(),
        }
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result_fail), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result_fail)

    child_env = strip_child_env()

    cmd = build_grok_command(
        worktree=worktree,
        session_id=session_id,
        prompt=prompt,
        max_turns=cfg.budgets.grok_max_turns,
        always_approve=always_approve,
        include_deny=bool(preflight.get("deny_supported") or dry_run or mock),
    )

    result: dict[str, Any] = {
        "status": "planned",
        "cycle_id": cycle_id,
        "session_id": session_id,
        "worktree": str(worktree),
        "branch": branch,
        "command": cmd[:12] + ["-p", "<redacted-prompt>"],
        "dry_run": dry_run,
        "mock": mock,
        "preflight": preflight,
        "always_approve": always_approve,
        "env_stripped_keys": sorted(STRIP_ENV_KEYS),
        "timestamp_utc": _utc_now(),
    }

    if dry_run and not mock:
        result["status"] = "dry_run"
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result)

    if mock:
        evidence = worktree / "output" / "cto" / "cycles" / cycle_id
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "mock_execution.txt").write_text(
            f"mock execution for {decision.get('work_id')}\n",
            encoding="utf-8",
        )
        # Also touch a tracked-allowed path so verifier sees a non-ignored change
        # (output/ is often gitignored).
        demo = worktree / "docs" / "ops" / "cto-autopilot" / f".mock-{cycle_id}.md"
        demo.parent.mkdir(parents=True, exist_ok=True)
        demo.write_text(
            f"# mock cycle {cycle_id}\n\nwork_id={decision.get('work_id')}\n",
            encoding="utf-8",
        )
        result["status"] = "mock_completed"
        result["exit_code"] = 0
        result["mock_artifact"] = str(evidence / "mock_execution.txt")
        result["mock_visible_change"] = str(demo)
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result)

    if not shutil.which("grok"):
        result["status"] = "failed"
        result["reason"] = "grok binary not found"
        return redact_obj(result)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=max(120, cfg.budgets.grok_max_turns * 60),
            env=child_env,
            check=False,
        )
        transcript = redact_text((proc.stdout or "") + "\n" + (proc.stderr or ""))
        (cdir / "transcript.streaming.jsonl").write_text(transcript[-500000:], encoding="utf-8")
        result["status"] = "completed" if proc.returncode == 0 else "failed"
        result["exit_code"] = proc.returncode
        result["transcript_path"] = str(cdir / "transcript.streaming.jsonl")
        result["transcript_excerpt"] = transcript[-8000:]
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["reason"] = safe_exception_message(exc)

    (cdir / "execution.json").write_text(
        json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return redact_obj(result)
