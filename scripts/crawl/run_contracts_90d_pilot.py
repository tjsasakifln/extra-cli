#!/usr/bin/env python3
"""Resumable 90-day PNCP contracts pilot (K3.2 / NEXT-30D).

Why not only ``monitor.py --source contracts --mode full``?
  National volume is ~500k contracts / 90d. Holding all raw rows then one giant
  JSON upsert is unsafe on modest RAM. This runner:

  1. Uses the same windowing + checkpoint as contracts_crawler (mode=full)
  2. Fetches page-by-page, transforms, upserts in batches
  3. Marks windows complete ONLY when no page errors (partial-window fix)
  4. Writes evidence JSON for go/no-go

Semantics:
  - Pilot ``status=success`` requires FULL planned window coverage (not path proof).
  - A clean 1-day window is ``path_proof`` only; never upgrades partial → success.
  - ``partial`` / ``failed`` always force go_no_go_3y=NO-GO.

Usage:
  PYTHONPATH=. python3 scripts/crawl/run_contracts_90d_pilot.py \\
    --dsn "$DATABASE_URL" \\
    --output-json output/contracts/pilot-90d-next30d.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl import contracts_crawler as _cc  # noqa: E402
from scripts.crawl.contracts_crawler import (  # noqa: E402
    CONTRACTS_FULL_DAYS,
    CONTRACTS_JANELA_DELAY,
    CONTRACTS_MAX_PAGES,
    CONTRACTS_REQUEST_DELAY,
    CONTRACTS_WINDOW_DAYS,
    CrawlCheckpoint,
    FetchStatus,
    _fetch_page,
    _fmt,
    transform,
)
from scripts.crawl.run_evidence import (  # noqa: E402
    assert_checkpoint_run_id,
    bind_checkpoint_run_id,
    build_run_evidence,
    new_run_id,
    sha256_file,
)

logger = logging.getLogger("contracts_90d_pilot")

UPSERT_BATCH = int(os.getenv("CONTRACTS_UPSERT_BATCH", "500"))
# Isolate pilot checkpoints from concurrent short runs that share mode=full.
DEFAULT_PILOT_CKPT_DIR = str(_PROJECT_ROOT / "data" / "contracts_checkpoints" / "a5_next30d")

# Pilot-level page retries (on top of contracts_crawler internal retries).
_PAGE_RETRY_MAX = 3
_PAGE_RETRYABLE = frozenset(
    {
        FetchStatus.HTTP_RATE_LIMIT,
        FetchStatus.HTTP_SERVER_ERROR,
        FetchStatus.CONNECTION_FAILED,
    }
)


def count_planned_windows(
    start: date, end: date, window_days: int = CONTRACTS_WINDOW_DAYS
) -> int:
    """Number of date windows the pilot will attempt between start and end."""
    if window_days < 1 or start >= end:
        return 0
    n = 0
    cur = start
    while cur < end:
        window_end = min(cur + timedelta(days=window_days - 1), end)
        n += 1
        cur = window_end + timedelta(days=1)
    return n


def evaluate_window_completion(
    window_errors: list[str],
    *,
    pages_exhausted: bool,
    last_total_pages: int,
    page: int,
    max_pages: int,
) -> tuple[bool, list[str]]:
    """Decide whether a date window may be marked complete (shipped predicate).

    A window is complete only when there are no errors AND pages were fully
    exhausted (or the API returned a legitimate zero on the first page path).
    Hitting ``max_pages`` without exhausting ``total_pages`` is incomplete.

    Returns:
        (fully_ok, errors) — errors may be extended with a max-pages message.
    """
    errors = list(window_errors)
    if (
        not pages_exhausted
        and last_total_pages
        and page <= last_total_pages
        and page > max_pages
    ):
        errors.append(
            f"Hit CONTRACTS_MAX_PAGES={max_pages} before "
            f"total_pages={last_total_pages}; window incomplete"
        )
    fully_ok = not errors
    return fully_ok, errors


def evaluate_pilot_status(
    totals: dict[str, Any],
    *,
    planned_windows: int | None = None,
    require_full_coverage: bool = False,
) -> str:
    """Map pilot window counters to terminal status string.

    Path-level (default, ``require_full_coverage=False``):
      - success if windows_failed==0 and windows_ok>0 (legacy path proof)
      - partial if windows_ok>0 with failures
      - failed otherwise

    Full pilot (``require_full_coverage=True``, used by ``run_pilot``):
      - success ONLY when windows_failed==0, page_errors==0, planned_windows>0,
        and (windows_ok + windows_skipped_resume) >= planned_windows
      - all-skipped_resume that covers planned counts as success
      - windows_ok>0 but incomplete coverage → partial
      - nothing ok → failed

    Note: path_proof existence must NEVER alone imply pilot success.
    """
    windows_ok = int(totals.get("windows_ok") or 0)
    windows_failed = int(totals.get("windows_failed") or 0)
    windows_skipped = int(totals.get("windows_skipped_resume") or 0)
    page_errors = int(totals.get("page_errors") or 0)
    covered = windows_ok + windows_skipped

    if require_full_coverage:
        planned = int(planned_windows or 0)
        if (
            windows_failed == 0
            and page_errors == 0
            and planned > 0
            and covered >= planned
        ):
            return "success"
        # Progress without full clean coverage (incl. skipped_resume short of planned)
        if windows_ok > 0 or windows_skipped > 0:
            return "partial"
        return "failed"

    # Path-level / backward-compatible (no full-coverage requirement)
    if windows_failed == 0 and windows_ok > 0:
        return "success"
    if windows_ok > 0:
        return "partial"
    return "failed"


def evaluate_go_no_go(
    status: str,
    criteria: dict[str, Any],
    *,
    days: int | None = None,
    min_days_for_3y: int = 90,
) -> tuple[str, str]:
    """Map terminal status + criteria to (go_no_go_3y, reason).

    Rules:
    - partial / failed / running always force NO-GO
    - short pilots (days < min_days_for_3y) never authorize 3y expansion
    - success alone is insufficient without required criteria and day span
    """
    if status in {"partial", "failed", "running"}:
        return (
            "NO-GO",
            "Pilot incomplete, partial windows, or residual errors — "
            "fix before 3y expansion. path_proof alone is not full-pilot success.",
        )
    if status != "success":
        return ("NO-GO", f"Unknown or non-success status={status!r}")

    if days is not None and int(days) < int(min_days_for_3y):
        return (
            "NO-GO",
            f"Pilot span days={days} < {min_days_for_3y}; "
            "short/path pilots cannot authorize unsupervised 3y expansion.",
        )

    required = (
        "P1_run_status",
        "P2_date_span",
        "P5_no_residual_page_errors",
        "P7_sample_fields",
        "P8_full_window_coverage",
    )
    missing = [k for k in required if not criteria.get(k)]
    if missing:
        return (
            "NO-GO",
            f"Success status but criteria failed: {', '.join(missing)}",
        )
    return (
        "GO",
        "Pilot completed all planned windows without page errors; "
        "schema upsert OK; sample fields populated; span meets 90d floor.",
    )


def _fetch_page_with_retry(
    data_ini: str,
    data_fim: str,
    page: int,
    *,
    max_retries: int = _PAGE_RETRY_MAX,
) -> Any:
    """Fetch one page with exponential backoff + jitter on 429/5xx/timeout.

    Wraps ``_fetch_page`` (which has its own internal retries). Pilot-level
    retries cover residual transient failures after the inner loop gives up.
    """
    last = None
    for attempt in range(max_retries + 1):
        last = _fetch_page(data_ini, data_fim, page)
        if not last.is_failure:
            return last
        if last.status not in _PAGE_RETRYABLE or attempt >= max_retries:
            return last
        # exponential backoff with full jitter: base 1s → 2 → 4 ...
        base = 2**attempt
        delay = base + random.uniform(0, base)  # noqa: S311 — retry jitter, not crypto
        logger.warning(
            "Retryable page error %s page=%d attempt=%d/%d sleep=%.2fs: %s",
            last.status.value,
            page,
            attempt + 1,
            max_retries,
            delay,
            last.error_message,
        )
        time.sleep(delay)
    return last


def _configure_checkpoint_dir(ckpt_dir: str | None) -> str:
    """Point contracts_crawler checkpoint I/O at an isolated directory."""
    path = ckpt_dir or os.getenv("CONTRACTS_CHECKPOINT_DIR") or DEFAULT_PILOT_CKPT_DIR
    os.makedirs(path, exist_ok=True)
    os.environ["CONTRACTS_CHECKPOINT_DIR"] = path
    _cc.CONTRACTS_CHECKPOINT_DIR = path
    return path


def load_checkpoint(mode: str) -> CrawlCheckpoint:
    return _cc.load_checkpoint(mode)


def save_checkpoint(cp: CrawlCheckpoint) -> None:
    _cc.save_checkpoint(cp)


def _apply_run_id_to_checkpoint(checkpoint: CrawlCheckpoint, run_id: str) -> list[str]:
    """Bind run_id into checkpoint.meta; optionally enforce same-run resume.

    Returns previous_run_ids list for the report.
    """
    cp_dict = checkpoint.to_dict()
    existing_meta = cp_dict.get("meta") or {}
    existing_run = existing_meta.get("run_id")

    if (
        os.getenv("CONTRACTS_REQUIRE_SAME_RUN_ID", "0") == "1"
        and existing_run
        and existing_run != run_id
    ):
        assert_checkpoint_run_id(cp_dict, run_id)

    bound = bind_checkpoint_run_id(cp_dict, run_id)
    checkpoint.meta = bound.get("meta") or {}
    return list((checkpoint.meta or {}).get("previous_run_ids") or [])


def _upsert_batch(conn: Any, rows: list[dict]) -> tuple[int, int]:
    """Upsert a batch; returns (inserted, skipped)."""
    if not rows:
        return 0, 0
    # Ensure source tag for RPC default path
    payload = []
    for r in rows:
        item = dict(r)
        item.setdefault("source", "pncp_contracts")
        # dates may be date objects
        for k in (
            "data_inicio",
            "data_fim",
            "data_publicacao",
            "data_assinatura",
            "data_publicacao_fonte",
            "data_atualizacao_fonte",
            "source_event_date",
            "query_window_start",
            "query_window_end",
            "source_updated_at",
        ):
            if item.get(k) is not None and not isinstance(item[k], str):
                item[k] = item[k].isoformat()
        payload.append(item)

    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT action, contrato_id FROM upsert_pncp_supplier_contracts(%s::jsonb)",
            (json.dumps(payload),),
        )
        actions = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

    inserted = sum(1 for a in actions if a and a[0] == "inserted")
    skipped = sum(1 for a in actions if a and a[0] in {"skipped", "unchanged", "updated"})
    return inserted, skipped


def _build_path_proof(
    *,
    days: int,
    planned_windows: int,
    status: str,
    totals: dict[str, Any],
    windows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Optional path_proof block — never upgrades pilot status to success."""
    windows_ok = int(totals.get("windows_ok") or 0)
    windows_failed = int(totals.get("windows_failed") or 0)
    page_errors = int(totals.get("page_errors") or 0)

    completed = [w for w in windows if w.get("status") == "completed"]
    single_clean = (
        windows_ok >= 1
        and windows_failed == 0
        and page_errors == 0
        and len(completed) >= 1
    )

    if days <= 1:
        return {
            "status": status if status in {"success", "partial", "failed"} else "partial",
            "days": days,
            "planned_windows": planned_windows,
            "totals": {
                k: totals.get(k)
                for k in (
                    "fetched",
                    "transformed",
                    "inserted",
                    "skipped",
                    "pages",
                    "page_errors",
                    "windows_ok",
                    "windows_failed",
                    "windows_skipped_resume",
                )
            },
            "note": "days<=1 run is path-level evidence only unless planned_windows fully covered",
        }

    if single_clean and status != "success":
        first = completed[0]
        return {
            "status": "success",
            "days": CONTRACTS_WINDOW_DAYS if CONTRACTS_WINDOW_DAYS <= days else days,
            "window": first.get("window_key"),
            "totals": {
                "fetched": totals.get("fetched"),
                "transformed": totals.get("transformed"),
                "inserted": totals.get("inserted"),
                "skipped": totals.get("skipped"),
                "pages": totals.get("pages"),
                "page_errors": totals.get("page_errors"),
                "windows_ok": windows_ok,
                "windows_failed": windows_failed,
            },
            "note": (
                "At least one clean window completed; this is path_proof only — "
                "full pilot status remains partial until planned coverage is met"
            ),
        }
    return None


