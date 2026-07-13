#!/usr/bin/env python3
"""Freshness gate for local datalake critical sources.

This gate exists because a local datalake may contain useful but stale legacy
data. For consultive use, the system must prove recent successful ingestion for
critical sources before users trust editais abertos or contratos historicos.

Critical sources in the current phase:
    - pncp: open bids / published tenders
    - contracts: historical contracts

Outputs:
    - output/readiness/freshness-gate.json
    - output/readiness/freshness-gate.csv

Exit codes:
    0 — all critical sources fresh
    2 — one or more critical sources stale / never / technical gap
    1 — technical failure
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)
OUTPUT_DIR = PROJECT_ROOT / "output" / "readiness"


@dataclass(frozen=True)
class CriticalSourceSpec:
    source_name: str
    purpose: str
    run_source: str
    table_name: str
    data_source: str
    recent_window_hours: int
    freshness_sla_hours: int
    business_date_column: str


CRITICAL_SOURCES: tuple[CriticalSourceSpec, ...] = (
    CriticalSourceSpec(
        source_name="pncp",
        purpose="editais_abertos",
        run_source="pncp",
        table_name="pncp_raw_bids",
        data_source="pncp",
        recent_window_hours=24,
        freshness_sla_hours=24,
        business_date_column="data_publicacao",
    ),
    CriticalSourceSpec(
        source_name="contracts",
        purpose="historical_contracts",
        run_source="contracts",
        table_name="pncp_supplier_contracts",
        data_source="pncp_contracts",
        recent_window_hours=24 * 7,
        freshness_sla_hours=24 * 24,
        business_date_column="data_publicacao",
    ),
)


def _get_conn(dsn: str | None = None):
    effective_dsn = dsn or DEFAULT_DSN
    try:
        conn = psycopg2.connect(effective_dsn)
    except Exception as exc:
        raise RuntimeError(
            "Failed to connect to local datalake for freshness gate. "
            "Set LOCAL_DATALAKE_DSN correctly and ensure PostgreSQL is reachable."
        ) from exc
    conn.autocommit = True
    return conn


def _query_one_dict(conn, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else {}


def _table_columns(conn, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            (table_name,),
        )
        return {row[0] for row in cur.fetchall()}


def _pick_existing_column(columns: set[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _status_from_snapshot(
    *,
    now: datetime,
    last_success_at: datetime | None,
    last_ingested_at: datetime | None,
    freshness_sla_hours: int,
) -> tuple[str, str | None]:
    """Return status + reason for one source snapshot."""
    if last_success_at is None:
        return "never", "No successful ingestion run found for critical source"

    age_hours = (now - last_success_at).total_seconds() / 3600
    if age_hours > freshness_sla_hours:
        return "stale", f"Last successful run is {age_hours:.1f}h old, above SLA {freshness_sla_hours}h"

    if last_ingested_at is None:
        return "stale", "Successful run exists but no persisted active records were found"

    data_age_hours = (now - last_ingested_at).total_seconds() / 3600
    if data_age_hours > freshness_sla_hours:
        return "stale", f"Persisted active records are {data_age_hours:.1f}h old, above SLA {freshness_sla_hours}h"

    return "fresh", None


def _run_snapshot(conn, spec: CriticalSourceSpec) -> dict[str, Any]:
    columns = _table_columns(conn, "ingestion_runs")
    finished_col = _pick_existing_column(columns, "completed_at", "finished_at")
    started_col = _pick_existing_column(columns, "started_at")
    status_col = _pick_existing_column(columns, "status")

    if not finished_col or not started_col or not status_col:
        raise RuntimeError("ingestion_runs schema missing required timestamp/status columns")

    sql = f"""
        SELECT
            MAX(CASE WHEN {status_col} = 'completed' THEN COALESCE({finished_col}, {started_col}) END) AS last_success_at,
            COUNT(*) FILTER (WHERE {status_col} = 'completed') AS successful_runs,
            COUNT(*) AS total_runs
        FROM ingestion_runs
        WHERE source = %s
    """
    return _query_one_dict(conn, sql, (spec.run_source,))


def _data_snapshot(conn, spec: CriticalSourceSpec) -> dict[str, Any]:
    table_columns = _table_columns(conn, spec.table_name)
    if "ingested_at" not in table_columns:
        raise RuntimeError(f"{spec.table_name} missing required column ingested_at")
    if spec.business_date_column not in table_columns:
        raise RuntimeError(f"{spec.table_name} missing required business date column {spec.business_date_column}")

    active_sql = "AND is_active IS TRUE" if "is_active" in table_columns else ""
    source_sql = "AND source = %s" if "source" in table_columns else ""
    source_params: tuple[Any, ...] = (spec.data_source,) if "source" in table_columns else ()

    sql = f"""
        SELECT
            MAX(ingested_at) AS last_ingested_at,
            MAX({spec.business_date_column}) AS latest_business_date,
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - (%s * INTERVAL '1 hour')) AS recent_records,
            COUNT(*) AS total_records
        FROM {spec.table_name}
        WHERE 1=1
          {source_sql}
          {active_sql}
    """
    return _query_one_dict(conn, sql, (spec.recent_window_hours, *source_params))


def evaluate_source(conn, spec: CriticalSourceSpec, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    run_snapshot = _run_snapshot(conn, spec)
    data_snapshot = _data_snapshot(conn, spec)

    last_success_at = run_snapshot.get("last_success_at")
    last_ingested_at = data_snapshot.get("last_ingested_at")
    status, reason = _status_from_snapshot(
        now=now,
        last_success_at=last_success_at,
        last_ingested_at=last_ingested_at,
        freshness_sla_hours=spec.freshness_sla_hours,
    )

    return {
        "source": spec.source_name,
        "purpose": spec.purpose,
        "critical": True,
        "run_source": spec.run_source,
        "data_table": spec.table_name,
        "data_source": spec.data_source,
        "freshness_sla_hours": spec.freshness_sla_hours,
        "recent_window_hours": spec.recent_window_hours,
        "last_success_at": last_success_at,
        "last_ingested_at": last_ingested_at,
        "latest_business_date": data_snapshot.get("latest_business_date"),
        "recent_records": int(data_snapshot.get("recent_records") or 0),
        "total_records": int(data_snapshot.get("total_records") or 0),
        "successful_runs": int(run_snapshot.get("successful_runs") or 0),
        "total_runs": int(run_snapshot.get("total_runs") or 0),
        "freshness_status": status,
        "failure_reason": reason,
    }


def generate(dsn: str | None = None) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn(dsn)
    try:
        rows = [evaluate_source(conn, spec) for spec in CRITICAL_SOURCES]
    finally:
        conn.close()

    failing = [row["source"] for row in rows if row["freshness_status"] != "fresh"]
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "local-first",
        "critical_sources": rows,
        "overall": {
            "all_critical_sources_fresh": not failing,
            "failing_sources": failing,
            "exit_code": 0 if not failing else 2,
        },
    }

    _write_json(OUTPUT_DIR / "freshness-gate.json", result)
    _write_csv(OUTPUT_DIR / "freshness-gate.csv", rows)
    return result


def _write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2, ensure_ascii=False)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        result = generate()
    except Exception as exc:
        _logger.error("Freshness gate failed: %s", exc, exc_info=True)
        print(f"FALHA TÉCNICA: {exc}")
        sys.exit(1)

    for row in result["critical_sources"]:
        status = row["freshness_status"]
        source = row["source"]
        last_success = row["last_success_at"] or "never"
        print(f"{source}: {status} | last_success_at={last_success}")
        if row["failure_reason"]:
            print(f"  -> {row['failure_reason']}")

    sys.exit(result["overall"]["exit_code"])


if __name__ == "__main__":
    main()
