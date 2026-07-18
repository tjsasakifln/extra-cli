#!/usr/bin/env python3
"""Global main-writer lock for main-direct integration mode.

Only one writer may hold the lock. Lock is required for product mutations on main.
Does not replace cycle.lock; both may be used (cycle for phase machine, this for write ownership).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
DEFAULT_TTL_MIN = 120


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_s() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def lock_path(squad_root: Path) -> Path:
    return squad_root / "state" / "locks" / "main-writer.lock"


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def load_lock(squad_root: Path) -> dict[str, Any] | None:
    lp = lock_path(squad_root)
    if not lp.is_file():
        return None
    try:
        return json.loads(lp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"corrupt": True, "path": str(lp)}


def is_expired(data: dict[str, Any]) -> bool:
    exp = data.get("expires_at")
    dt = _parse_ts(exp) if exp else None
    if not dt:
        return False
    return utcnow() > dt


def acquire(
    squad_root: Path,
    *,
    agent: str,
    task: str,
    intended_files: list[str] | None = None,
    head: str | None = None,
    ttl_minutes: int = DEFAULT_TTL_MIN,
    force: bool = False,
    recovery_command: str | None = None,
) -> int:
    lp = lock_path(squad_root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    existing = load_lock(squad_root)
    if existing and not force:
        if existing.get("corrupt"):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "LOCK_CORRUPT",
                        "lock": existing,
                        "recovery": "main_writer_lock.py release --force",
                    },
                    indent=2,
                )
            )
            return 1
        if not is_expired(existing):
            print(
                json.dumps(
                    {"ok": False, "error": "LOCK_HELD", "lock": existing},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 1
        # expired → allow acquire (steal with note)
    now = utcnow()
    expires = now + timedelta(minutes=ttl_minutes)
    payload = {
        "version": "1.0.0",
        "agent": agent,
        "task": task,
        "pid": os.getpid(),
        "timestamp": utcnow_s(),
        "acquired_at": utcnow_s(),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_minutes": ttl_minutes,
        "intended_files": intended_files or [],
        "head_at_start": head or "",
        "state": "HELD",
        "mode": "main-direct",
        "recovery_command": recovery_command
        or "python3 squads/extra-dod-roi/scripts/main_writer_lock.py release --force",
        "stolen_from_expired": bool(existing and is_expired(existing)),
    }
    lp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "lock": payload}, indent=2, ensure_ascii=False), file=sys.stderr)
    return 0


def release(squad_root: Path, *, force: bool = False, agent: str | None = None) -> int:
    lp = lock_path(squad_root)
    if not lp.exists():
        print(json.dumps({"ok": True, "released": False, "reason": "not_held"}, indent=2))
        return 0
    data = load_lock(squad_root) or {}
    if not force and agent and data.get("agent") and data.get("agent") != agent:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "LOCK_OWNER_MISMATCH",
                    "lock": data,
                    "requested_by": agent,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1
    lp.unlink(missing_ok=True)
    print(json.dumps({"ok": True, "released": True, "previous": data}, indent=2, ensure_ascii=False))
    return 0


def status(squad_root: Path) -> int:
    data = load_lock(squad_root)
    if not data:
        print(json.dumps({"held": False, "mode": "main-direct"}, indent=2))
        return 0
    exp = is_expired(data)
    print(
        json.dumps(
            {
                "held": not exp,
                "expired": exp,
                "lock": data,
                "mode": "main-direct",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if not exp else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="main-direct global writer lock")
    p.add_argument("action", choices=["acquire", "release", "status"])
    p.add_argument("--squad", default=str(SQUAD_DIR))
    p.add_argument("--agent", default="roi-orchestrator")
    p.add_argument("--task", default="")
    p.add_argument("--files", default="", help="comma-separated intended files")
    p.add_argument("--head", default="")
    p.add_argument("--ttl-minutes", type=int, default=DEFAULT_TTL_MIN)
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    squad = Path(args.squad)
    if args.action == "acquire":
        if not args.task:
            print(json.dumps({"ok": False, "error": "task required"}, indent=2))
            return 2
        files = [x.strip() for x in args.files.split(",") if x.strip()]
        return acquire(
            squad,
            agent=args.agent,
            task=args.task,
            intended_files=files,
            head=args.head or None,
            ttl_minutes=args.ttl_minutes,
            force=args.force,
        )
    if args.action == "release":
        return release(squad, force=args.force, agent=args.agent)
    return status(squad)


if __name__ == "__main__":
    raise SystemExit(main())
