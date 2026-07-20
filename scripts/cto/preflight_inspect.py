"""Preflight using `grok inspect --json` — fail closed if AIOX surfaces missing."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.cto.aiox_bridge import preflight_aiox_discovery
from scripts.cto.paths import repo_root


def run_grok_inspect(*, root: Path | None = None, timeout: int = 60) -> dict[str, Any]:
    root = root or repo_root()
    grok = shutil.which("grok")
    if not grok:
        return {"ok": False, "error": "grok binary not found", "inspect": None}
    try:
        proc = subprocess.run(
            [grok, "inspect", "--json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "grok inspect timeout", "inspect": None}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"grok inspect exit {proc.returncode}: {(proc.stderr or '')[:500]}",
            "inspect": None,
            "stdout_tail": (proc.stdout or "")[-1000:],
        }
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid inspect json: {exc}", "inspect": None}
    return {
        "ok": True,
        "inspect": data,
        "grok_version": data.get("grokVersion"),
        "channel": data.get("channel"),
    }


def preflight_for_cycle(*, root: Path | None = None, require_grok: bool = True) -> dict[str, Any]:
    """Fail closed when required AIOX/project discovery is absent."""
    root = root or repo_root()
    checks: list[dict[str, Any]] = []
    inspect_res = run_grok_inspect(root=root)
    if require_grok and not inspect_res.get("ok"):
        return {
            "ok": False,
            "error": inspect_res.get("error") or "grok inspect failed",
            "checks": checks,
            "inspect": inspect_res,
        }
    discovery = preflight_aiox_discovery(inspect_res.get("inspect"))
    checks.append({"name": "aiox_discovery", **discovery})
    # Structural paths (do not copy agent definitions)
    required_paths = [
        root / "AGENTS.md",
        root / "squads" / "extra-dod-roi" / "scripts" / "cli.py",
        root / ".cto" / "authorized_tests.yaml",
        root / ".cto" / "policies.yaml",
    ]
    missing_paths = [str(p) for p in required_paths if not p.exists()]
    checks.append(
        {
            "name": "required_paths",
            "ok": not missing_paths,
            "missing": missing_paths,
        }
    )
    ok = discovery.get("ok") and not missing_paths and (
        inspect_res.get("ok") or not require_grok
    )
    return {
        "ok": ok,
        "checks": checks,
        "inspect": {
            "grok_version": inspect_res.get("grok_version"),
            "channel": inspect_res.get("channel"),
            "ok": inspect_res.get("ok"),
            "error": inspect_res.get("error"),
        },
        "error": None if ok else "preflight_failed",
    }