def run_pilot(
    dsn: str,
    *,
    days: int = CONTRACTS_FULL_DAYS,
    output_json: str | None = None,
    dry_run: bool = False,
    checkpoint_dir: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    mode = "full"
    today = date.today()
    start = today - timedelta(days=days)
    planned_windows = count_planned_windows(start, today, CONTRACTS_WINDOW_DAYS)
    run_id = run_id or new_run_id(prefix="contracts-90d")

    ckpt_dir = _configure_checkpoint_dir(checkpoint_dir)
    checkpoint_path = str(Path(ckpt_dir) / f"contracts_{mode}.json")
    checkpoint = load_checkpoint(mode)
    previous_run_ids = _apply_run_id_to_checkpoint(checkpoint, run_id)
    save_checkpoint(checkpoint)

    # Reset counters for this pilot run report but KEEP completed_windows for resume
    report: dict[str, Any] = {
        "pilot": "k3.2-pncp-90d",
        "campaign": "NEXT-30D",
        "run_id": run_id,
        "previous_run_ids": previous_run_ids,
        "mode": mode,
        "days": days,
        "window_days": CONTRACTS_WINDOW_DAYS,
        "planned_windows": planned_windows,
        "range_start": start.isoformat(),
        "range_end": today.isoformat(),
        "started_at": started.isoformat(),
        "checkpoint_path": checkpoint_path,
        "windows": [],
        "totals": {
            "fetched": 0,
            "transformed": 0,
            "inserted": 0,
            "skipped": 0,
            "pages": 0,
            "page_errors": 0,
            "windows_ok": 0,
            "windows_failed": 0,
            "windows_skipped_resume": 0,
        },
        "status": "running",
        "errors": [],
    }

    conn = None if dry_run else psycopg2.connect(dsn)
    if conn is not None:
        conn.autocommit = False

    try:
        cur_date = start
        while cur_date < today:
            window_end = min(cur_date + timedelta(days=CONTRACTS_WINDOW_DAYS - 1), today)
            window_key = f"{_fmt(cur_date)}_{_fmt(window_end)}"
            data_ini, data_fim = _fmt(cur_date), _fmt(window_end)
            w_started = time.time()

            if window_key in checkpoint.completed_windows:
                logger.info("SKIP completed window %s", window_key)
                report["totals"]["windows_skipped_resume"] += 1
                report["windows"].append(
                    {
                        "window_key": window_key,
                        "status": "skipped_resume",
                        "records_fetched": 0,
                    }
                )
                cur_date = window_end + timedelta(days=1)
                continue

            checkpoint.current_window_start = data_ini
            save_checkpoint(checkpoint)

            page = 1
            window_records_raw: list[dict] = []
            window_errors: list[str] = []
            window_pages = 0
            window_inserted = 0
            window_skipped = 0
            window_transformed = 0

            pages_exhausted = False
            last_total_pages = 0
            print(f"WINDOW_START {window_key}", flush=True)
            while page <= CONTRACTS_MAX_PAGES:
                result = _fetch_page_with_retry(data_ini, data_fim, page)
                if result.is_failure:
                    msg = f"Page {page}: [{result.status.value}] {result.error_message}"
                    window_errors.append(msg)
                    logger.warning("Window %s %s", window_key, msg)
                    print(f"WINDOW_ERR {window_key} {msg}", flush=True)
                    report["totals"]["page_errors"] += 1
                    break

                if result.is_zero:
                    pages_exhausted = True
                    break

                last_total_pages = int(result.total_pages or 0)
                window_records_raw.extend(result.items)
                window_pages += 1
                report["totals"]["pages"] += 1
                if page == 1 or page % 10 == 0:
                    print(
                        f"PAGE {window_key} p={page}/{last_total_pages} "
                        f"batch={len(result.items)} ins_total={report['totals']['inserted']}",
                        flush=True,
                    )

                # Transform + upsert incrementally every UPSERT_BATCH raw pages worth
                if len(window_records_raw) >= UPSERT_BATCH or page >= result.total_pages:
                    rows = transform(window_records_raw)
                    window_transformed += len(rows)
                    report["totals"]["fetched"] += len(window_records_raw)
                    report["totals"]["transformed"] += len(rows)
                    if not dry_run and conn is not None:
                        # batch further if needed
                        for i in range(0, len(rows), UPSERT_BATCH):
                            chunk = rows[i : i + UPSERT_BATCH]
                            try:
                                ins, sk = _upsert_batch(conn, chunk)
                                window_inserted += ins
                                window_skipped += sk
                                report["totals"]["inserted"] += ins
                                report["totals"]["skipped"] += sk
                            except Exception as e:
                                err = f"upsert failed window={window_key} page~{page}: {e}"
                                logger.exception(err)
                                window_errors.append(err)
                                report["errors"].append(err)
                                break
                    window_records_raw = []
                    if window_errors:
                        break

                if page >= result.total_pages:
                    pages_exhausted = True
                    break
                page += 1
                time.sleep(CONTRACTS_REQUEST_DELAY)
            else:
                # while-else: loop ended because page > MAX without exhausting pages
                # (predicate applied below via evaluate_window_completion)
                pass

            # Flush any remainder not yet upserted (e.g. last partial batch)
            if window_records_raw and not window_errors:
                rows = transform(window_records_raw)
                window_transformed += len(rows)
                report["totals"]["fetched"] += len(window_records_raw)
                report["totals"]["transformed"] += len(rows)
                if not dry_run and conn is not None:
                    for i in range(0, len(rows), UPSERT_BATCH):
                        chunk = rows[i : i + UPSERT_BATCH]
                        try:
                            ins, sk = _upsert_batch(conn, chunk)
                            window_inserted += ins
                            window_skipped += sk
                            report["totals"]["inserted"] += ins
                            report["totals"]["skipped"] += sk
                        except Exception as e:
                            err = f"upsert failed window={window_key} flush: {e}"
                            logger.exception(err)
                            window_errors.append(err)
                            report["errors"].append(err)
                            break
                window_records_raw = []

            fully_ok, window_errors = evaluate_window_completion(
                window_errors,
                pages_exhausted=pages_exhausted,
                last_total_pages=last_total_pages,
                page=page,
                max_pages=CONTRACTS_MAX_PAGES,
            )
            if not fully_ok and any("Hit CONTRACTS_MAX_PAGES" in e for e in window_errors):
                report["totals"]["page_errors"] += 1
            elapsed = round(time.time() - w_started, 1)
            w_status = "completed" if fully_ok else "partial_or_failed"
            if fully_ok:
                checkpoint.completed_windows.append(window_key)
                checkpoint.total_windows_completed += 1
                checkpoint.total_contracts_fetched += window_transformed
                report["totals"]["windows_ok"] += 1
            else:
                checkpoint.total_windows_failed += 1
                checkpoint.last_error = "; ".join(window_errors[:3])
                report["totals"]["windows_failed"] += 1
                logger.warning(
                    "Window %s NOT marked complete (errors=%d, transformed=%d)",
                    window_key,
                    len(window_errors),
                    window_transformed,
                )
            # Keep run_id binding fresh on every save
            _apply_run_id_to_checkpoint(checkpoint, run_id)
            save_checkpoint(checkpoint)

            report["windows"].append(
                {
                    "window_key": window_key,
                    "status": w_status,
                    "pages": window_pages,
                    "transformed": window_transformed,
                    "inserted": window_inserted,
                    "skipped": window_skipped,
                    "errors": window_errors[:5],
                    "elapsed_seconds": elapsed,
                }
            )
            logger.info(
                "Window %s %s pages=%d transformed=%d ins=%d skip=%d t=%.1fs",
                window_key,
                w_status,
                window_pages,
                window_transformed,
                window_inserted,
                window_skipped,
                elapsed,
            )
            # Intermediate evidence so a kill mid-run still leaves a non-empty terminal-ish file
            if output_json:
                interim = dict(report)
                interim["status"] = "running"
                interim["checkpoint"] = checkpoint.to_dict()
                Path(output_json).parent.mkdir(parents=True, exist_ok=True)
                Path(output_json).write_text(
                    json.dumps(interim, indent=2, default=str), encoding="utf-8"
                )

            cur_date = window_end + timedelta(days=1)
            if cur_date < today:
                time.sleep(CONTRACTS_JANELA_DELAY)

        completed = datetime.now(UTC)
        report["completed_at"] = completed.isoformat()
        report["duration_seconds"] = round((completed - started).total_seconds(), 1)

        # DB proof metrics
        if conn is not None and not dry_run:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT COUNT(*) AS n,
                       MIN(data_publicacao) AS min_pub,
                       MAX(data_publicacao) AS max_pub
                FROM pncp_supplier_contracts
                """
            )
            row = cur.fetchone() or {}
            cur.execute(
                """
                SELECT date_trunc('month', data_publicacao)::date AS mes, COUNT(*) AS n
                FROM pncp_supplier_contracts
                WHERE data_publicacao >= CURRENT_DATE - INTERVAL '100 days'
                GROUP BY 1 ORDER BY 1
                """
            )
            monthly = [dict(r) for r in cur.fetchall()]
            for m in monthly:
                if m.get("mes") is not None:
                    m["mes"] = m["mes"].isoformat()
            cur.execute(
                """
                SELECT COUNT(*) AS n_sample
                FROM (
                  SELECT contrato_id, orgao_cnpj, valor_total, data_publicacao
                  FROM pncp_supplier_contracts
                  WHERE contrato_id IS NOT NULL
                    AND orgao_cnpj IS NOT NULL
                    AND data_publicacao IS NOT NULL
                  LIMIT 20
                ) s
                """
            )
            sample_ok = (cur.fetchone() or {}).get("n_sample", 0)

            # Optional semantic date columns (migration 051). Soft-fail if missing.
            min_assin = max_assin = None
            has_assinatura_col = False
            try:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'pncp_supplier_contracts'
                      AND column_name = 'data_assinatura'
                    LIMIT 1
                    """
                )
                has_assinatura_col = cur.fetchone() is not None
                if has_assinatura_col:
                    cur.execute(
                        """
                        SELECT MIN(data_assinatura) AS min_a,
                               MAX(data_assinatura) AS max_a
                        FROM pncp_supplier_contracts
                        WHERE data_assinatura IS NOT NULL
                        """
                    )
                    arow = cur.fetchone() or {}
                    min_assin = arow.get("min_a")
                    max_assin = arow.get("max_a")
            except Exception as e:  # noqa: BLE001 — soft-fail for older DBs
                logger.warning("Could not report data_assinatura min/max: %s", e)

            cur.close()
            report["db"] = {
                "pncp_supplier_contracts_count": row.get("n"),
                "min_data_publicacao": row["min_pub"].isoformat() if row.get("min_pub") else None,
                "max_data_publicacao": row["max_pub"].isoformat() if row.get("max_pub") else None,
                # LEGACY: data_publicacao historically held dataAssinatura (mixed semantics).
                # Prefer data_assinatura / data_publicacao_fonte after migration 051.
                "data_publicacao_note": (
                    "legacy/mixed semantics — historically stored dataAssinatura; "
                    "prefer data_assinatura / data_publicacao_fonte (migration 051)"
                ),
                "min_data_assinatura": min_assin.isoformat() if min_assin else None,
                "max_data_assinatura": max_assin.isoformat() if max_assin else None,
                "has_data_assinatura_column": has_assinatura_col,
                "monthly": monthly,
                "sample_populated_n20": int(sample_ok),
            }

        # Final checkpoint snapshot
        report["checkpoint"] = checkpoint.to_dict()

        # Full-coverage pilot status (never path-level alone)
        report["status"] = evaluate_pilot_status(
            report["totals"],
            planned_windows=planned_windows,
            require_full_coverage=True,
        )

        # Optional path_proof (does NOT override pilot status)
        path_proof = _build_path_proof(
            days=days,
            planned_windows=planned_windows,
            status=report["status"],
            totals=report["totals"],
            windows=report["windows"],
        )
        if path_proof is not None:
            report["path_proof"] = path_proof

        # Go/no-go heuristics (P1-P5, P7 simplified)
        p = report["totals"]
        db = report.get("db") or {}
        criteria = {
            "P1_run_status": report["status"] == "success",
            "P2_date_span": bool(db.get("min_data_publicacao") and db.get("max_data_publicacao")),
            "P3_monthly": bool(db.get("monthly")),
            "P5_no_residual_page_errors": p["page_errors"] == 0 and p["windows_failed"] == 0,
            "P6_checkpoint_coherent": len(checkpoint.completed_windows)
            >= (p["windows_ok"] + p["windows_skipped_resume"])
            or len(checkpoint.completed_windows) >= p["windows_ok"],
            "P7_sample_fields": int(db.get("sample_populated_n20") or 0) >= 20
            or int(db.get("pncp_supplier_contracts_count") or 0) >= 20,
            "P8_full_window_coverage": (
                planned_windows > 0
                and (p["windows_ok"] + p["windows_skipped_resume"]) >= planned_windows
                and p["windows_failed"] == 0
            ),
        }
        report["criteria"] = criteria
        go_label, go_reason = evaluate_go_no_go(
            report["status"],
            criteria,
            days=days,
            min_days_for_3y=CONTRACTS_FULL_DAYS,
        )
        report["go_no_go_3y"] = go_label
        report["go_no_go_reason"] = go_reason

        # Claims discipline
        report["claims_allowed"] = [
            "Resumable pilot runner exists; partial windows are not marked complete on page errors",
        ]
        if int(p.get("windows_ok") or 0) >= 1 or (
            path_proof and path_proof.get("status") == "success"
        ):
            report["claims_allowed"].append(
                "At least one full day/window completed with 0 page errors (path_proof)"
            )
        if int((db or {}).get("pncp_supplier_contracts_count") or 0) >= 1000:
            report["claims_allowed"].append(
                "Contracts persisted in pncp_supplier_contracts (see db counts)"
            )
        report["claims_forbidden"] = [
            "Full 90-day national pilot completed"
            if report["status"] != "success"
            else "Unsupervised 3y without re-validation",
            "GO for unsupervised 3-year backfill"
            if go_label != "GO"
            else "Skip re-check after schema changes",
            "CONTRATOS_95",
        ]

    finally:
        if conn is not None:
            conn.close()

    # Attach evidence block, write final JSON once, then stamp output_hash of that write.
    evidence = build_run_evidence(
        run_id=run_id,
        started_at=report.get("started_at"),
        completed_at=report.get("completed_at"),
        command="scripts/crawl/run_contracts_90d_pilot.py",
        args={
            "days": days,
            "mode": mode,
            "dry_run": dry_run,
            "planned_windows": planned_windows,
            "checkpoint_dir": ckpt_dir,
        },
        checkpoint_path=checkpoint_path,
        checkpoint_hash=sha256_file(checkpoint_path),
        output_path=str(output_json) if output_json else None,
        output_hash=None,
        status=report.get("status"),
        errors=report.get("errors") or [],
        criteria=report.get("criteria") or {},
        claims_allowed=report.get("claims_allowed") or [],
        claims_forbidden=report.get("claims_forbidden") or [],
        counts_after={
            "inserted": report["totals"].get("inserted"),
            "transformed": report["totals"].get("transformed"),
            "windows_ok": report["totals"].get("windows_ok"),
            "windows_failed": report["totals"].get("windows_failed"),
            "windows_skipped_resume": report["totals"].get("windows_skipped_resume"),
            "planned_windows": planned_windows,
        },
        previous_run_ids=previous_run_ids,
    )
    report["evidence"] = evidence

    if output_json:
        out = Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        # Hash of the written artifact (pre self-hash); re-write once with hash set.
        report["evidence"]["output_hash"] = sha256_file(out)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Wrote evidence %s run_id=%s", out, run_id)

    return report


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="PNCP contracts 90d resumable pilot")
    ap.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN"),
        help="PostgreSQL DSN",
    )
    ap.add_argument(
        "--output-json",
        default="output/contracts/pilot-90d-next30d.json",
    )
    ap.add_argument("--days", type=int, default=CONTRACTS_FULL_DAYS)
    ap.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Clear completed_windows for a fresh pilot range (keeps file path)",
    )
    ap.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Isolated checkpoint dir (default: data/contracts_checkpoints/a5_next30d)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dsn and not args.dry_run:
        print("ERROR: --dsn or DATABASE_URL required", file=sys.stderr)
        return 2

    _configure_checkpoint_dir(args.checkpoint_dir)

    if args.reset_checkpoint:
        cp = load_checkpoint("full")
        cp.completed_windows = []
        cp.current_window_start = None
        cp.total_windows_completed = 0
        cp.total_windows_failed = 0
        cp.total_contracts_fetched = 0
        cp.last_error = None
        # Preserve meta.run_ids history when resetting windows
        save_checkpoint(cp)
        logging.getLogger("contracts_90d_pilot").info("Checkpoint reset for mode=full")

    report = run_pilot(
        args.dsn or "",
        days=args.days,
        output_json=args.output_json,
        dry_run=args.dry_run,
        checkpoint_dir=args.checkpoint_dir,
    )
    summary_keys = (
        "run_id",
        "status",
        "totals",
        "planned_windows",
        "go_no_go_3y",
        "duration_seconds",
        "db",
        "path_proof",
    )
    print(
        json.dumps(
            {k: report[k] for k in summary_keys if k in report},
            indent=2,
            default=str,
        )
    )
    if report["status"] == "success":
        return 0
    if report["status"] == "partial":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
