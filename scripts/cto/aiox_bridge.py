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
        # Keep head+tail so rank-next "### 1. cand-..." lines are not lost
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


# Aliases that map alternate names → required agent id (not invalid freestyle aliases).
_AGENT_ALIASES: dict[str, str] = {
    "po": "po",
    "@po": "po",
    "pax": "po",
    "dev": "dev",
    "@dev": "dev",
    "dex": "dev",
    "qa": "qa",
    "@qa": "qa",
    "quinn": "qa",
    "devops": "devops",
    "@devops": "devops",
    "gage": "devops",
    "roi-orchestrator": "roi-orchestrator",
    "codebase-cartographer": "codebase-cartographer",
    "dod-truth-auditor": "dod-truth-auditor",
    "critical-path-roi-planner": "critical-path-roi-planner",
    "delivery-engineer": "delivery-engineer",
    "adversarial-qa-auditor": "adversarial-qa-auditor",
    "evidence-release-steward": "evidence-release-steward",
}

# Skills / instruction paths required for the canonical sequence
_REQUIRED_SKILL_HINTS = (
    "aiox-story-cycle",
    "develop-story",
    "validate-story-draft",
    "review-story",
    "aiox-publish",
)


def _discover_agents_on_disk(root: Path) -> dict[str, list[str]]:
    """Map agent_id → list of source paths where it was found."""
    found: dict[str, list[str]] = {}
    search_roots = [
        root / "squads" / "extra-dod-roi" / "agents",
        root / ".claude" / "skills" / "AIOX" / "agents",
        root / ".aiox-core" / "development" / "agents",
        root / "agents",
    ]
    for base in search_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".yaml", ".yml", ".json"}:
                continue
            stem = path.stem.lower().replace("_", "-")
            # agent folders: agents/dev/MEMORY.md → dev
            parent_name = path.parent.name.lower().replace("_", "-")
            candidates = {stem, parent_name}
            for cand in candidates:
                canon = _AGENT_ALIASES.get(cand) or (
                    cand if cand in REQUIRED_AGENTS else None
                )
                if canon and canon in REQUIRED_AGENTS:
                    found.setdefault(canon, []).append(
                        str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
                    )
    # AGENTS.md alone is NOT an agent proof — only listed for diagnostics
    return found


def _discover_skills_on_disk(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    skill_roots = [
        root / ".claude" / "skills",
        root / ".agents" / "skills",
    ]
    for base in skill_roots:
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.is_file():
                    found[child.name] = str(skill_md.relative_to(root))
    return found


def preflight_aiox_discovery(
    inspect: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Fail closed unless every REQUIRED_AGENTS entry is discoverable on disk.

    ``AGENTS.md`` or a lone AIOX folder is **not** sufficient proof.
    Grok inspect JSON may enrich found_agents but cannot replace filesystem proof.
    """
    root = root or repo_root()
    missing: list[str] = []
    found_map = _discover_agents_on_disk(root)
    found_agents = sorted(found_map.keys())
    sources: dict[str, list[str]] = dict(found_map)
    inspect_names: list[str] = []
    project_instructions: list[Any] = []
    if inspect:
        project_instructions = list(inspect.get("projectInstructions") or [])
        for key in ("agents", "discoveredAgents", "agentDefinitions"):
            val = inspect.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and item.get("name"):
                        inspect_names.append(str(item["name"]))
                    elif isinstance(item, str):
                        inspect_names.append(item)
    # Map inspect names through aliases (diagnostic only)
    for name in inspect_names:
        key = name.lower().lstrip("@").replace("_", "-")
        canon = _AGENT_ALIASES.get(key) or _AGENT_ALIASES.get(name.lower())
        if canon and canon not in found_map:
            # inspect-only hits do not count as proof
            sources.setdefault(f"inspect-only:{canon}", []).append("grok-inspect")

    for agent in REQUIRED_AGENTS:
        if agent not in found_map:
            missing.append(agent)

    skills = _discover_skills_on_disk(root)
    missing_skills = [s for s in _REQUIRED_SKILL_HINTS if s not in skills]
    # Skills are soft if agents fully present? Goal says validate skills for canonical sequence.
    if missing_skills:
        for s in missing_skills:
            missing.append(f"skill:{s}")

    paths = [str(p.get("path") or "") for p in project_instructions if isinstance(p, dict)]
    has_aiox_rules = any(".claude/rules" in p or "aiox" in p.lower() for p in paths) or (
        (root / ".claude" / "rules").is_dir()
    )
    has_agents_md = any(
        p.endswith("AGENTS.md") or p.endswith("Agents.md") for p in paths
    ) or (root / "AGENTS.md").is_file() or (root / "Agents.md").is_file()

    # Explicit: AGENTS.md alone never makes ok=True
    agent_ok = all(a in found_map for a in REQUIRED_AGENTS)
    skill_ok = all(s in skills for s in _REQUIRED_SKILL_HINTS)
    ok = agent_ok and skill_ok and len(missing) == 0

    # Duplicates / invalid aliases report
    invalid_aliases = [
        n for n in inspect_names
        if n.lower().lstrip("@").replace("_", "-") not in _AGENT_ALIASES
        and n.lower().lstrip("@") not in REQUIRED_AGENTS
    ]

    return {
        "ok": ok,
        "missing": missing,
        "found_agents": found_agents,
        "agent_sources": sources,
        "skills_found": sorted(skills.keys()),
        "missing_skills": missing_skills,
        "has_aiox_rules": has_aiox_rules,
        "has_agents_md": has_agents_md,
        "agents_md_insufficient": True,
        "invalid_aliases": invalid_aliases[:20],
        "required_agents": list(REQUIRED_AGENTS),
        "canonical_sequence": list(CANONICAL_SEQUENCE),
        "note": (
            "Every REQUIRED_AGENTS entry must resolve to a file under squads/ or "
            ".claude/skills/AIOX/. AGENTS.md alone is never sufficient. Partial "
            "preflight cannot start an executable cycle."
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
