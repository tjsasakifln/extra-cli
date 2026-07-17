#!/usr/bin/env python3
"""Simple file lock for evergreen cycle."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def lock_path(squad_root: Path) -> Path:
    return squad_root / "state" / "locks" / "cycle.lock"


def acquire(squad_root: Path, owner: str, force: bool = False) -> int:
    lp = lock_path(squad_root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    if lp.exists() and not force:
        data = json.loads(lp.read_text(encoding="utf-8"))
        print(json.dumps({"ok": False, "error": "LOCK_HELD", "lock": data}, indent=2))
        return 1
    payload = {
        "owner": owner,
        "pid": os.getpid(),
        "acquired_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    lp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # stderr so force-next --json stays pure on stdout
    print(json.dumps({"ok": True, "lock": payload}, indent=2), file=sys.stderr)
    return 0


def release(squad_root: Path) -> int:
    lp = lock_path(squad_root)
    if lp.exists():
        lp.unlink()
    print(json.dumps({"ok": True, "released": True}, indent=2), file=sys.stderr)
    return 0


def status(squad_root: Path) -> int:
    lp = lock_path(squad_root)
    if not lp.exists():
        print(json.dumps({"held": False}, indent=2))
        return 0
    print(json.dumps({"held": True, "lock": json.loads(lp.read_text(encoding="utf-8"))}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["acquire", "release", "status"])
    p.add_argument("--squad", default="squads/extra-dod-roi")
    p.add_argument("--owner", default="roi-orchestrator")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.squad)
    if args.action == "acquire":
        return acquire(root, args.owner, force=args.force)
    if args.action == "release":
        return release(root)
    return status(root)


if __name__ == "__main__":
    raise SystemExit(main())
