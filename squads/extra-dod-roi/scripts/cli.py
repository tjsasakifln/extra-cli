#!/usr/bin/env python3
"""Unified CLI for extra-dod-roi squad commands.

Examples:
  python squads/extra-dod-roi/scripts/cli.py force-next   # FOOL-PROOF entry (AIOX-bound)
  python squads/extra-dod-roi/scripts/cli.py status
  python squads/extra-dod-roi/scripts/cli.py rank-next
  python squads/extra-dod-roi/scripts/cli.py scan-state
  python squads/extra-dod-roi/scripts/cli.py audit-dod --summary
  python squads/extra-dod-roi/scripts/cli.py show-blockers
  python squads/extra-dod-roi/scripts/cli.py enforce implement
  python squads/extra-dod-roi/scripts/cli.py advance --to STORY_READY --actor po
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent


def run_py(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPT_DIR / script), *args]
    return subprocess.call(cmd)


def cmd_status(_: argparse.Namespace) -> int:
    lock = SQUAD_DIR / "state" / "locks" / "cycle.lock"
    latest_rank = SQUAD_DIR / "state" / "rankings" / "latest.json"
    status = {
        "squad": "extra-dod-roi",
        "lock_held": lock.is_file(),
        "latest_ranking": None,
        "commands": {
            "read_only": [
                "status", "scan-state", "audit-dod", "rank-next",
                "explain-next", "plan-next", "verify-current", "show-blockers",
            ],
            "write_require_permission": ["force-next", "execute-next", "run-cycle", "resume-cycle"],
            "foolproof_entry": "force-next",
        },
    }
    if latest_rank.is_file():
        data = json.loads(latest_rank.read_text(encoding="utf-8"))
        status["latest_ranking"] = {
            "generated_at": data.get("generated_at"),
            "selected_id": data.get("selected_id"),
            "top": [
                {"id": c.get("id"), "roi": c.get("roi")}
                for c in (data.get("ranking") or [])[:5]
            ],
        }
    cycle = SQUAD_DIR / "state" / "cycles" / "current.json"
    if cycle.is_file():
        cdata = json.loads(cycle.read_text(encoding="utf-8"))
        status["cycle"] = {
            "cycle_id": cdata.get("cycle_id"),
            "phase": cdata.get("phase"),
            "next_phase_required": cdata.get("next_phase_required"),
            "selected_id": cdata.get("selected_id"),
            "story_id": cdata.get("story_id"),
            "status": cdata.get("status"),
            "foolproof": cdata.get("foolproof"),
        }
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="extra-roi")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    p_scan = sub.add_parser("scan-state")
    p_scan.add_argument("--fetch", action="store_true")
    p_scan.add_argument("--write", action="store_true")

    p_audit = sub.add_parser("audit-dod")
    p_audit.add_argument("--summary", action="store_true")
    p_audit.add_argument("--write", action="store_true")

    p_rank = sub.add_parser("rank-next")
    p_rank.add_argument("--top", type=int, default=5)
    p_rank.add_argument("--write-state", action="store_true")
    p_rank.add_argument("--json", action="store_true")
    p_rank.add_argument("--fetch", action="store_true")

    sub.add_parser("explain-next")
    sub.add_parser("show-blockers")

    p_lock = sub.add_parser("lock")
    p_lock.add_argument("action", choices=["acquire", "release", "status"])

    p_force = sub.add_parser("force-next", help="FOOL-PROOF: bind ranking[0] to AIOX SDC")
    p_force.add_argument("--fetch", action="store_true")
    p_force.add_argument("--json", action="store_true")
    p_force.add_argument("--skip-lock", action="store_true")

    p_enf = sub.add_parser("enforce", help="Fail-closed gate for a phase action")
    p_enf.add_argument(
        "action",
        choices=[
            "force-next", "run-cycle", "rank", "card", "materialize-story",
            "implement", "execute-next", "qa", "po-close", "publish", "dod-update",
        ],
    )

    p_adv = sub.add_parser("advance", help="Advance cycle state machine (legal transitions only)")
    p_adv.add_argument("--to", required=True)
    p_adv.add_argument("--actor", default="roi-orchestrator")
    p_adv.add_argument("--evidence-json", default=None)

    sub.add_parser("cycle", help="Show current cycle state")

    args = p.parse_args(argv)

    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "scan-state":
        a = []
        if args.fetch:
            a.append("--fetch")
        if args.write:
            a.append("--write")
        return run_py("snapshot_state.py", a)
    if args.cmd == "audit-dod":
        a = []
        if args.summary:
            a.append("--summary-only")
        if args.write:
            a.append("--write")
        return run_py("parse_dod.py", a)
    if args.cmd == "rank-next":
        a = [f"--top={args.top}"]
        if args.write_state:
            a.append("--write-state")
        if args.json:
            a.append("--json")
        if args.fetch:
            a.append("--fetch")
        return run_py("rank_next_cli.py", a)
    if args.cmd == "explain-next":
        # reuse rank-next top 1 narrative
        return run_py("rank_next_cli.py", ["--top=3"])
    if args.cmd == "show-blockers":
        return run_py("rank_next_cli.py", ["--top=1", "--json"])  # includes blockers; user reads blockers key
    if args.cmd == "lock":
        return run_py("cycle_lock.py", [args.action, f"--squad={SQUAD_DIR}"])
    if args.cmd == "force-next":
        a = []
        if args.fetch:
            a.append("--fetch")
        if args.json:
            a.append("--json")
        if args.skip_lock:
            a.append("--skip-lock")
        return run_py("force_next.py", a)
    if args.cmd == "enforce":
        return run_py("enforce_aiox_path.py", [args.action])
    if args.cmd == "advance":
        a = ["advance", f"--to={args.to}", f"--actor={args.actor}"]
        if args.evidence_json:
            a.append(f"--evidence-json={args.evidence_json}")
        return run_py("cycle_state.py", a)
    if args.cmd == "cycle":
        return run_py("cycle_state.py", ["show"])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
