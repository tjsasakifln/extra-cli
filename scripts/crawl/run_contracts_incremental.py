#!/usr/bin/env python3
"""Canonical incremental update for historical contracts (PNCP).

Uses the hardened pilot runner and PNCP update-date endpoint for a short
closed-day lookback window (default 7 days)
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
  77 — only transient PNCP/source-population-drift failure; service may retry once
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import UTC, date, datetime
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
INCREMENTAL_QUERY_KIND = "update"
INCREMENTAL_WINDOW_DAYS = 1
EXIT_RETRYABLE_SOURCE = 77
RETRY_DELAY_SECONDS = 300


def current_incremental_window_keys(
    *,
    days: int,
    today: date | None = None,
    window_days: int = INCREMENTAL_WINDOW_DAYS,
) -> list[str]:
    """Return every closed overlap window that must be revalidated.

    Incremental observations deliberately use daily partitions.  A mutable
    seven-day PNCP result set can change while 100+ pages are traversed; daily
    windows keep the same lookback while making each completion unit small,
    independently auditable, and retryable.
    """
    from scripts.crawl.run_contracts_90d_pilot import (
        closed_crawl_range,
        iter_planned_window_keys,
        utc_today,
    )

    operational_today = today or utc_today()
    start, _closed_through, exclusive_end = closed_crawl_range(operational_today, days)
    keys = iter_planned_window_keys(start, exclusive_end, window_days)
    if not keys:
        raise ValueError(f"incremental range produced no window for days={days}")
    return keys


def current_incremental_window_key(*, days: int, today: date | None = None) -> str:
    """Return the latest daily window key (compatibility helper)."""
    return current_incremental_window_keys(days=days, today=today)[-1]


def reopen_current_window(checkpoint: object, *, window_key: str) -> bool:
    """Force the moving incremental window through PNCP on every timer slot.

    Historical windows remain resumable. The latest closed overlap window is
    different: treating it as permanently complete turns a 4h timer into a
    once-per-day source refresh and lets late updates go unseen.
    Removing it before the attempt is fail-closed: a failed revalidation leaves
    it absent; only a clean 93/93-style traversal adds it back.
    """
    completed = list(getattr(checkpoint, "completed_windows", []) or [])
    if window_key not in completed:
        return False
    setattr(checkpoint, "completed_windows", [key for key in completed if key != window_key])
    return True


def reopen_incremental_windows(checkpoint: object, *, window_keys: list[str]) -> list[str]:
    """Reopen the complete moving lookback, returning the removed keys."""
    completed = list(getattr(checkpoint, "completed_windows", []) or [])
    moving = set(window_keys)
    reopened = [key for key in completed if key in moving]
    if reopened:
        setattr(checkpoint, "completed_windows", [key for key in completed if key not in moving])
    return reopened


def _is_retryable_source_error(error: str) -> bool:
    """Subset of the pilot taxonomy that is safe to replay as a whole run.

    Keep this dependency-light because the systemd entrypoint must classify an
    error even when optional database modules are unavailable after a failed
    attempt.  Everything not named here is structural and therefore terminal.
    """
    text = str(error or "").strip().lower()
    return bool(
        re.match(
            r"^(source_population_drift|connection_failed|http_rate_limit|rate_limit|http_server_error)(:|\b)",
            text,
        )
        or re.match(
            r"^page\s+\d+:\s*\[(source_population_drift|connection_failed|http_rate_limit|rate_limit|http_server_error)\]",
            text,
        )
    )


def retry_exit_for_report(report: dict[str, object]) -> int:
    """Return a retry-only exit code for known transient upstream outcomes.

    The systemd unit deliberately has no general ``Restart=on-failure``:
    checkpoint, persistence, schema and request-contract faults need an
    operator, not a second concurrent crawl.  A complete failed attempt can
    be retried once only when *every* recorded window error is classified as
    transient (including PNCP's mutable-population drift).
    """
    errors: list[str] = []
    for window in report.get("windows") or []:
        if not isinstance(window, dict):
            continue
        for error in window.get("errors") or []:
            if str(error).strip():
                errors.append(str(error))
    if not errors:
        return 1
    if all(_is_retryable_source_error(error) for error in errors):
        return EXIT_RETRYABLE_SOURCE
    return 1


def run_with_one_retry(run, *, sleep=time.sleep) -> int:
    """Run at most twice; only typed upstream exit 77 earns the second call."""
    result = run()
    if result != EXIT_RETRYABLE_SOURCE:
        return result
    logger.warning("Typed PNCP source failure; retrying once in %ss", RETRY_DELAY_SECONDS)
    sleep(RETRY_DELAY_SECONDS)
    return run()


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
        return run_with_one_retry(lambda: _run_incremental(args))
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
        meta["query_kind"] = INCREMENTAL_QUERY_KIND
        meta["window_days"] = INCREMENTAL_WINDOW_DAYS
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
            prior_query_kind = (data.get("meta") or {}).get("query_kind")
            if prior_query_kind and prior_query_kind != INCREMENTAL_QUERY_KIND:
                raise ValueError(
                    f"query_kind mismatch existing={prior_query_kind!r} "
                    f"requested={INCREMENTAL_QUERY_KIND!r}; use --reset-checkpoint after archive"
                )
            prior_window_days = (data.get("meta") or {}).get("window_days")
            if prior_window_days is None and data.get("completed_windows"):
                raise ValueError(
                    "checkpoint has completed windows without window_days binding; "
                    "daily-window migration requires --reset-checkpoint after archive"
                )
            if prior_window_days is not None and int(prior_window_days) != INCREMENTAL_WINDOW_DAYS:
                raise ValueError(
                    f"window_days mismatch existing={prior_window_days!r} "
                    f"requested={INCREMENTAL_WINDOW_DAYS!r}; use --reset-checkpoint after archive"
                )
            data.setdefault("meta", {})["query_kind"] = INCREMENTAL_QUERY_KIND
            data.setdefault("meta", {})["window_days"] = INCREMENTAL_WINDOW_DAYS
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

    # Completed moving windows are not durable freshness evidence. Revalidate
    # the full daily-partitioned lookback on every 4h slot; success re-adds
    # every unit, while any failed unit remains fail-closed.
    checkpoint = load_checkpoint("full")
    refresh_keys = current_incremental_window_keys(days=int(args.days))
    reopened = reopen_incremental_windows(checkpoint, window_keys=refresh_keys)
    if reopened:
        save_checkpoint(checkpoint)
        logger.info(
            "Reopened %d daily incremental windows for refresh: %s..%s",
            len(reopened),
            reopened[0],
            reopened[-1],
        )

    report = run_pilot(
        dsn=args.dsn,
        days=args.days,
        window_days=INCREMENTAL_WINDOW_DAYS,
        output_json=str(args.output_json),
        checkpoint_dir=args.checkpoint_dir,
        dry_run=bool(args.dry_run),
        logical_job_id=str(args.logical_job_id),
        campaign_id=str(args.campaign_id),
        query_kind=INCREMENTAL_QUERY_KIND,
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
        meta_after["query_kind"] = INCREMENTAL_QUERY_KIND
        meta_after["window_days"] = INCREMENTAL_WINDOW_DAYS
        if report.get("run_id"):
            meta_after["attempt_run_id"] = report["run_id"]
            meta_after["run_id"] = report["run_id"]
        cp_after.meta = meta_after
        save_checkpoint(cp_after)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not annotate incremental checkpoint meta: %s", exc)

    report["command"] = "run_contracts_incremental"
    report["incremental_days"] = args.days
    report["window_days"] = INCREMENTAL_WINDOW_DAYS
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
    return 0 if ok else retry_exit_for_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
