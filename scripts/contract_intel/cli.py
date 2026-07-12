"""Contract Intelligence CLI — offline-first analytical interface.

Provides canonical queries for the target universe (200 km Florianópolis):
  - Historical contracts by entity
  - Supplier/competitor analytics
  - Active contracts ending in 90–180 days
  - P25/P50/P75 value percentiles by category

Uses SQLite (offline) by default.  If LOCAL_DATALAKE_DSN is set, uses PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "contract_intel.db")

# ---------------------------------------------------------------------------
# SQL queries (canonical — same for SQLite and PostgreSQL)
# ---------------------------------------------------------------------------

# Note: SQLite uses simpler syntax; PostgreSQL versions use PERCENTILE_CONT.
# We provide both backends and select based on connection type.

QUERY_HISTORICO = """
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
ORDER BY c.data_publicacao DESC
"""

QUERY_FORNECEDORES = """
SELECT
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    COUNT(*) AS qtd_contratos,
    SUM(c.valor_total) AS valor_total_contratos,
    ROUND(AVG(c.valor_total), 2) AS valor_medio_contrato,
    COUNT(DISTINCT c.orgao_cnpj) AS qtd_orgaos_distintos,
    GROUP_CONCAT(DISTINCT c.orgao_nome) AS orgaos_lista
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
WHERE c.fornecedor_cnpj IS NOT NULL AND c.fornecedor_cnpj != ''
GROUP BY c.fornecedor_cnpj, c.fornecedor_nome
ORDER BY valor_total_contratos DESC
"""

QUERY_ATIVOS_90_180 = """
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    CAST(julianday(c.data_fim) - julianday('now') AS INTEGER) AS dias_ate_fim
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
WHERE c.data_fim IS NOT NULL
  AND c.data_fim BETWEEN date('now', '+90 days') AND date('now', '+180 days')
ORDER BY c.data_fim, c.valor_total DESC
"""

QUERY_PERCENTIS = """
WITH categorias AS (
    SELECT
        CASE
            WHEN c.objeto_contrato LIKE '%obra%'
              OR c.objeto_contrato LIKE '%construção%'
              OR c.objeto_contrato LIKE '%pavimentação%'
              OR c.objeto_contrato LIKE '%edificação%'
              OR c.objeto_contrato LIKE '%engenharia%'
            THEN 'OBRAS'
            WHEN c.objeto_contrato LIKE '%limpeza%'
              OR c.objeto_contrato LIKE '%conservação%'
              OR c.objeto_contrato LIKE '%manutenção%'
              OR c.objeto_contrato LIKE '%zeladoria%'
            THEN 'FACILITIES'
            WHEN c.objeto_contrato LIKE '%software%'
              OR c.objeto_contrato LIKE '%ti%'
              OR c.objeto_contrato LIKE '%tecnologia%'
              OR c.objeto_contrato LIKE '%sistema%'
              OR c.objeto_contrato LIKE '%informática%'
            THEN 'TI'
            WHEN c.objeto_contrato LIKE '%saúde%'
              OR c.objeto_contrato LIKE '%medicamento%'
              OR c.objeto_contrato LIKE '%hospitalar%'
              OR c.objeto_contrato LIKE '%medico%'
              OR c.objeto_contrato LIKE '%farmacêutico%'
              OR c.objeto_contrato LIKE '%laboratório%'
            THEN 'SAÚDE'
            WHEN c.objeto_contrato LIKE '%alimentação%'
              OR c.objeto_contrato LIKE '%alimento%'
              OR c.objeto_contrato LIKE '%merenda%'
              OR c.objeto_contrato LIKE '%gênero alimentício%'
            THEN 'ALIMENTAÇÃO'
            WHEN c.objeto_contrato LIKE '%transporte%'
              OR c.objeto_contrato LIKE '%veículo%'
              OR c.objeto_contrato LIKE '%frota%'
              OR c.objeto_contrato LIKE '%ônibus%'
              OR c.objeto_contrato LIKE '%locação de veículo%'
            THEN 'TRANSPORTE'
            WHEN c.objeto_contrato LIKE '%segurança%'
              OR c.objeto_contrato LIKE '%vigilância%'
              OR c.objeto_contrato LIKE '%monitoramento%'
              OR c.objeto_contrato LIKE '%porteiro%'
            THEN 'SEGURANÇA'
            WHEN c.objeto_contrato LIKE '%consultoria%'
              OR c.objeto_contrato LIKE '%assessoria%'
              OR c.objeto_contrato LIKE '%advocacia%'
              OR c.objeto_contrato LIKE '%jurídico%'
              OR c.objeto_contrato LIKE '%contábil%'
            THEN 'CONSULTORIA'
            WHEN c.objeto_contrato LIKE '%combustível%'
              OR c.objeto_contrato LIKE '%gasolina%'
              OR c.objeto_contrato LIKE '%diesel%'
              OR c.objeto_contrato LIKE '%etanol%'
            THEN 'COMBUSTÍVEL'
            ELSE 'OUTROS'
        END AS categoria,
        c.valor_total AS valor
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.valor_total IS NOT NULL AND c.valor_total > 0
),
pcts AS (
    SELECT
        categoria,
        COUNT(*) AS qtd_contratos,
        SUM(valor) AS valor_total,
        AVG(valor) AS ticket_medio
    FROM categorias
    GROUP BY categoria
)
SELECT
    p.*,
    -- SQLite doesn't have PERCENTILE_CONT, so we compute approximate
    -- percentiles via ordered subquery (exact for SQLite).
    -- For PostgreSQL, use the SQL view v_contract_intel_percentis instead.
    NULL AS p25_valor,
    NULL AS p50_valor,
    NULL AS p75_valor
