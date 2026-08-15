"""CLI: python -m scripts.market_penetration snapshot

Read-only assembly of the versioned ICP / reachability / Warmbly snapshot.
Does not send mail, mutate Warmbly, or invent TAM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.market_penetration.baseline import build_operational_snapshot, emit_snapshot
from scripts.market_penetration.facts import (
    DEFAULT_WARMBLY_MAX_AGE_DAYS,
    join_from_paths,
)
from scripts.market_penetration.icp_denominator import DEFAULT_RULES, PenetrationError
from scripts.warmbly_bridge.io_jsonl import InputError

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.market_penetration",
        description=(
            "Build a reproducible CONFENGE penetration snapshot from universe, "
            "DUI, and optional Warmbly facts. extra-cli is authority only through "
            "ACTIONABLE_ROUTE."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="Join facts and write JSON + CSV + executive report")
    snap.add_argument("--universe", required=True, help="Universe JSON/JSONL (canonical accounts)")
    snap.add_argument("--universe-manifest", default=None, help="Optional universe manifest for universe_version")
    snap.add_argument("--dui", default=None, help="DUI accounts dir, cards.json, or JSONL")
    snap.add_argument("--warmbly", default=None, help="Warmbly outcome JSON/JSONL")
    snap.add_argument(
        "--warmbly-absent",
        action="store_true",
        help="Declare Warmbly facts unavailable. CONTACTED+ become 0 observed.",
    )
    snap.add_argument("--as-of", required=True, help="Snapshot date (YYYY-MM-DD)")
    snap.add_argument("--out", required=True, help="Output directory (not committed)")
    snap.add_argument(
        "--max-warmbly-age-days",
        type=int,
        default=DEFAULT_WARMBLY_MAX_AGE_DAYS,
        help=f"Fail-closed if latest Warmbly event is older than this (default {DEFAULT_WARMBLY_MAX_AGE_DAYS})",
    )
    return parser


def cmd_snapshot(args: argparse.Namespace) -> int:
    if bool(args.warmbly) == bool(args.warmbly_absent):
        _print({"ok": False, "error": "pass exactly one of --warmbly or --warmbly-absent"})
        return EXIT_USAGE
    try:
        join = join_from_paths(
            as_of=args.as_of,
            universe_path=Path(args.universe),
            dui_path=Path(args.dui) if args.dui else None,
            warmbly_path=Path(args.warmbly) if args.warmbly else None,
            warmbly_absent=bool(args.warmbly_absent),
            universe_manifest_path=Path(args.universe_manifest) if args.universe_manifest else None,
            max_warmbly_age_days=args.max_warmbly_age_days,
        )
        payload = build_operational_snapshot(
            join,
            as_of=args.as_of,
            rules=DEFAULT_RULES,
            inputs={
                "universe": args.universe,
                "universe_manifest": args.universe_manifest,
                "dui": args.dui,
                "warmbly": args.warmbly,
                "warmbly_absent": bool(args.warmbly_absent),
            },
        )
        paths = emit_snapshot(payload, Path(args.out))
    except InputError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    except PenetrationError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_FAIL
    _print(
        {
            "ok": True,
            "as_of": payload["as_of"],
            "universe_version": payload["universe_version"],
            "invented_tam": payload["policy"]["invented_tam"],
            "counts": payload["counts"],
            "hashes": payload["hashes"],
            "paths": paths,
            "warmbly_status": payload["policy"]["warmbly_status"],
        }
    )
    return EXIT_OK


def _print(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        return cmd_snapshot(args)
    parser.error(f"unknown command {args.command}")
    return EXIT_USAGE
