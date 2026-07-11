#!/usr/bin/env python3
"""Crawl coverage metrics collector.

Extra Consultoria — Story TD-5.5
Coleta metricas operacionais:
    - Orgaos crawlados por dia por fonte
    - Taxa de sucesso/falha dos crawlers
    - Registros processados (fetched, upserted, matched)
    - Status do ultimo backup
    - Alertas ativos

Usage:
    python scripts/collect-metrics.py                          # All metrics (JSON to stdout)
    python scripts/collect-metrics.py --source pncp            # Single source
    python scripts/collect-metrics.py --days 30                # Custom window
    python scripts/collect-metrics.py --summary                # Human-readable summary
    python scripts/collect-metrics.py --export /tmp/metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging_config import get_logger, set_correlation_id
from config.settings import DEFAULT_DSN

logger = get_logger(__name__)

BACKUP_LOG_FILE = os.getenv("BACKUP_LOG_FILE", "/var/log/backup-database.log")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_conn():
    """Create database connection from DEFAULT_DSN."""
    import psycopg2  # noqa: PLC0415 — lazy import for CLI-only module

    return psycopg2.connect(DEFAULT_DSN)


# ---------------------------------------------------------------------------
# Metrics collectors
# ---------------------------------------------------------------------------


def collect_crawl_metrics(conn: Any, days: int) -> dict[str, Any]:
    """Collect crawl success/failure metrics from ingestion_runs.

    Args:
        conn: Database connection.
        days: Lookback window in days.

    Returns:
        Dict with per-source breakdown and overall stats.
    """
    cur = conn.cursor()

    # Per-source summary
    cur.execute(
        """SELECT
            source,
            COUNT(*) AS total_runs,
            COUNT(*) FILTER (WHERE status = 'completed') AS successful,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COALESCE(SUM(records_fetched), 0) AS total_fetched,
            COALESCE(SUM(records_upserted), 0) AS total_upserted,
            COALESCE(SUM(entities_covered), 0) AS total_matched,
            MAX(started_at) AS last_run,
            MAX(started_at) FILTER (WHERE status = 'completed') AS last_success
        FROM ingestion_runs
        WHERE started_at >= NOW() - INTERVAL '%s days'::INTERVAL
        GROUP BY source
        ORDER BY source""",
        (timedelta(days=days),),
    )
    rows = cur.fetchall()

    sources: list[dict[str, Any]] = []
    total_runs = 0
    total_ok = 0
    total_failed = 0
    total_fetched = 0
    total_upserted = 0

    for row in rows:
        src = {
            "source": row[0],
            "total_runs": row[1],
            "successful": row[2],
            "failed": row[3],
            "fetched": row[4],
            "upserted": row[5],
            "matched": row[6],
            "last_run": row[7].isoformat() if row[7] else None,
            "last_success": row[8].isoformat() if row[8] else None,
        }
        if src["total_runs"] > 0:
            src["success_rate"] = round(src["successful"] / src["total_runs"] * 100, 1)
        else:
            src["success_rate"] = 0.0
        sources.append(src)
        total_runs += src["total_runs"]
        total_ok += src["successful"]
        total_failed += src["failed"]
        total_fetched += src["fetched"]
        total_upserted += src["upserted"]

    cur.close()

    return {
        "sources": sources,
        "total_runs": total_runs,
        "total_successful": total_ok,
        "total_failed": total_failed,
        "total_fetched": total_fetched,
        "total_upserted": total_upserted,
        "overall_success_rate": round(total_ok / total_runs * 100, 1) if total_runs > 0 else 0.0,
    }


def collect_coverage_metrics(conn: Any) -> dict[str, Any]:
    """Collect entity coverage metrics from entity_coverage.

    Args:
        conn: Database connection.

    Returns:
        Dict with coverage breakdown by source and overall.
    """
    cur = conn.cursor()

    # Overall coverage
    cur.execute(
        """SELECT
            COUNT(DISTINCT e.id) AS total_entities,
            COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) AS covered
        FROM sc_public_entities e
        LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
        WHERE e.is_active = TRUE"""
    )
    total_entities, covered = cur.fetchone()
    total_entities = total_entities or 0
    covered = covered or 0

    # Per-source breakdown
    cur.execute(
        """SELECT source, COUNT(*) AS cnt
        FROM entity_coverage
        WHERE is_covered = TRUE
        GROUP BY source
        ORDER BY source"""
    )
    by_source = {r[0]: r[1] for r in cur.fetchall()}

    cur.close()

    return {
        "total_entities": total_entities,
        "covered_entities": covered,
        "uncovered_entities": total_entities - covered,
        "coverage_pct": round(covered / total_entities * 100, 1) if total_entities > 0 else 0.0,
        "by_source": by_source,
    }


def collect_backup_metrics() -> dict[str, Any]:
    """Collect last backup status from log file.

    Returns:
        Dict with last backup timestamp, status, and size.
    """
    metrics: dict[str, Any] = {
        "last_backup": None,
        "last_backup_status": "unknown",
        "last_backup_size": None,
        "log_available": False,
    }

    log_path = Path(BACKUP_LOG_FILE)
    if not log_path.exists():
        logger.warning("Backup log not found: %s", BACKUP_LOG_FILE)
        return metrics

    metrics["log_available"] = True

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        logger.warning("Cannot read backup log: %s", e)
        return metrics

    # Look for the most recent LOG_JSON entry (structured log from backup-database.sh)
    last_log_entry = None
    for line in reversed(lines):
        if "LOG_JSON:" in line:
            try:
                json_str = line.split("LOG_JSON:", 1)[1].strip()
                last_log_entry = json.loads(json_str)
                break
            except (json.JSONDecodeError, IndexError):
                continue

    if last_log_entry:
        metrics["last_backup"] = last_log_entry.get("timestamp")
        metrics["last_backup_status"] = last_log_entry.get("status", "unknown")
        metrics["last_backup_size"] = last_log_entry.get("size_bytes")
        metrics["last_backup_file"] = last_log_entry.get("file")
        metrics["last_backup_duration_sec"] = last_log_entry.get("duration_sec")

    # Check last ERROR in the log
    error_lines = [line for line in reversed(lines) if "[ERROR]" in line or "[FATAL]" in line]
    if error_lines:
        metrics["last_error"] = error_lines[0][:200]
        metrics["last_error_timestamp"] = error_lines[0][:30]

    return metrics


def check_consecutive_failures(conn: Any, threshold: int = 3) -> list[dict[str, Any]]:
    """Check for sources with consecutive crawl failures.

    Args:
        conn: Database connection.
        threshold: Number of consecutive failures to flag.

    Returns:
        List of sources with consecutive failures >= threshold.
    """
    cur = conn.cursor()

    # For each source, check the last N runs and count consecutive failures
    cur.execute(
        """WITH ranked AS (
            SELECT
                source,
                status,
                started_at,
                ROW_NUMBER() OVER (PARTITION BY source ORDER BY started_at DESC) AS rn
            FROM ingestion_runs
            WHERE started_at >= NOW() - INTERVAL '7 days'
        ),
        consec_failures AS (
            SELECT
                source,
                COUNT(*) AS consec_fails,
                MIN(started_at) AS since,
                MAX(started_at) AS last_attempt
            FROM ranked
            WHERE rn <= 10 AND status = 'failed'
            GROUP BY source
            HAVING COUNT(*) >= %s
        )
        SELECT source, consec_fails, since, last_attempt
        FROM consec_failures
        ORDER BY consec_fails DESC""",
        (threshold,),
    )
    results = []
    for row in cur.fetchall():
        results.append({
            "source": row[0],
            "consecutive_failures": row[1],
            "since": row[2].isoformat() if row[2] else None,
            "last_attempt": row[3].isoformat() if row[3] else None,
        })

    cur.close()
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def collect_all(days: int = 7) -> dict[str, Any]:
    """Collect all metrics and return as a single dict.

    Args:
        days: Lookback window for crawl metrics.

    Returns:
        Complete metrics dict.
    """
    timestamp = datetime.now(UTC).isoformat()

    metrics: dict[str, Any] = {
        "event": "metrics_collection",
        "timestamp": timestamp,
        "host": os.uname().nodename,
        "window_days": days,
    }

    conn = _get_conn()
    try:
        metrics["crawl"] = collect_crawl_metrics(conn, days)
        metrics["coverage"] = collect_coverage_metrics(conn)
        metrics["consecutive_failures"] = check_consecutive_failures(conn)
    except Exception as e:
        logger.exception("Failed to collect database metrics")
        metrics["error"] = str(e)
    finally:
        conn.close()

    metrics["backup"] = collect_backup_metrics()

    return metrics


def print_summary(metrics: dict[str, Any]) -> None:
    """Print human-readable summary of metrics."""
    print("=" * 60)
    print("  METRICAS DE MONITORAMENTO — Extra Consultoria")
    print("=" * 60)
    print(f"  Timestamp: {metrics.get('timestamp', 'N/A')}")
    print(f"  Host:      {metrics.get('host', 'N/A')}")
    print(f"  Janela:    {metrics.get('window_days', 'N/A')} dias")
    print()

    # Crawl metrics
    crawl = metrics.get("crawl", {})
    print("  --- CRAWL ---")
    print(f"  Total runs:       {crawl.get('total_runs', 0)}")
    print(f"  Successful:       {crawl.get('total_successful', 0)}")
    print(f"  Failed:           {crawl.get('total_failed', 0)}")
    print(f"  Success rate:     {crawl.get('overall_success_rate', 0)}%")
    print(f"  Records fetched:  {crawl.get('total_fetched', 0)}")
    print(f"  Records upserted: {crawl.get('total_upserted', 0)}")
    print()

    for src in crawl.get("sources", []):
        last_run = (src.get("last_run") or "N/A")[:16]
        print(f"    {src['source']:20s} "
              f"ok={src['successful']:3d} fail={src['failed']:2d} "
              f"({src['success_rate']:5.1f}%) "
              f"fetched={src['fetched']:5d} "
              f"last={last_run}")

    # Coverage
    cov = metrics.get("coverage", {})
    print()
    print("  --- COBERTURA ---")
    print(f"  Entities:     {cov.get('total_entities', 0)}")
    print(f"  Covered:      {cov.get('covered_entities', 0)}")
    print(f"  Uncovered:    {cov.get('uncovered_entities', 0)}")
    print(f"  Coverage:     {cov.get('coverage_pct', 0)}%")
    for src, cnt in cov.get("by_source", {}).items():
        print(f"    {src}: {cnt} entidades")

    # Backup
    bkp = metrics.get("backup", {})
    print()
    print("  --- BACKUP ---")
    if bkp.get("last_backup"):
        print(f"  Last backup:  {bkp['last_backup']}")
        print(f"  Status:       {bkp.get('last_backup_status', 'unknown')}")
        size = bkp.get("last_backup_size")
        if size is not None:
            size_mb = int(size) / (1024 * 1024)
            print(f"  Size:         {size_mb:.1f} MB")
    else:
        print("  No backup data available")

    # Consecutive failures
    failures = metrics.get("consecutive_failures", [])
    if failures:
        print()
        print("  --- FALHAS CONSECUTIVAS ---")
        for f in failures:
            print(f"    {f['source']}: {f['consecutive_failures']}x "
                  f"(since {f['since'][:16] if f.get('since') else 'N/A'})")

    print()
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extra Consultoria — Crawl Coverage Metrics Collector",
    )
    p.add_argument("--source", help="Filter by source (default: all)")
    p.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    p.add_argument("--summary", action="store_true", help="Human-readable output")
    p.add_argument("--export", help="Export metrics to JSON file")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    set_correlation_id()

    metrics = collect_all(days=args.days)

    if args.summary:
        print_summary(metrics)
    else:
        print(json.dumps(metrics, ensure_ascii=False, default=str, indent=2))

    if args.export:
        export_path = Path(args.export)
        export_path.write_text(
            json.dumps(metrics, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        logger.info("Metrics exported to %s", export_path)

    # Log the complete metrics as structured log
    logger.info(
        "Metrics collected: %d sources, %.1f%% success rate, %.1f%% coverage",
        len(metrics.get("crawl", {}).get("sources", [])),
        metrics.get("crawl", {}).get("overall_success_rate", 0),
        metrics.get("coverage", {}).get("coverage_pct", 0),
        extra={"extra_data": {"metrics": metrics}},
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
