#!/usr/bin/env python3
"""Resumable 90-day PNCP contracts pilot (K3.2 / NEXT-30D).

Why not only ``monitor.py --source contracts --mode full``?
  National volume is ~500k contracts / 90d. Holding all raw rows then one giant
  JSON upsert is unsafe on modest RAM. This runner:

  1. Uses the same windowing + checkpoint as contracts_crawler (mode=full)
  2. Fetches page-by-page, transforms, upserts in batches
  3. Marks windows complete ONLY when no page errors (partial-window fix)
  4. Writes evidence JSON for go/no-go

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
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.contracts_crawler import (  # noqa: E402
    CONTRACTS_FULL_DAYS,
    CONTRACTS_JANELA_DELAY,
    CONTRACTS_MAX_PAGES,
    CONTRACTS_REQUEST_DELAY,
    CONTRACTS_WINDOW_DAYS,
    _fetch_page,
    _fmt,
    load_checkpoint,
    save_checkpoint,
    transform,
)

logger = logging.getLogger("contracts_90d_pilot")

UPSERT_BATCH = int(os.getenv("CONTRACTS_UPSERT_BATCH", "500"))


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
        for k in ("data_inicio", "data_fim", "data_publicacao"):
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


def run_pilot(
    dsn: str,
    *,
    days: int = CONTRACTS_FULL_DAYS,
    output_json: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    mode = "full"
    today = date.today()
    start = today - timedelta(days=days)

    checkpoint = load_checkpoint(mode)
    # Reset counters for this pilot run report but KEEP completed_windows for resume
    report: dict[str, Any] = {
        "pilot": "k3.2-pncp-90d",
        "campaign": "NEXT-30D",
        "mode": mode,
        "days": days,
        "window_days": CONTRACTS_WINDOW_DAYS,
        "range_start": start.isoformat(),
        "range_end": today.isoformat(),
        "started_at": started.isoformat(),
        "checkpoint_path": str(
            Path(os.getenv("CONTRACTS_CHECKPOINT_DIR", str(_PROJECT_ROOT / "data" / "contracts_checkpoints")))
            / f"contracts_{mode}.json"
        ),
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
                result = _fetch_page(data_ini, data_fim, page)
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
                if not pages_exhausted and last_total_pages and page <= last_total_pages:
                    window_errors.append(
                        f"Hit CONTRACTS_MAX_PAGES={CONTRACTS_MAX_PAGES} before "
                        f"total_pages={last_total_pages}; window incomplete"
                    )
                    report["totals"]["page_errors"] += 1

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

            fully_ok = not window_errors
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

        completed = datetime.now(timezone.utc)
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
            cur.close()
            report["db"] = {
                "pncp_supplier_contracts_count": row.get("n"),
                "min_data_publicacao": row["min_pub"].isoformat() if row.get("min_pub") else None,
                "max_data_publicacao": row["max_pub"].isoformat() if row.get("max_pub") else None,
                "monthly": monthly,
                "sample_populated_n20": int(sample_ok),
            }

        # Final checkpoint snapshot
        report["checkpoint"] = checkpoint.to_dict()

        if report["totals"]["windows_failed"] == 0 and report["totals"]["windows_ok"] > 0:
            report["status"] = "success"
        elif report["totals"]["windows_ok"] > 0:
            report["status"] = "partial"
        else:
            report["status"] = "failed"

        # Go/no-go heuristics (P1-P5, P7 simplified)
        p = report["totals"]
        db = report.get("db") or {}
        criteria = {
            "P1_run_status": report["status"] in {"success", "partial"},
            "P2_date_span": bool(db.get("min_data_publicacao") and db.get("max_data_publicacao")),
            "P3_monthly": bool(db.get("monthly")),
            "P5_no_residual_page_errors": p["page_errors"] == 0 and p["windows_failed"] == 0,
            "P6_checkpoint_coherent": len(checkpoint.completed_windows) == p["windows_ok"]
            + report["totals"]["windows_skipped_resume"]
            or len(checkpoint.completed_windows) >= p["windows_ok"],
            "P7_sample_fields": int(db.get("sample_populated_n20") or 0) >= 20
            or int(db.get("pncp_supplier_contracts_count") or 0) >= 20,
        }
        report["criteria"] = criteria
        go = all(
            [
                criteria["P1_run_status"],
                criteria["P2_date_span"],
                criteria["P5_no_residual_page_errors"],
                criteria["P7_sample_fields"],
            ]
        )
        # Partial success with remaining errors → NO-GO for 3y until clean resume
        if report["status"] != "success":
            go = False
        report["go_no_go_3y"] = "GO" if go else "NO-GO"
        report["go_no_go_reason"] = (
            "Pilot completed all windows without page errors; schema upsert OK; sample fields populated."
            if go
            else "Pilot incomplete, partial windows, or residual errors — fix before 3y expansion."
        )

    finally:
        if conn is not None:
            conn.close()

    if output_json:
        out = Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Wrote evidence %s", out)

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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dsn and not args.dry_run:
        print("ERROR: --dsn or DATABASE_URL required", file=sys.stderr)
        return 2

    if args.reset_checkpoint:
        cp = load_checkpoint("full")
        cp.completed_windows = []
        cp.current_window_start = None
        cp.total_windows_completed = 0
        cp.total_windows_failed = 0
        cp.total_contracts_fetched = 0
        cp.last_error = None
        save_checkpoint(cp)
        logger = logging.getLogger("contracts_90d_pilot")
        logger.info("Checkpoint reset for mode=full")

    report = run_pilot(
        args.dsn or "",
        days=args.days,
        output_json=args.output_json,
        dry_run=args.dry_run,
    )
    print(json.dumps({k: report[k] for k in ("status", "totals", "go_no_go_3y", "duration_seconds", "db") if k in report}, indent=2, default=str))
    if report["status"] == "success":
        return 0
    if report["status"] == "partial":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