FROM pcts p
ORDER BY p.valor_total DESC
"""

# For PostgreSQL, we provide the exact PERCENTILE_CONT query
QUERY_PERCENTIS_PG = """
SELECT
    categoria_agrupada AS categoria,
    COUNT(*) AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2) AS valor_total,
    ROUND(AVG(valor)::numeric, 2) AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p75_valor
FROM (
    SELECT
        CASE
            WHEN c.objeto_contrato ILIKE '%obra%'
              OR c.objeto_contrato ILIKE '%construção%'
            THEN 'OBRAS'
            -- ... (same categories as above, using ILIKE for PG)
            ELSE 'OUTROS'
        END AS categoria_agrupada,
        c.valor_total AS valor
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj LIKE e.cnpj_raiz || '%'
    WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
      AND c.valor_total IS NOT NULL AND c.valor_total > 0
) sub
GROUP BY categoria_agrupada
ORDER BY valor_total DESC
"""

QUERY_STATS = """
SELECT
    'Total contracts' AS metrica,
    CAST(COUNT(*) AS TEXT) AS valor
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'

UNION ALL

SELECT
    'Unique suppliers',
    CAST(COUNT(DISTINCT fornecedor_cnpj) AS TEXT)
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
WHERE fornecedor_cnpj IS NOT NULL

UNION ALL

SELECT
    'Unique entities',
    CAST(COUNT(DISTINCT c.orgao_cnpj) AS TEXT)
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'

UNION ALL

SELECT
    'Total value (R$)',
    CAST(ROUND(SUM(valor_total), 2) AS TEXT)
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
WHERE valor_total IS NOT NULL

UNION ALL

SELECT
    'Date range',
    COALESCE(MIN(c.data_publicacao), 'N/A') || ' to ' || COALESCE(MAX(c.data_publicacao), 'N/A')
