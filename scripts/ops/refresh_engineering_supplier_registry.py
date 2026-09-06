#!/usr/bin/env python3
"""Expand supplier_registry to engineering suppliers of the last 24 months (#549).

Universe: official PNCP categoria_processo (migration 112), never objeto regex.
Cadastral contact stays on enriched_entities with enriched_at + source.
Does not discover decision-makers.

Usage::

    python3 -m scripts.ops.refresh_engineering_supplier_registry --limit 100 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.supplier_registry import upsert_registry_rows  # noqa: E402
from scripts.ops.ingest_supplier_registry_brasilapi import fetch_one  # noqa: E402

UNIVERSE_SQL = """
SELECT cnpj14
FROM public.v_engineering_supplier_universe
WHERE cnpj14 > %s
ORDER BY cnpj14
LIMIT %s
"""

MISSING_SQL = """
SELECT universe.cnpj14
FROM public.v_engineering_supplier_universe universe
LEFT JOIN public.supplier_registry registry ON registry.cnpj14 = universe.cnpj14
WHERE registry.cnpj14 IS NULL
  AND universe.cnpj14 > %s
ORDER BY universe.cnpj14
LIMIT %s
"""


def list_candidates(conn: Any, *, after: str, limit: int, missing_only: bool) -> list[str]:
    cur = conn.cursor()
    sql = MISSING_SQL if missing_only else UNIVERSE_SQL
    cur.execute(sql, (after or "", int(limit)))
    rows = cur.fetchall() or []
    out: list[str] = []
    for row in rows:
        value = row[0] if not isinstance(row, dict) else row.get("cnpj14")
        if value:
            out.append(str(value))
    return out


def record_run(
    conn: Any,
    *,
    run_id: str,
    cursor: str | None,
    planned: int,
    upserted: int,
    skipped: int,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO public.engineering_supplier_registry_runs (
            run_id, cursor_cnpj14, planned, upserted, skipped, last_run_at, notes
        ) VALUES (%s, %s, %s, %s, %s, NOW(), 'engineering-supplier-registry-v1')
        ON CONFLICT (run_id) DO UPDATE SET
            cursor_cnpj14 = EXCLUDED.cursor_cnpj14,
            planned = public.engineering_supplier_registry_runs.planned + EXCLUDED.planned,
            upserted = public.engineering_supplier_registry_runs.upserted + EXCLUDED.upserted,
            skipped = public.engineering_supplier_registry_runs.skipped + EXCLUDED.skipped,
            last_run_at = NOW()
        """,
        (run_id, cursor, planned, upserted, skipped),
    )


def refresh(
    conn: Any,
    *,
    after: str,
    limit: int,
    run_id: str,
    missing_only: bool,
    dry_run: bool,
    fetcher=fetch_one,
) -> dict[str, Any]:
    planned = list_candidates(conn, after=after, limit=limit, missing_only=missing_only)
    rows: list[dict[str, Any]] = []
    skipped = 0
    for cnpj in planned:
        payload = None if dry_run else fetcher(cnpj)
        if payload is None:
            skipped += 1
            continue
        rows.append(payload)
    upserted = 0 if dry_run else upsert_registry_rows(conn, rows)
    cursor = planned[-1] if planned else after or None
    if not dry_run:
        record_run(
            conn,
            run_id=run_id,
            cursor=cursor,
            planned=len(planned),
            upserted=upserted,
            skipped=skipped,
        )
        conn.commit()
    return {
        "planned": len(planned),
        "upserted": upserted,
        "skipped": skipped,
        "cursor": cursor,
        "dry_run": dry_run,
        "missing_only": missing_only,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--after", default="", help="Resume after this CNPJ14 (exclusive).")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--run-id", default="engineering-registry-default")
    parser.add_argument("--all", action="store_true", help="Re-refresh already registered CNPJs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dsn:
        raise SystemExit("LOCAL_DATALAKE_DSN or --dsn is required")
    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        result = refresh(
            conn,
            after=args.after,
            limit=args.limit,
            run_id=args.run_id,
            missing_only=not args.all,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
