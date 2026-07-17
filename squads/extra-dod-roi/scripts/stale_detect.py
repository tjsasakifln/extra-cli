#!/usr/bin/env python3
"""Detect stale squad state vs current HEAD/DOD/PRs."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=str(root), text=True).strip()
    except Exception:
        return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=".")
    p.add_argument("--state", default=None, help="Prior snapshot or ranking JSON")
    args = p.parse_args(argv)
    root = Path(args.repo).resolve()
    current = {
        "head": git(root, "rev-parse", "HEAD"),
        "dod_hash": sha256_file(root / "DOD.md"),
    }
    stale = False
    reasons = []
    prior = {}
    if args.state and Path(args.state).is_file():
        prior = json.loads(Path(args.state).read_text(encoding="utf-8"))
        prior_git = prior.get("git") or prior
        if prior_git.get("head") and prior_git.get("head") != current["head"]:
            stale = True
            reasons.append("HEAD changed")
        prior_dod = prior.get("dod_hash") or (prior.get("dod") or {}).get("sha256")
        if prior_dod and prior_dod != current["dod_hash"]:
            stale = True
            reasons.append("DOD.md hash changed")
    print(json.dumps({"stale": stale, "reasons": reasons, "current": current, "prior_keys": list(prior.keys())[:20]}, indent=2))
    return 2 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
