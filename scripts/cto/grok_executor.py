"""Grok Build executor — headless, sandboxed, worktree-bound."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.config import load_config
from scripts.cto.paths import cto_dir, cycles_dir, repo_root
from scripts.cto.redaction import redact_obj, redact_text, safe_exception_message


class ExecutorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    # create branch from base
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), base],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if not wt_path.exists():
        # try without -b if branch exists
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


def build_grok_command(
    *,
    worktree: Path,
    session_id: str,
    prompt: str,
    max_turns: int,
    always_approve: bool,
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
    # deny dangerous operations (best-effort; grok flag names may vary)
    deny_rules = [
        "Bash(git push*)",
        "Bash(git merge*)",
        "Bash(git rebase*)",
        "Bash(git reset --hard*)",
        "Bash(gh pr merge*)",
        "Bash(rm -rf*)",
        "Read(.env)",
        "Read(~/.ssh/**)",
    ]
    for rule in deny_rules:
        cmd.extend(["--deny", rule])
    if always_approve:
        cmd.append("--always-approve")
    cmd.extend(["-p", prompt])
    return cmd


def execute(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = True,
    mock: bool = False,
    repair: bool = False,
    repair_context: dict[str, Any] | None = None,
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

    # Fail closed if human gate required
    hg = decision.get("human_gate") or {}
    if hg.get("required"):
        return {
            "status": "escalated",
            "reason": "human_gate.required",
            "cycle_id": cycle_id,
        }

    # Prepare prompt
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

    # Redact secrets from prompt just in case
    prompt = redact_text(prompt)
    (cdir / ("repair_prompt.md" if repair else "execute_prompt.md")).write_text(
        prompt, encoding="utf-8"
    )

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

    # Safety: always_approve only if sandbox + worktree + deny rules
    always_approve = True
    if not worktree.exists():
        always_approve = False
    # Never pass DEEPSEEK key into child env explicitly beyond existing
    child_env = os.environ.copy()
    # Strip cloud credentials that executor should not need
    for k in list(child_env.keys()):
        if k in {
            "AWS_SECRET_ACCESS_KEY",
            "AWS_ACCESS_KEY_ID",
            "DEEPSEEK_API_KEY",  # CTO only
        }:
            child_env.pop(k, None)

    cmd = build_grok_command(
        worktree=worktree,
        session_id=session_id,
        prompt=prompt,
        max_turns=cfg.budgets.grok_max_turns,
        always_approve=always_approve,
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
        # Controlled mock: create a small evidence file inside allowed path if possible
        evidence = worktree / "output" / "cto" / "cycles" / cycle_id
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "mock_execution.txt").write_text(
            f"mock execution for {decision.get('work_id')}\n",
            encoding="utf-8",
        )
        result["status"] = "mock_completed"
        result["mock_artifact"] = str(evidence / "mock_execution.txt")
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result)

    # Live Grok execution
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
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["reason"] = safe_exception_message(exc)

    (cdir / "execution.json").write_text(
        json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return redact_obj(result)
