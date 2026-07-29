#!/usr/bin/env python3
"""Canonical incremental update for historical contracts (PNCP).

Uses the hardened pilot runner for a short lookback window (default 7 days)
so upsert, checkpoint isolation, page retries, and evidence artifacts stay
consistent with the 90d pilot path.

Exit codes:
  0 — status=success and zero page/window failures
  1 — incomplete / failed / unproven
  2 — usage error
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("contracts_incremental")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dsn",
        default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"),
    )
    ap.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("CONTRACTS_INCREMENTAL_DAYS", "7")),
        help="Lookback days with overlap for late updates (default 7)",
    )
    ap.add_argument(
        "--output-json",
        type=Path,
        default=Path("output/contracts/incremental-latest.json"),
    )
    ap.add_argument(
        "--checkpoint-dir",
        default="data/contracts_checkpoints/incremental",
    )
    ap.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Clear incremental checkpoint before run",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.dsn and not args.dry_run:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    if args.days < 1 or args.days > 90:
        print("ERROR: --days must be in 1..90 for incremental path", file=sys.stderr)
        return 2

    from scripts.crawl.run_contracts_90d_pilot import (
        _configure_checkpoint_dir,
        load_checkpoint,
        run_pilot,
        save_checkpoint,
    )

    started = datetime.now(UTC)
    _configure_checkpoint_dir(args.checkpoint_dir)
    if args.reset_checkpoint:
        cp = load_checkpoint("full")
        cp.completed_windows = []
        cp.current_window_start = None
        cp.total_windows_completed = 0
        cp.total_windows_failed = 0
        cp.total_contracts_fetched = 0
        cp.last_error = None
        # Clear bound run_id so the next pilot can rebind without foreign-resume
        # hard-fail (weekly cycle always generates a new contracts run_id).
        meta = dict(cp.meta or {})
        old_run = meta.get("run_id")
        if old_run:
            prev = list(meta.get("previous_run_ids") or [])
            if old_run not in prev:
                prev.append(old_run)
            meta["previous_run_ids"] = prev
            meta.pop("run_id", None)
            meta["reset_cleared_run_id"] = True
        meta.pop("foreign_resume", None)
        meta["incremental_days"] = int(args.days)
        meta["campaign_role"] = "historical_contracts_incremental"
        cp.meta = meta
        save_checkpoint(cp)
        logger.info("Incremental checkpoint reset")
    else:
        # Fail-closed: never silently resume a foreign or wrong-parameter checkpoint.
        # Each CLI invocation gets a new pilot run_id; resuming completed_windows
        # from another run requires explicit CONTRACTS_ALLOW_CROSS_RUN_RESUME=1
        # and matching incremental_days.
        cp = load_checkpoint("full")
        meta = dict(cp.meta or {})
        existing_run = meta.get("run_id")
        bound_days = meta.get("incremental_days")
        has_progress = bool(cp.completed_windows) or bool(existing_run)
        if has_progress:
            allow_cross = os.getenv("CONTRACTS_ALLOW_CROSS_RUN_RESUME", "0") == "1"
            if bound_days is not None and int(bound_days) != int(args.days):
                print(
                    "ERROR: checkpoint incremental_days="
                    f"{bound_days} != --days={args.days}; "
                    "refusing wrong-window resume. Use --reset-checkpoint.",
                    file=sys.stderr,
                )
                return 1
            if existing_run and not allow_cross:
                print(
                    f"ERROR: checkpoint bound to run_id={existing_run!r}; "
                    "refusing silent foreign resume. Use --reset-checkpoint "
                    "or set CONTRACTS_ALLOW_CROSS_RUN_RESUME=1.",
                    file=sys.stderr,
                )
                return 1
            if not allow_cross and cp.completed_windows:
                # No run_id but leftover windows from another process/context
                print(
                    "ERROR: checkpoint has completed_windows without explicit "
                    "cross-run allow; refusing silent resume. "
                    "Use --reset-checkpoint or CONTRACTS_ALLOW_CROSS_RUN_RESUME=1.",
                    file=sys.stderr,
                )
                return 1

    report = run_pilot(
        dsn=args.dsn,
        days=args.days,
        output_json=str(args.output_json),
        checkpoint_dir=args.checkpoint_dir,
        dry_run=bool(args.dry_run),
    )
    # Persist parameter binding for the next invocation's wrong-window guard.
    try:
        cp_after = load_checkpoint("full")
        meta_after = dict(cp_after.meta or {})
        meta_after["incremental_days"] = int(args.days)
        meta_after["campaign_role"] = "historical_contracts_incremental"
        cp_after.meta = meta_after
        save_checkpoint(cp_after)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not annotate incremental checkpoint meta: %s", exc)
    # Annotate as incremental product surface
    report["command"] = "run_contracts_incremental"
    report["incremental_days"] = args.days
    report["campaign_role"] = "historical_contracts_incremental"
    report["claims_forbidden"] = [
        "3y backfill complete",
        "HISTORICAL_CONTRACTS_OPERATIONAL_COVERAGE_PASS without dual gate after projection",
    ]
    report["annotated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    report["started_at_wrapper"] = started.isoformat().replace("+00:00", "Z")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    status = str(report.get("status") or "")
    totals = report.get("totals") or {}
    ok = (
        status == "success"
        and int(totals.get("windows_failed") or 0) == 0
        and int(totals.get("page_errors") or 0) == 0
    )
    logger.info(
        "incremental done status=%s ok=%s inserted=%s",
        status,
        ok,
        totals.get("inserted"),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
