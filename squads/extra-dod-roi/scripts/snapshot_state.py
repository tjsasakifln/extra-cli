#!/usr/bin/env python3
"""Deterministic project state snapshot for extra-dod-roi.

Read-only toward product tree. Optional write only under squad state/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SQUAD_REL = Path("squads/extra-dod-roi")


def repo_root_from(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists() and (p / "DOD.md").exists():
            return p
        if (p / ".git").exists() and (p / "squads" / "extra-dod-roi").exists():
            return p
    return cur


def run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def list_dir_names(path: Path, limit: int = 200) -> list[str]:
    if not path.is_dir():
        return []
    names = sorted(p.name for p in path.iterdir())
    return names[:limit]


def collect_snapshot(root: Path, fetch_remote: bool = False) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap: dict[str, Any] = {
        "version": "1.0.0",
        "generated_at": now,
        "repo_root": str(root),
        "confidence": "high",
        "git": {},
        "dod": {},
        "structure": {},
        "open_prs": [],
        "branches": [],
        "warnings": [],
    }

    if fetch_remote:
        code, _, err = run(["git", "fetch", "--prune", "--quiet"], root, timeout=120)
        if code != 0:
            snap["warnings"].append(f"git fetch failed: {err or code}")
            snap["confidence"] = "partial"

    code, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    code2, head, _ = run(["git", "rev-parse", "HEAD"], root)
    code3, main_head, _ = run(["git", "rev-parse", "origin/main"], root)
    if code3 != 0:
        code3, main_head, _ = run(["git", "rev-parse", "main"], root)
    code4, dirty, _ = run(["git", "status", "--porcelain"], root)
    code5, log, _ = run(["git", "log", "--oneline", "-10"], root)

    snap["git"] = {
        "branch": branch if code == 0 else None,
        "head": head if code2 == 0 else None,
        "main_head": main_head if code3 == 0 else None,
        "dirty_count": len(dirty.splitlines()) if code4 == 0 and dirty else 0,
        "dirty_sample": dirty.splitlines()[:30] if code4 == 0 else [],
        "recent_commits": log.splitlines() if code5 == 0 else [],
        "on_main": branch in ("main", "master") if code == 0 else None,
        "ahead_of_main": None,
    }
    if snap["git"]["head"] and snap["git"]["main_head"]:
        c, merge_base, _ = run(
            ["git", "merge-base", snap["git"]["head"], snap["git"]["main_head"]], root
        )
        c2, ahead, _ = run(
            ["git", "rev-list", "--count", f'{snap["git"]["main_head"]}..{snap["git"]["head"]}'],
            root,
        )
        c3, behind, _ = run(
            ["git", "rev-list", "--count", f'{snap["git"]["head"]}..{snap["git"]["main_head"]}'],
            root,
        )
        snap["git"]["merge_base"] = merge_base if c == 0 else None
        snap["git"]["ahead"] = int(ahead) if c2 == 0 and ahead.isdigit() else None
        snap["git"]["behind"] = int(behind) if c3 == 0 and behind.isdigit() else None

    dod = root / "DOD.md"
    snap["dod"] = {
        "path": "DOD.md",
        "exists": dod.is_file(),
        "sha256": sha256_file(dod),
        "bytes": dod.stat().st_size if dod.is_file() else 0,
        "lines": sum(1 for _ in dod.open(encoding="utf-8", errors="replace")) if dod.is_file() else 0,
    }

    # structure inventory
    snap["structure"] = {
        "scripts_top": list_dir_names(root / "scripts"),
        "tests_top": list_dir_names(root / "tests"),
        "docs_operations": list_dir_names(root / "docs" / "operations"),
        "docs_ops": list_dir_names(root / "docs" / "ops"),
        "ci_workflows": list_dir_names(root / ".github" / "workflows"),
        "migrations": list_dir_names(root / "supabase" / "migrations")
        or list_dir_names(root / "db" / "migrations")
        or list_dir_names(root / "migrations"),
        "makefile_exists": (root / "Makefile").is_file(),
        "squads": list_dir_names(root / "squads"),
    }

    # branches
    c, br, _ = run(["git", "branch", "-a", "--list"], root)
    if c == 0:
        snap["branches"] = [b.strip().lstrip("* ").strip() for b in br.splitlines() if b.strip()][:80]

    # PRs
    c, pr_json, err = run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,baseRefName,url,updatedAt,mergeable",
            "--limit",
            "30",
        ],
        root,
        timeout=45,
    )
    if c == 0 and pr_json:
        try:
            snap["open_prs"] = json.loads(pr_json)
        except json.JSONDecodeError:
            snap["warnings"].append("failed to parse gh pr list")
            snap["confidence"] = "partial"
    else:
        snap["warnings"].append(f"gh pr list unavailable: {err or c}")
        snap["confidence"] = "partial" if snap["confidence"] == "high" else snap["confidence"]
        # still try PR 12 specifically via local knowledge of branches
        if any("pre-vps-final-truth-gate" in b for b in snap["branches"]):
            snap["open_prs"].append(
                {
                    "number": 12,
                    "title": "fix(resilience): pre-VPS final truth gate — destroy false greens",
                    "headRefName": "fix/pre-vps-final-truth-gate-20260717",
                    "baseRefName": "main",
                    "url": "https://github.com/tjsasakifln/extra-consultoria/pull/12",
                    "inferred_local": True,
                }
            )

    # key ops docs presence
    ops = root / "docs" / "operations"
    snap["ops_truth_docs"] = {
        name: (ops / name).is_file()
        for name in [
            "PRE-VPS-FINAL-TRUTH.md",
            "PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md",
            "PRE-VPS-READINESS.md",
            "LOCAL-RESILIENCE-RUNBOOK.md",
        ]
    }
    return snap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot project state (read-only product tree)")
    parser.add_argument("--repo", type=str, default=None, help="Repo root")
    parser.add_argument("--fetch", action="store_true", help="git fetch --prune")
    parser.add_argument("--write", action="store_true", help="Write under squad state/snapshots")
    parser.add_argument("--stdout", action="store_true", default=True)
    parser.add_argument("-o", "--output", type=str, default=None)
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve() if args.repo else repo_root_from()
    snap = collect_snapshot(root, fetch_remote=args.fetch)
    text = json.dumps(snap, indent=2, ensure_ascii=False)

    if args.write or args.output:
        if args.output:
            out = Path(args.output)
        else:
            out_dir = root / SQUAD_REL / "state" / "snapshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = snap["generated_at"].replace(":", "").replace("-", "")
            out = out_dir / f"{ts}-snapshot.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
