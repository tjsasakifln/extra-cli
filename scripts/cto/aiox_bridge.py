"""Thin adapter: CTO Autopilot → AIOX + squad extra-dod-roi.

Does NOT reimplement ranking, story format, or engineering workflow.
Invokes existing squad CLI and records agent handoff intents for Grok.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, repo_root
from scripts.cto.redaction import redact_obj

# Required AIOX/squad agents for a full cycle (discovery only — not reimplemented).
REQUIRED_AGENTS = (
    "roi-orchestrator",
    "codebase-cartographer",
    "dod-truth-auditor",
    "critical-path-roi-planner",
    "delivery-engineer",
    "adversarial-qa-auditor",
    "evidence-release-steward",
    "po",
    "dev",
    "qa",
    "devops",
)

CANONICAL_SEQUENCE = (
    "force-next",
    "story-draft",
    "@po",
    "enforce-implement",
    "@dev",
    "@qa",
    "@po",
    "@devops",
    "force-next-rerank",
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_squad(
    args: list[str],
    *,
    root: Path,
    timeout: int = 300,
) -> dict[str, Any]:
    cmd = [sys.executable, "squads/extra-dod-roi/scripts/cli.py", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        stdout = proc.stdout or ""
        parsed: Any = None
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
        head = stdout[:12000]
        tail = stdout[-8000:]
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout_head": head,
            "stdout_tail": tail,
            "stdout_text": head if "### 1." in head else (stdout if len(stdout) < 20000 else head + "\n...\n" + tail),
            "stderr_tail": (proc.stderr or "")[-4000:],
            "json": parsed,
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": -1, "error": "timeout"}
    except FileNotFoundError:
        return {"cmd": cmd, "exit_code": -2, "error": "not_found"}


def preflight_aiox_discovery(inspect: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail closed if Grok/AIOX discovery surfaces are missing.

    Uses grok inspect JSON when provided; does not invent agent copies.
    """
    missing: list[str] = []
    found_agents: list[str] = []
    project_instructions = []
    if inspect:
        project_instructions = list(inspect.get("projectInstructions") or [])
        # Agents may appear under various keys depending on grok version
        for key in ("agents", "discoveredAgents", "agentDefinitions"):
            val = inspect.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and item.get("name"):
                        found_agents.append(str(item["name"]))
                    elif isinstance(item, str):
                        found_agents.append(item)
    # Presence of AIOX skills/rules paths is a soft signal
    paths = [str(p.get("path") or "") for p in project_instructions if isinstance(p, dict)]
    has_aiox_rules = any(".claude/rules" in p or "aiox" in p.lower() for p in paths)
    has_agents_md = any(p.endswith("AGENTS.md") or p.endswith("Agents.md") for p in paths)
    if not has_aiox_rules and not has_agents_md:
        missing.append("AIOX project instructions / AGENTS.md not discovered by grok inspect")
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "found_agents": found_agents,
        "has_aiox_rules": has_aiox_rules,
        "has_agents_md": has_agents_md,
        "required_agents": list(REQUIRED_AGENTS),
        "canonical_sequence": list(CANONICAL_SEQUENCE),
        "note": (
            "CTO does not fork agent definitions; Grok loads AIOX via project "
            "instructions and .claude/skills. Implementation uses delivery-engineer/@dev "
            "prompts; QA uses independent session."
        ),
    }


def squad_status(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    return _run_squad(["status"], root=root)


def squad_rank_next(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    return _run_squad(["rank-next"], root=root, timeout=600)


def squad_audit_dod_summary(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    return _run_squad(["audit-dod", "--summary"], root=root, timeout=600)


def squad_force_next(root: Path | None = None, *, dry_run: bool = True) -> dict[str, Any]:
    """Invoke force-next. dry_run defaults True — live force-next needs human/write path."""
    root = root or repo_root()
    if dry_run:
        # Read-only substitute: rank-next + status (force-next mutates)
        rank = squad_rank_next(root)
        status = squad_status(root)
        return {
            "dry_run": True,
            "action": "force-next-simulated",
            "rank": rank,
            "status": status,
            "note": "Live force-next requires write permission and cycle lock",
        }
    return _run_squad(["force-next"], root=root, timeout=900)


def build_handoff_prompt(
    *,
    phase: str,
    work_id: str | None,
    objective: str,
    allowed_paths: list[str],
    test_ids: list[str],
) -> str:
    """Sealed prompt fragment instructing Grok to act as the named AIOX agent."""
    agent = {
        "implement": "@dev / delivery-engineer",
        "qa": "@qa / adversarial-qa-auditor",
        "po": "@po",
        "devops": "@devops / evidence-release-steward",
        "cartography": "@codebase-cartographer (read-only)",
        "audit": "@dod-truth-auditor (read-only)",
    }.get(phase, "@dev")
    return (
        f"You are operating as {agent} under the Extra Consultoria AIOX protocol.\n"
        f"Work id: {work_id or 'n/a'}\n"
        f"Objective: {objective}\n"
        f"Allowed paths: {', '.join(allowed_paths) or '(none)'}\n"
        f"Authorized test_ids only: {', '.join(test_ids) or '(none)'}\n"
        "Do not merge, push, open PRs, or alter DoD checkboxes without QA evidence.\n"
        "Do not invent free-form shell tests; use only test_ids from the registry.\n"
        "Follow story acceptance criteria exactly. Fail closed on ambiguity.\n"
    )


def record_bridge_snapshot(
    cycle_id: str,
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    root = root or repo_root()
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / "aiox_bridge.json"
    blob = {
        "timestamp_utc": _utc_now(),
        "cycle_id": cycle_id,
        **payload,
    }
    path.write_text(
        json.dumps(redact_obj(blob), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