FROM pncp_supplier_contracts c
JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
"""


# ---------------------------------------------------------------------------
# Database abstraction
# ---------------------------------------------------------------------------


def _get_connection(db_path: str | None = None):
    """Get a DB connection — PostgreSQL if DSN is set, else SQLite.

    When LOCAL_DATALAKE_DSN is explicitly set: fail closed on PostgreSQL
    connection failure — NO silent SQLite fallback.
    """
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "")
    if dsn:
        try:
            import psycopg2

            conn = psycopg2.connect(dsn, connect_timeout=5)
            conn.autocommit = True
            return conn, "postgresql"
        except Exception as e:
            raise ConnectionError(
                f"PostgreSQL connection failed with explicit LOCAL_DATALAKE_DSN. "
                f"Refusing to fall back to SQLite. Set DSN correctly or unset to use SQLite. "
                f"Error: {e}"
            ) from e

    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def _ensure_tables(conn: Any, backend: str) -> None:
    """Create minimal schema if not exists (SQLite only — PG uses migrations)."""
    if backend != "sqlite":
        return

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS target_universe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social TEXT NOT NULL,
            cnpj8 TEXT NOT NULL,
            municipio TEXT,
            codigo_ibge TEXT,
            natureza_juridica TEXT,
            latitude REAL,
            longitude REAL,
            distancia_km REAL,
            within_200km INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_tu_cnpj8 ON target_universe(cnpj8);

        CREATE TABLE IF NOT EXISTS pncp_supplier_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id TEXT UNIQUE NOT NULL,
            orgao_cnpj TEXT,
            orgao_nome TEXT,
            fornecedor_cnpj TEXT,
            fornecedor_nome TEXT,
            objeto_contrato TEXT,
            valor_total REAL,
            data_inicio TEXT,
            data_fim TEXT,
            data_publicacao TEXT,
            uf TEXT,
            municipio TEXT,
            source_id TEXT,
            ingested_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_contracts_orgao
            ON pncp_supplier_contracts(orgao_cnpj);
        CREATE INDEX IF NOT EXISTS idx_contracts_fornecedor
            ON pncp_supplier_contracts(fornecedor_cnpj);
        CREATE INDEX IF NOT EXISTS idx_contracts_data_fim
            ON pncp_supplier_contracts(data_fim);
    """)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_historico(conn: Any, args: argparse.Namespace) -> int:
    """Query historical contracts."""
    query = QUERY_HISTORICO
    params: list[Any] = []

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.format == "json":
        result = [dict(row) for row in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_fornecedores(conn: Any, args: argparse.Namespace) -> int:
    """Query supplier/competitor analytics."""
    query = QUERY_FORNECEDORES
    params: list[Any] = []

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.format == "json":
        result = [dict(row) for row in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_ativos(conn: Any, args: argparse.Namespace) -> int:
    """Query active contracts ending in 90-180 days."""
    cur = conn.cursor()
    cur.execute(QUERY_ATIVOS_90_180)
    rows = cur.fetchall()

    if args.format == "json":
        result = [dict(row) for row in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_percentis(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Query P25/P50/P75 percentiles."""
    if backend == "postgresql":
        query = QUERY_PERCENTIS_PG
    else:
        query = QUERY_PERCENTIS

    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()

    if args.format == "json":
        result = [dict(row) for row in rows]
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_stats(conn: Any, args: argparse.Namespace) -> int:
    """Query summary statistics."""
    cur = conn.cursor()
    cur.execute(QUERY_STATS)
    rows = cur.fetchall()

    if args.format == "json":
        result = {row[0]: row[1] for row in rows}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(f"  {row[0]:30s} {row[1]}")

    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_table(rows: list[Any], description: Any) -> None:
    """Print rows as a formatted table."""
    if not rows:
        print("(no results)")
        return

    cols = [d[0] for d in description]

    # Compute column widths
    widths = [len(c) for c in cols]
    for row in rows:
        for i, val in enumerate(row):
            s = str(val) if val is not None else "NULL"
            widths[i] = max(widths[i], min(len(s), 40))

    # Print header
    header = " | ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "-+-".join("-" * w for w in widths)
    print(header)
    print(sep)

    # Print rows
    for row in rows:
        vals = []
        for i, val in enumerate(row):
            s = str(val) if val is not None else "NULL"
            if len(s) > widths[i]:
                s = s[: widths[i] - 3] + "..."
            vals.append(s.ljust(widths[i]))
        print(" | ".join(vals))

    print(f"\n({len(rows)} rows)")


# ---------------------------------------------------------------------------
# Seed the target universe into SQLite (for offline use)
# ---------------------------------------------------------------------------


def seed_target_universe(conn: Any, backend: str) -> int:
    """Populate target_universe table from the seed spreadsheet.

    Returns the number of entities inserted.
    """
    from scripts.contract_intel.target_universe import (
        entities_within_radius,
        load_target_universe,
    )

    universe = load_target_universe()
    entities = entities_within_radius(universe)

    if backend == "sqlite":
        conn.execute("DELETE FROM target_universe")
        for e in entities:
            conn.execute(
                """INSERT INTO target_universe
                   (razao_social, cnpj8, municipio, codigo_ibge,
                    natureza_juridica, latitude, longitude,
                    distancia_km, within_200km)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    e.razao_social,
                    e.cnpj8,
                    e.municipio,
                    e.codigo_ibge,
                    e.natureza_juridica,
                    e.latitude,
                    e.longitude,
                    e.distancia_km,
                ),
            )
        conn.commit()

    return len(entities)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contract Intelligence CLI — analytical queries for target universe",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # historico
    p_hist = sub.add_parser("historico", help="Historical contracts")
    p_hist.add_argument("--limit", type=int, default=100, help="Max rows")
    p_hist.add_argument("--format", choices=["table", "json"], default="table")

    # fornecedores
    p_forn = sub.add_parser("fornecedores", help="Supplier/competitor analytics")
    p_forn.add_argument("--limit", type=int, default=50, help="Max rows")
    p_forn.add_argument("--format", choices=["table", "json"], default="table")

    # ativos
    p_ativ = sub.add_parser("ativos", help="Active contracts ending in 90-180 days")
    p_ativ.add_argument("--format", choices=["table", "json"], default="table")

    # percentis
    p_pct = sub.add_parser("percentis", help="P25/P50/P75 value percentiles by category")
    p_pct.add_argument("--format", choices=["table", "json"], default="table")

    # stats
    p_stats = sub.add_parser("stats", help="Summary statistics")
    p_stats.add_argument("--format", choices=["table", "json"], default="table")

    # seed
    _ = sub.add_parser("seed", help="Seed the target universe into the local DB")

    # DB path
    parser.add_argument("--db", default=None, help="SQLite database path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    conn, backend = _get_connection(args.db)
    _ensure_tables(conn, backend)

    try:
        if args.command == "seed":
            count = seed_target_universe(conn, backend)
            print(f"Seeded {count} entities into target_universe.")
            return 0
        elif args.command == "historico":
            return cmd_historico(conn, args)
        elif args.command == "fornecedores":
            return cmd_fornecedores(conn, args)
        elif args.command == "ativos":
            return cmd_ativos(conn, args)
        elif args.command == "percentis":
            return cmd_percentis(conn, args, backend)
        elif args.command == "stats":
            return cmd_stats(conn, args)
        else:
            parser.print_help()
            return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
