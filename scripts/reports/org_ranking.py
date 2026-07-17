#!/usr/bin/env python3
"""Minimal organ ranking for commercial reports (next-30d).

Ranks organs by contract count / value:

1. Prefer ``pncp_supplier_contracts`` when rows exist
   → semantic: CONTRATADO (valor_total)
2. Else fall back to ``opportunity_intel`` (if rows) and/or ``pncp_raw_bids``
   → semantic labels: ESTIMADO (valor_estimado / valor_total_estimado)

Writes CSV + JSON under ``output/reports/``.

Usage:
    LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \\
      python scripts/reports/org_ranking.py --uf SC
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_DSN = "postgresql://test:test@127.0.0.1:5433/pncp_datalake"
DSN = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL") or DEFAULT_DSN

DEFAULT_JSON = _PROJECT_ROOT / "output" / "reports" / "org-ranking-next30d.json"
DEFAULT_CSV = _PROJECT_ROOT / "output" / "reports" / "org-ranking-next30d.csv"


def get_conn(dsn: str):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        raise SystemExit(2) from None
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def query(conn, sql: str, params: list | tuple | None = None) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def scalar(conn, sql: str, params: list | tuple | None = None) -> Any:
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _serialize_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        item: dict[str, Any] = {}
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                item[k] = v.isoformat()
            elif v is not None and not isinstance(v, (str, int, float, bool)):
                try:
                    item[k] = float(v)
                except (TypeError, ValueError):
                    item[k] = str(v)
            else:
                item[k] = v
        out.append(item)
    return out


def count_contracts(conn, uf: str | None) -> int:
    try:
        n = scalar(
            conn,
            """
            SELECT COUNT(*) FROM pncp_supplier_contracts
            WHERE is_active = true
              AND (%s::text IS NULL OR uf = %s)
            """,
            (uf, uf),
        )
        return int(n or 0)
    except Exception:
        return 0


def rank_from_contracts(conn, uf: str | None, limit: int) -> list[dict]:
    """CONTRATADO — count/value from pncp_supplier_contracts.valor_total."""
    rows = query(
        conn,
        """
        SELECT
            COALESCE(orgao_nome, orgao_cnpj, '(sem órgão)') AS orgao,
            orgao_cnpj,
            uf,
            COUNT(*)::int AS qtd,
            ROUND(SUM(COALESCE(valor_total, 0))::numeric, 2) AS valor_total,
            'CONTRATADO'::text AS valor_semantica,
            'pncp_supplier_contracts'::text AS source_table,
            'valor_total'::text AS value_column
        FROM pncp_supplier_contracts
        WHERE is_active = true
          AND (%s::text IS NULL OR uf = %s)
        GROUP BY COALESCE(orgao_nome, orgao_cnpj, '(sem órgão)'), orgao_cnpj, uf
        ORDER BY qtd DESC, valor_total DESC NULLS LAST
        LIMIT %s
        """,
        (uf, uf, limit),
    )
    return _serialize_rows(rows)


def rank_from_opportunity_intel(conn, uf: str | None, limit: int) -> list[dict]:
    """ESTIMADO — count/value from opportunity_intel.valor_estimado."""
    rows = query(
        conn,
        """
        SELECT
            COALESCE(orgao_nome, orgao_cnpj, '(sem órgão)') AS orgao,
            orgao_cnpj,
            uf,
            COUNT(*)::int AS qtd,
            ROUND(SUM(COALESCE(valor_estimado, 0))::numeric, 2) AS valor_total,
            'ESTIMADO'::text AS valor_semantica,
            'opportunity_intel'::text AS source_table,
            'valor_estimado'::text AS value_column
        FROM opportunity_intel
        WHERE is_active = true
          AND (%s::text IS NULL OR uf = %s)
          AND orgao_nome IS NOT NULL
        GROUP BY COALESCE(orgao_nome, orgao_cnpj, '(sem órgão)'), orgao_cnpj, uf
        ORDER BY qtd DESC, valor_total DESC NULLS LAST
        LIMIT %s
        """,
        (uf, uf, limit),
    )
    return _serialize_rows(rows)


def rank_from_raw_bids(conn, uf: str | None, limit: int) -> list[dict]:
    """ESTIMADO — count/value from pncp_raw_bids.valor_total_estimado."""
    rows = query(
        conn,
        """
        SELECT
            COALESCE(orgao_razao_social, orgao_cnpj, '(sem órgão)') AS orgao,
            orgao_cnpj,
            uf,
            COUNT(*)::int AS qtd,
            ROUND(SUM(COALESCE(valor_total_estimado, 0))::numeric, 2) AS valor_total,
            'ESTIMADO'::text AS valor_semantica,
            'pncp_raw_bids'::text AS source_table,
            'valor_total_estimado'::text AS value_column
        FROM pncp_raw_bids
        WHERE is_active = true
          AND (%s::text IS NULL OR uf = %s)
        GROUP BY COALESCE(orgao_razao_social, orgao_cnpj, '(sem órgão)'), orgao_cnpj, uf
        ORDER BY qtd DESC, valor_total DESC NULLS LAST
        LIMIT %s
        """,
        (uf, uf, limit),
    )
    return _serialize_rows(rows)


def build_ranking(conn, uf: str | None, limit: int) -> dict[str, Any]:
    n_contracts = count_contracts(conn, uf)
    source_used: str
    semantic: str
    rows: list[dict]
    notes: list[str] = []

    if n_contracts > 0:
        rows = rank_from_contracts(conn, uf, limit)
        source_used = "pncp_supplier_contracts"
        semantic = "CONTRATADO"
        notes.append(
            f"Ranking derivado de pncp_supplier_contracts ({n_contracts} contratos ativos). "
            "valor_semantica=CONTRATADO (coluna valor_total)."
        )
    else:
        notes.append(
            "pncp_supplier_contracts vazia (0 linhas ativas) — "
            "fallback para opportunity_intel / pncp_raw_bids com rótulo ESTIMADO."
        )
        oi_rows = rank_from_opportunity_intel(conn, uf, limit)
        if oi_rows:
            rows = oi_rows
            source_used = "opportunity_intel"
            semantic = "ESTIMADO"
            notes.append(
                "Fonte: opportunity_intel.valor_estimado (ESTIMADO). "
                "NÃO confundir com valor contratado."
            )
        else:
            notes.append("opportunity_intel sem linhas para o filtro — tentando pncp_raw_bids.")
            bid_rows = rank_from_raw_bids(conn, uf, limit)
            rows = bid_rows
            source_used = "pncp_raw_bids"
            semantic = "ESTIMADO"
            notes.append(
                "Fonte: pncp_raw_bids.valor_total_estimado (ESTIMADO). "
                "NÃO confundir com valor contratado / homologado."
            )

    status = "OK" if rows else "INSUFFICIENT"
    return {
        "status": status,
        "source_table": source_used,
        "valor_semantica": semantic,
        "uf_filter": uf,
        "limit": limit,
        "count": len(rows),
        "rows": rows,
        "notes": notes,
        "claims": {
            "allowed": [
                f"Ranking de órgãos por contagem/valor com semântica explícita ({semantic}).",
                f"Tabela-fonte: {source_used}.",
            ],
            "forbidden": [
                "Afirmar 'mercado completo SC' com amostra pequena.",
                "Tratar ESTIMADO como CONTRATADO.",
                "Inferir contratos vincendos a partir de pncp_raw_bids.",
            ],
        },
    }


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "orgao",
        "orgao_cnpj",
        "uf",
        "qtd",
        "valor_total",
        "valor_semantica",
        "source_table",
        "value_column",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            writer.writerow({"rank": i, **row})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rank organs by contract/bid count and value")
    p.add_argument("--uf", default="SC", help="UF filter (default SC; empty string = all)")
    p.add_argument("--limit", type=int, default=50, help="Max organs (default 50)")
    p.add_argument("--dsn", default=None, help="PostgreSQL DSN override")
    p.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON,
        help=f"JSON output (default: {DEFAULT_JSON})",
    )
    p.add_argument(
        "--csv-out",
        type=Path,
        default=DEFAULT_CSV,
        help=f"CSV output (default: {DEFAULT_CSV})",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dsn = args.dsn or DSN
    uf = args.uf.strip() or None

    try:
        conn = get_conn(dsn)
    except Exception as exc:
        print(f"ERROR: cannot connect to DB: {exc}", file=sys.stderr)
        return 2

    try:
        ranking = build_ranking(conn, uf=uf, limit=args.limit)
    finally:
        conn.close()

    payload = {
        "schema_version": 1,
        "title": "Ranking de órgãos (next-30d)",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "dsn_host": dsn.split("@", 1)[-1] if "@" in dsn else "configured",
        "ranking": ranking,
    }

    json_path: Path = args.json_out
    csv_path: Path = args.csv_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(ranking["rows"], csv_path)

    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(
        f"  status={ranking['status']} source={ranking['source_table']} "
        f"semantic={ranking['valor_semantica']} organs={ranking['count']} uf={uf or 'ALL'}"
    )
    for note in ranking["notes"]:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
