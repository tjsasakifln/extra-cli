#!/usr/bin/env python3
"""Canonical incremental update for historical contracts (PNCP).

Uses the hardened pilot runner for a short lookback window (default 7 days)
so upsert, checkpoint isolation, page retries, and evidence artifacts stay
consistent with the 90d pilot path.

Checkpoint contract (v2):
  * ``logical_job_id`` = ``pncp-contracts-incremental`` (stable)
  * ``attempt_run_id`` changes every invocation
  * completed windows resume across attempts without foreign-run hard-fail

Lock domain:
  PostgreSQL advisory fence (EXIT 75 if busy). Host-local flock is not used.

Exit codes:
  0 — status=success and zero page/window failures
  1 — incomplete / failed / unproven
  2 — usage error
  75 — contracts writer lock busy (not a source failure)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.contracts_truth import (  # noqa: E402
    WriterFenceBusyError,
    acquire_national_writer_fence,
    refuse_writer_bypass,
    resolve_checkpoint_dir,
)
from scripts.crawl.contracts_checkpoint_contract import (  # noqa: E402
    LOGICAL_JOB_INCREMENTAL,
    archive_checkpoint,
    checkpoint_file,
    diagnose,
    load_raw,
    migrate_meta,
    save_raw,
)
from scripts.crawl.contracts_writer_lock import EXIT_LOCK_BUSY  # noqa: E402

logger = logging.getLogger("contracts_incremental")

DEFAULT_CHECKPOINT_DIR = "data/contracts_checkpoints/incremental"
DEFAULT_CAMPAIGN = "historical_contracts_incremental"


def current_incremental_window_key(*, days: int, today: date | None = None) -> str:
    """Return the live window key that must be revalidated this attempt."""
    from scripts.crawl.run_contracts_90d_pilot import (
        CONTRACTS_WINDOW_DAYS,
        iter_planned_window_keys,
    )

    end = today or datetime.now(UTC).date()
    keys = iter_planned_window_keys(end - timedelta(days=days), end, CONTRACTS_WINDOW_DAYS)
    if not keys:
        raise ValueError(f"incremental range produced no window for days={days}")
    return keys[-1]


def reopen_current_window(checkpoint: object, *, window_key: str) -> bool:
    """Force the moving incremental window through PNCP on every timer slot.

    Historical windows remain resumable. The one window that reaches the
    current date is different: treating it as permanently complete turns a 4h
    timer into a once-per-day source refresh and lets late arrivals go unseen.
    Removing it before the attempt is fail-closed: a failed revalidation leaves
    it absent; only a clean 93/93-style traversal adds it back.
    """
    completed = list(getattr(checkpoint, "completed_windows", []) or [])
    if window_key not in completed:
        return False
    setattr(checkpoint, "completed_windows", [key for key in completed if key != window_key])
    return True


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
        default=DEFAULT_CHECKPOINT_DIR,
    )
    ap.add_argument(
        "--campaign-id",
        default=os.getenv("CONTRACTS_CAMPAIGN_ID") or DEFAULT_CAMPAIGN,
    )
    ap.add_argument(
        "--logical-job-id",
        default=os.getenv("CONTRACTS_LOGICAL_JOB_ID") or LOGICAL_JOB_INCREMENTAL,
    )
    ap.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Archive and clear completed windows (keeps logical_job_id)",
    )
    ap.add_argument(
        "--skip-lock",
        action="store_true",
        help="Skip writer lock (tests only; never in production timers)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.dsn and not args.dry_run:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    if args.days < 1 or args.days > 90:
        print("ERROR: --days must be in 1..90 for incremental path", file=sys.stderr)
        return 2

    refuse_writer_bypass(
        skip_lock=args.skip_lock,
        env_skip=os.getenv("CONTRACTS_SKIP_WRITER_LOCK", "0"),
    )
    args.checkpoint_dir = str(
        resolve_checkpoint_dir(
            args.checkpoint_dir,
            repo_root=_PROJECT_ROOT,
        )
    )
    fence = None
    if args.dsn and not args.dry_run:
        try:
            fence = acquire_national_writer_fence(args.dsn, skip=args.skip_lock)
        except WriterFenceBusyError:
            print(
                f"LOCK_BUSY: national writer fence held; exit={EXIT_LOCK_BUSY}",
                file=sys.stderr,
            )
            return EXIT_LOCK_BUSY
    try:
        return _run_incremental(args)
    finally:
        if fence is not None:
            fence.release()
            conn = getattr(fence, "_conn", None)
            close = getattr(conn, "close", None)
            if callable(close):
                close()


def _run_incremental(args: argparse.Namespace) -> int:
    from scripts.crawl.run_contracts_90d_pilot import (
        _configure_checkpoint_dir,
        load_checkpoint,
        run_pilot,
        save_checkpoint,
    )

    started = datetime.now(UTC)
    # Do not permanently mutate process env (pollutes subsequent tests/jobs).
    # Pass logical_job_id explicitly into run_pilot instead.

    _configure_checkpoint_dir(args.checkpoint_dir)
    cp_path = checkpoint_file(args.checkpoint_dir, "full")

    # Diagnose + migrate legacy to v2 before pilot bind
    diag = diagnose(args.checkpoint_dir, mode="full")
    if diag.exists and not diag.ok:
        print(f"ERROR: checkpoint unusable: {diag.issues}", file=sys.stderr)
        return 1

    if args.reset_checkpoint:
        if cp_path.is_file():
            archive_checkpoint(cp_path, reason="reset-checkpoint")
            data = load_raw(cp_path)
        else:
            data = {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": [],
                "meta": {},
            }
        data["completed_windows"] = []
        data["current_window_start"] = None
        data["total_windows_completed"] = 0
        data["total_windows_failed"] = 0
        data["total_contracts_fetched"] = 0
        data["last_error"] = None
        data = migrate_meta(
            data,
            logical_job_id=str(args.logical_job_id),
            campaign_id=str(args.campaign_id),
            incremental_days=int(args.days),
            force_campaign=True,
        )
        meta = dict(data.get("meta") or {})
        # Drop attempt binding so first pilot attempt is clean
        old_run = meta.get("run_id") or meta.get("attempt_run_id")
        if old_run:
            prev = list(meta.get("previous_run_ids") or [])
            if old_run not in prev:
                prev.append(old_run)
            meta["previous_run_ids"] = prev
        meta.pop("run_id", None)
        meta.pop("attempt_run_id", None)
        meta["reset_cleared_run_id"] = True
        meta["campaign_role"] = "historical_contracts_incremental"
        data["meta"] = meta
        save_raw(cp_path, data)
        logger.info("Incremental checkpoint reset (archived prior file)")
    elif cp_path.is_file():
        # Ensure v2 identity without wiping progress
        try:
            data = load_raw(cp_path)
            data = migrate_meta(
                data,
                logical_job_id=str(args.logical_job_id),
                campaign_id=str(args.campaign_id),
                incremental_days=int(args.days),
                force_campaign=False,
            )
            save_raw(cp_path, data)
        except Exception as exc:  # noqa: BLE001
            # Wrong campaign/days → hard fail with guidance
            print(
                f"ERROR: checkpoint migrate refused: {exc}. "
                "Use --reset-checkpoint after archive, or "
                "python -m scripts.crawl.contracts_checkpoint_contract repair ...",
                file=sys.stderr,
            )
            return 1

    # A completed moving window is not durable freshness evidence. Revalidate
    # it on every 4h slot; success re-adds it, any failure remains fail-closed.
    checkpoint = load_checkpoint("full")
    refresh_key = current_incremental_window_key(days=int(args.days))
    if reopen_current_window(checkpoint, window_key=refresh_key):
        save_checkpoint(checkpoint)
        logger.info("Reopened current incremental window for refresh: %s", refresh_key)

    report = run_pilot(
        dsn=args.dsn,
        days=args.days,
        output_json=str(args.output_json),
        checkpoint_dir=args.checkpoint_dir,
        dry_run=bool(args.dry_run),
        logical_job_id=str(args.logical_job_id),
        campaign_id=str(args.campaign_id),
    )
    # Persist parameter binding for the next invocation
    try:
        cp_after = load_checkpoint("full")
        meta_after = dict(cp_after.meta or {})
        meta_after["incremental_days"] = int(args.days)
        meta_after["campaign_role"] = "historical_contracts_incremental"
        meta_after["logical_job_id"] = str(args.logical_job_id)
        meta_after["campaign_id"] = str(args.campaign_id)
        meta_after["checkpoint_version"] = int(meta_after.get("checkpoint_version") or 2)
        meta_after["capability"] = "historical_contracts"
        if report.get("run_id"):
            meta_after["attempt_run_id"] = report["run_id"]
            meta_after["run_id"] = report["run_id"]
        cp_after.meta = meta_after
        save_checkpoint(cp_after)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not annotate incremental checkpoint meta: %s", exc)

    report["command"] = "run_contracts_incremental"
    report["incremental_days"] = args.days
    report["campaign_role"] = "historical_contracts_incremental"
    report["logical_job_id"] = str(args.logical_job_id)
    report["campaign_id"] = str(args.campaign_id)
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
        status == "success" and int(totals.get("windows_failed") or 0) == 0 and int(totals.get("page_errors") or 0) == 0
    )
    logger.info(
        "incremental done status=%s ok=%s inserted=%s attempt=%s",
        status,
        ok,
        totals.get("inserted"),
        report.get("run_id"),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
