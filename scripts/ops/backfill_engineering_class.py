#!/usr/bin/env python3
"""Resumable backfill of persisted engineering class (#544)."""

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

from scripts.contracts.engineering_class import (  # noqa: E402
    attach_engineering_class,
    stamp_engineering_class_labels,
)

SELECT_SQL = """
SELECT contrato_id, objeto_contrato, fornecedor_nome,
       categoria_processo_nome, regime_execucao_nome, tipo_contrato_nome, srp
FROM public.pncp_supplier_contracts
WHERE contrato_id > %s
ORDER BY contrato_id
LIMIT %s
"""


def load_batch(conn: Any, after: str, limit: int) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(SELECT_SQL, (after or "", int(limit)))
    rows = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append(
                {
                    "contrato_id": row[0],
                    "objeto_contrato": row[1],
                    "fornecedor_nome": row[2],
                    "categoria_processo_nome": row[3],
                    "regime_execucao_nome": row[4],
                    "tipo_contrato_nome": row[5],
                    "srp": row[6],
                }
            )
    return out


def run_backfill(conn: Any, *, after: str, limit: int, dry_run: bool) -> dict[str, Any]:
    batch = load_batch(conn, after, limit)
    classified = [attach_engineering_class(dict(row)) for row in batch]
    updated = 0 if dry_run else stamp_engineering_class_labels(conn, classified)
    if not dry_run:
        conn.commit()
    return {
        "planned": len(classified),
        "updated": updated,
        "cursor": classified[-1]["contrato_id"] if classified else after or None,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--after", default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dsn:
        raise SystemExit("LOCAL_DATALAKE_DSN or --dsn is required")
    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        print(json.dumps(run_backfill(conn, after=args.after, limit=args.limit, dry_run=args.dry_run), sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
