"""Contract Intelligence Truth v1 — CLI for PostgreSQL DataLake.

Provides canonical queries for the target universe (200 km Florianópolis):
  - historical_contracts — 3-year contract history
  - competitor_winners — supplier rankings by count/value/ticket/concentration
  - expiring_contracts — contracts ending in 90–180 days
  - manifesto — per-capability readiness manifest (JSON/CSV)

Uses PostgreSQL views as the canonical query layer.
SQLite is available as fixture/adapter only, never as proof of readiness.

Design constraints (per goal criteria):
  - All queries use the REAL PostgreSQL column names.
  - "valor_global" is NOT called "preço praticado".
  - Readiness manifest is per-capability, with conservative denominators.
  - Exit code non-zero below 95% readiness or with unresolved uncertainty.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "contract_intel.db")
OUTPUT_DIR = str(_PROJECT_ROOT / "output" / "readiness")
READINESS_THRESHOLD = 0.95

# ---------------------------------------------------------------------------
# Canonical SQL queries (PostgreSQL — real column names)
# ---------------------------------------------------------------------------

# These queries match the views defined in migration 026.
# When views exist, we query them directly. When they don't (SQLite),
# we fall back to inline queries adapted for the backend.

PG_QUERY_HISTORICAL = """
SELECT
    contrato_id,
    orgao_cnpj,
    orgao_nome,
    fornecedor_cnpj,
    fornecedor_nome,
    objeto_contrato,
    valor_contrato,
    data_inicio_contrato,
    data_fim_contrato,
    uf,
    municipio,
    ente_razao_social,
    ente_municipio,
    ente_distancia_km
FROM v_contract_historical
ORDER BY data_inicio_contrato DESC NULLS LAST
"""

PG_QUERY_SUPPLIERS = """
SELECT
    fornecedor_cnpj,
    fornecedor_nome,
    qtd_contratos,
    valor_total_contratos,
    ticket_medio_contrato,
    qtd_orgaos_distintos,
    hhi_concentracao,
    orgaos_lista
FROM v_supplier_winners
"""

PG_QUERY_EXPIRING = """
SELECT
    contrato_id,
    orgao_cnpj,
    orgao_nome,
    fornecedor_cnpj,
    fornecedor_nome,
    objeto_contrato,
    valor_contrato,
    data_inicio_contrato,
    data_fim_contrato,
    dias_ate_fim,
    uf,
    municipio,
    ente_razao_social
FROM v_expiring_contracts
ORDER BY dias_ate_fim, valor_contrato DESC NULLS LAST
"""

# Readiness queries — per-capability coverage against sc_public_entities

PG_QUERY_READINESS_HISTORICAL = """
SELECT
    COUNT(DISTINCT e.id)                                                   AS total_entes,
    COUNT(DISTINCT CASE WHEN c.numero_controle_pncp IS NOT NULL
                        THEN e.id END)                                     AS entes_com_contratos,
    CASE WHEN COUNT(DISTINCT e.id) > 0
         THEN ROUND(COUNT(DISTINCT CASE WHEN c.numero_controle_pncp IS NOT NULL
                                        THEN e.id END)::numeric
                    / COUNT(DISTINCT e.id)::numeric, 4)
         ELSE 0.0 END                                                      AS coverage
FROM sc_public_entities e
LEFT JOIN pncp_supplier_contracts c
    ON c.orgao_cnpj8 = e.cnpj_8
    AND c.is_active IS TRUE
    AND c.data_assinatura >= (CURRENT_DATE - INTERVAL '3 years')
WHERE e.raio_200km IS TRUE
  AND e.is_active IS TRUE
"""

PG_QUERY_READINESS_SUPPLIERS = """
SELECT
    COUNT(DISTINCT e.id)                                                   AS total_entes,
    COUNT(DISTINCT CASE WHEN c.ni_fornecedor IS NOT NULL
                          AND c.ni_fornecedor != ''
                        THEN e.id END)                                     AS entes_com_fornecedores,
    CASE WHEN COUNT(DISTINCT e.id) > 0
         THEN ROUND(COUNT(DISTINCT CASE WHEN c.ni_fornecedor IS NOT NULL
                                          AND c.ni_fornecedor != ''
                                        THEN e.id END)::numeric
                    / COUNT(DISTINCT e.id)::numeric, 4)
         ELSE 0.0 END                                                      AS coverage
FROM sc_public_entities e
LEFT JOIN pncp_supplier_contracts c
    ON c.orgao_cnpj8 = e.cnpj_8
    AND c.is_active IS TRUE
WHERE e.raio_200km IS TRUE
  AND e.is_active IS TRUE
"""

PG_QUERY_READINESS_EXPIRING = """
SELECT
    COUNT(DISTINCT e.id)                                                   AS total_entes,
    COUNT(DISTINCT CASE WHEN c.data_fim_vigencia IS NOT NULL
                          AND c.data_fim_vigencia BETWEEN
                              (CURRENT_DATE + INTERVAL '90 days')
                              AND (CURRENT_DATE + INTERVAL '180 days')
                        THEN e.id END)                                     AS entes_com_expirando,
    COUNT(DISTINCT e.id)                                                   AS total_entes_denominator,
    -- Denominator stays as total entities — even those without contracts
    CASE WHEN COUNT(DISTINCT e.id) > 0
         THEN ROUND(COUNT(DISTINCT CASE WHEN c.data_fim_vigencia IS NOT NULL
                                          AND c.data_fim_vigencia BETWEEN
                                              (CURRENT_DATE + INTERVAL '90 days')
                                              AND (CURRENT_DATE + INTERVAL '180 days')
                                        THEN e.id END)::numeric
                    / COUNT(DISTINCT e.id)::numeric, 4)
         ELSE 0.0 END                                                      AS coverage,
    COUNT(*) FILTER (WHERE c.data_fim_vigencia IS NULL AND c.numero_controle_pncp IS NOT NULL)
        AS contratos_sem_data_fim,
    COUNT(*) FILTER (WHERE c.numero_controle_pncp IS NOT NULL)
        AS total_contratos_no_raio
FROM sc_public_entities e
LEFT JOIN pncp_supplier_contracts c
    ON c.orgao_cnpj8 = e.cnpj_8
    AND c.is_active IS TRUE
WHERE e.raio_200km IS TRUE
  AND e.is_active IS TRUE
"""

# ---------------------------------------------------------------------------
# Database abstraction
# ---------------------------------------------------------------------------


def _get_connection(db_path: str | None = None) -> tuple[Any, str]:
    """Get DB connection — PostgreSQL if DSN set, else SQLite.

    When LOCAL_DATALAKE_DSN is set: fail closed on PG connection failure.
    """
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "")
    if dsn:
        try:
            import psycopg2  # noqa: F811

            conn = psycopg2.connect(dsn, connect_timeout=10)
            conn.autocommit = True
            return conn, "postgresql"
        except Exception as e:
            raise ConnectionError(
                f"PostgreSQL connection failed with explicit LOCAL_DATALAKE_DSN. "
                f"Refusing to fall back to SQLite. Error: {e}"
            ) from e

    path = db_path or DEFAULT_DB_PATH
    import sqlite3

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def _ensure_views_pg(cur: Any) -> None:
    """Apply migration 026 views if they don't exist."""
    migration_path = _PROJECT_ROOT / "db" / "migrations" / "026_contract_intel_truth_v1.sql"
    if not migration_path.exists():
        return
    try:
        cur.execute(migration_path.read_text())
    except Exception:
        pass  # Views may already exist or migration already applied


def _ensure_tables(conn: Any, backend: str) -> None:
    """Create minimal SQLite schema for offline/fixture use."""
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
            numero_controle_pncp TEXT UNIQUE NOT NULL,
            ni_fornecedor TEXT,
            nome_fornecedor TEXT,
            orgao_cnpj TEXT,
            orgao_nome TEXT,
            objeto_contrato TEXT,
            valor_global REAL,
            data_assinatura TEXT,
            data_fim_vigencia TEXT,
            uf TEXT,
            municipio TEXT,
            esfera TEXT,
            nr_contrato TEXT,
            ano INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            ingested_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_psc_orgao
            ON pncp_supplier_contracts(orgao_cnpj);
        CREATE INDEX IF NOT EXISTS idx_psc_fornecedor
            ON pncp_supplier_contracts(ni_fornecedor);
        CREATE INDEX IF NOT EXISTS idx_psc_data_fim
            ON pncp_supplier_contracts(data_fim_vigencia);
        CREATE INDEX IF NOT EXISTS idx_psc_data_assinatura
            ON pncp_supplier_contracts(data_assinatura);
    """)


def _query_to_dicts(cur: Any, rows: list[Any]) -> list[dict[str, Any]]:
    """Convert cursor results to dicts."""
    cols = [d[0] for d in cur.description]
    result: list[dict[str, Any]] = []
    for row in rows:
        d: dict[str, Any] = {}
        for i, col in enumerate(cols):
            val = row[i]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            d[col] = val
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_historico(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Query historical contracts."""
    if backend == "postgresql":
        query = PG_QUERY_HISTORICAL
    else:
        query = _sqlite_historico_query()
    params: list[Any] = []

    if args.limit:
        query += " LIMIT %s" if backend == "postgresql" else " LIMIT ?"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.format == "json":
        result = _query_to_dicts(cur, rows)
        _output(args, result)
    elif args.format == "csv":
        result = _query_to_dicts(cur, rows)
        _write_csv(args, result)
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_fornecedores(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Query supplier/competitor analytics."""
    if backend == "postgresql":
        query = PG_QUERY_SUPPLIERS
    else:
        query = _sqlite_fornecedores_query()
    params: list[Any] = []

    if args.limit:
        query += " LIMIT %s" if backend == "postgresql" else " LIMIT ?"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.format == "json":
        result = _query_to_dicts(cur, rows)
        _output(args, result)
    elif args.format == "csv":
        result = _query_to_dicts(cur, rows)
        _write_csv(args, result)
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_ativos(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Query expiring contracts (90-180 days)."""
    if backend == "postgresql":
        query = PG_QUERY_EXPIRING
    else:
        query = _sqlite_expiring_query()
    params: list[Any] = []

    if args.limit:
        query += " LIMIT %s" if backend == "postgresql" else " LIMIT ?"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    if args.format == "json":
        result = _query_to_dicts(cur, rows)
        _output(args, result)
    elif args.format == "csv":
        result = _query_to_dicts(cur, rows)
        _write_csv(args, result)
    else:
        _print_table(rows, cur.description)

    return 0


def cmd_manifesto(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Generate per-capability readiness manifest.

    Each capability gets a readiness assessment:
    - historical_contracts: % of target entities with contracts in 3yr window
    - competitor_winners: % of target entities with identifiable suppliers
    - expiring_contracts: % of target entities with contracts expiring in 90-180d

    Returns exit code 0 if >= 95% on all capabilities, non-zero otherwise.
    """
    manifesto: dict[str, Any] = {
        "generated_at": date.today().isoformat(),
        "threshold": READINESS_THRESHOLD,
        "backend": backend,
        "capacities": {},
        "overall": {},
    }

    if backend == "postgresql":
        manifesto.update(_manifesto_pg(conn))
    else:
        manifesto.update(_manifesto_sqlite(conn))

    # Determine overall readiness
    caps = manifesto.get("capacities", {})
    all_above_threshold = True
    unresolved_uncertainties: list[str] = []

    for cap_name, cap_data in caps.items():
        if cap_data.get("uncertainty", False):
            unresolved_uncertainties.append(cap_name)
        if cap_data.get("coverage", 0.0) < READINESS_THRESHOLD:
            all_above_threshold = False

    manifesto["overall"] = {
        "all_capabilities_above_threshold": all_above_threshold,
        "unresolved_uncertainties": unresolved_uncertainties,
        "exit_code": 0 if (all_above_threshold and not unresolved_uncertainties) else 1,
    }

    # Output
    if args.format == "json":
        _output(args, manifesto)
    else:
        _print_manifesto_table(manifesto)
        if args.output:
            _write_json(args, manifesto)

    # Generate CSV gaps report
    _write_manifesto_csv(manifesto, args)

    return manifesto["overall"]["exit_code"]


def cmd_stats(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Query summary statistics."""
    if backend == "postgresql":
        query = _pg_stats_query()
    else:
        query = _sqlite_stats_query()

    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()

    if args.format == "json":
        result = {row[0]: row[1] for row in rows}
        _output(args, result)
    else:
        for row in rows:
            print(f"  {row[0]:35s} {row[1]}")

    return 0


def seed_target_universe(conn: Any, backend: str) -> int:
    """Populate target_universe table from seed spreadsheet."""
    from scripts.contract_intel.target_universe import (
        entities_within_radius,
        load_target_universe,
    )

    universe = load_target_universe()
    entities = entities_within_radius(universe)

    if backend == "sqlite":
        cur = conn.cursor()
        cur.execute("DELETE FROM target_universe")
        for e in entities:
            cur.execute(
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
# Manifesto helpers
# ---------------------------------------------------------------------------


def _manifesto_pg(conn: Any) -> dict[str, Any]:
    """Build readiness manifest from PostgreSQL."""
    cur = conn.cursor()
    capacities: dict[str, dict[str, Any]] = {}

    # 1. historical_contracts
    cur.execute(PG_QUERY_READINESS_HISTORICAL)
    row = cur.fetchone()
    total_entes = row[0] if row else 0
    entes_com = row[1] if row else 0
    cov = float(row[2]) if row else 0.0
    capacities["historical_contracts"] = {
        "description": "Entes-alvo com pelo menos 1 contrato nos últimos 3 anos",
        "denominator": total_entes,
        "numerator": entes_com,
        "coverage": round(cov, 4),
        "threshold": READINESS_THRESHOLD,
        "ready": cov >= READINESS_THRESHOLD,
        "uncertainty": False,
        "uncertainty_reason": None,
        "semantic_note": "valor_global (PNCP) — não é preço praticado",
        "window": "3 anos a partir de data_assinatura",
    }

    # 2. competitor_winners
    cur.execute(PG_QUERY_READINESS_SUPPLIERS)
    row = cur.fetchone()
    total_entes = row[0] if row else 0
    entes_com = row[1] if row else 0
    cov = float(row[2]) if row else 0.0
    capacities["competitor_winners"] = {
        "description": "Entes-alvo com pelo menos 1 fornecedor vencedor identificável",
        "denominator": total_entes,
        "numerator": entes_com,
        "coverage": round(cov, 4),
        "threshold": READINESS_THRESHOLD,
        "ready": cov >= READINESS_THRESHOLD,
        "uncertainty": False,
        "uncertainty_reason": None,
        "semantic_note": "Apenas vencedores históricos (contratos assinados), não todos os licitantes",
        "supplier_count_note": _count_distinct_suppliers_pg(cur),
    }

    # 3. expiring_contracts
    cur.execute(PG_QUERY_READINESS_EXPIRING)
    row = cur.fetchone()
    total_entes = row[0] if row else 0
    entes_com = row[1] if row else 0
    cov = float(row[3]) if row else 0.0
    contratos_sem_fim = row[4] if row else 0
    total_contratos = row[5] if row else 0
    pct_sem_fim = round(contratos_sem_fim / total_contratos * 100, 1) if total_contratos else 0.0

    uncertainty = pct_sem_fim > 50  # More than 50% missing data_fim = uncertainty
    capacities["expiring_contracts"] = {
        "description": "Entes-alvo com contratos terminando em 90-180 dias",
        "denominator": total_entes,
        "numerator": entes_com,
        "coverage": round(cov, 4),
        "threshold": READINESS_THRESHOLD,
        "ready": cov >= READINESS_THRESHOLD and not uncertainty,
        "uncertainty": uncertainty,
        "uncertainty_reason": (
            f"{pct_sem_fim}% dos contratos no raio têm data_fim_vigencia NULL "
            f"({contratos_sem_fim} de {total_contratos}). "
            f"Status de vigência é inferido, não declarado pelo PNCP."
        )
        if uncertainty
        else None,
        "semantic_note": (
            "Status do contrato inferido por data_fim_vigencia vs CURRENT_DATE. "
            "PNCP não possui campo 'status' direto. "
            "Contratos sem data_fim_vigencia são excluídos desta capacidade."
        ),
        "contratos_sem_data_fim": contratos_sem_fim,
        "total_contratos_no_raio": total_contratos,
        "pct_contratos_sem_data_fim": pct_sem_fim,
    }

    return {"capacities": capacities}


def _manifesto_sqlite(conn: Any) -> dict[str, Any]:
    """Build readiness manifest from SQLite (limited — no views)."""
    capacities: dict[str, dict[str, Any]] = {
        "historical_contracts": {
            "description": "Entes-alvo com contratos nos últimos 3 anos",
            "ready": False,
            "uncertainty": True,
            "uncertainty_reason": "SQLite backend — manifesto requires PostgreSQL",
            "coverage": 0.0,
        },
        "competitor_winners": {
            "description": "Entes-alvo com fornecedores vencedores identificáveis",
            "ready": False,
            "uncertainty": True,
            "uncertainty_reason": "SQLite backend — manifesto requires PostgreSQL",
            "coverage": 0.0,
        },
        "expiring_contracts": {
            "description": "Entes-alvo com contratos terminando em 90-180 dias",
            "ready": False,
            "uncertainty": True,
            "uncertainty_reason": "SQLite backend — manifesto requires PostgreSQL",
            "coverage": 0.0,
        },
    }
    return {"capacities": capacities}


def _count_distinct_suppliers_pg(cur: Any) -> str:
    """Count distinct suppliers in target universe."""
    try:
        cur.execute("""
            SELECT COUNT(DISTINCT c.ni_fornecedor)
            FROM pncp_supplier_contracts c
            JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
            WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
              AND c.ni_fornecedor IS NOT NULL AND c.ni_fornecedor != ''
        """)
        return str(cur.fetchone()[0])
    except Exception:
        return "N/A"


def _print_manifesto_table(manifesto: dict[str, Any]) -> None:
    """Print manifesto as formatted table."""
    caps = manifesto.get("capacities", {})
    overall = manifesto.get("overall", {})

    print("\n  Readiness Manifest — Contract Intelligence Truth v1")
    print(f"  Generated: {manifesto.get('generated_at', 'N/A')}")
    print(f"  Threshold: {manifesto.get('threshold', READINESS_THRESHOLD):.0%}")
    print(f"  Backend: {manifesto.get('backend', 'N/A')}")
    print()
    print(f"  {'Capability':<30s} {'Coverage':>8s} {'Ready':>6s} {'Uncertain':>10s}")
    print(f"  {'-' * 30} {'-' * 8} {'-' * 6} {'-' * 10}")

    for name, cap in caps.items():
        cov_str = f"{cap.get('coverage', 0):.1%}" if isinstance(cap.get("coverage"), (int, float)) else "N/A"
        ready_str = "SIM" if cap.get("ready") else "NÃO"
        uncert_str = "SIM" if cap.get("uncertainty") else "NÃO"
        print(f"  {name:<30s} {cov_str:>8s} {ready_str:>6s} {uncert_str:>10s}")

    print()
    for name, cap in caps.items():
        if cap.get("semantic_note"):
            print(f"  [{name}] {cap['semantic_note']}")
        if cap.get("uncertainty_reason"):
            print(f"  [{name}] ⚠ {cap['uncertainty_reason']}")

    print()
    exit_code = overall.get("exit_code", 1)
    if exit_code == 0:
        print(f"  ✅ All capabilities above {READINESS_THRESHOLD:.0%} — READY")
    else:
        unresolved = overall.get("unresolved_uncertainties", [])
        if unresolved:
            print(f"  ❌ Unresolved uncertainties: {', '.join(unresolved)}")
        print(f"  ❌ NOT READY (exit code {exit_code})")
    print()


def _write_manifesto_csv(manifesto: dict[str, Any], args: argparse.Namespace) -> None:
    """Write gaps report as CSV."""
    caps = manifesto.get("capacities", {})
    output_path = args.output_csv or os.path.join(OUTPUT_DIR, "manifesto-gaps.csv")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "capability",
                "description",
                "denominator",
                "numerator",
                "coverage",
                "threshold",
                "ready",
                "uncertainty",
                "uncertainty_reason",
                "semantic_note",
            ]
        )
        for name, cap in caps.items():
            writer.writerow(
                [
                    name,
                    cap.get("description", ""),
                    cap.get("denominator", ""),
                    cap.get("numerator", ""),
                    cap.get("coverage", ""),
                    cap.get("threshold", READINESS_THRESHOLD),
                    str(cap.get("ready", False)),
                    str(cap.get("uncertainty", False)),
                    cap.get("uncertainty_reason", ""),
                    cap.get("semantic_note", ""),
                ]
            )

    if not getattr(args, "quiet", False):
        print(f"  Gaps CSV: {output_path}")


# ---------------------------------------------------------------------------
# SQLite fallback queries (simplified, for fixture/testing only)
# ---------------------------------------------------------------------------


def _sqlite_historico_query() -> str:
    return """
    SELECT
        c.numero_controle_pncp AS contrato_id,
        c.orgao_cnpj,
        c.orgao_nome,
        c.ni_fornecedor AS fornecedor_cnpj,
        c.nome_fornecedor AS fornecedor_nome,
        c.objeto_contrato,
        c.valor_global AS valor_contrato,
        c.data_assinatura AS data_inicio_contrato,
        c.data_fim_vigencia AS data_fim_contrato,
        c.uf,
        c.municipio,
        u.razao_social AS ente_razao_social,
        u.municipio AS ente_municipio,
        u.distancia_km AS ente_distancia_km
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1
      AND c.data_assinatura >= date('now', '-3 years')
    ORDER BY c.data_assinatura DESC
    """


def _sqlite_fornecedores_query() -> str:
    return """
    SELECT
        c.ni_fornecedor AS fornecedor_cnpj,
        c.nome_fornecedor AS fornecedor_nome,
        COUNT(*) AS qtd_contratos,
        ROUND(SUM(COALESCE(c.valor_global, 0)), 2) AS valor_total_contratos,
        ROUND(AVG(COALESCE(c.valor_global, 0)), 2) AS ticket_medio_contrato,
        COUNT(DISTINCT c.orgao_cnpj) AS qtd_orgaos_distintos,
        NULL AS hhi_concentracao,
        GROUP_CONCAT(DISTINCT c.orgao_nome) AS orgaos_lista
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1
      AND c.ni_fornecedor IS NOT NULL AND c.ni_fornecedor != ''
    GROUP BY c.ni_fornecedor, c.nome_fornecedor
    ORDER BY valor_total_contratos DESC
    """


def _sqlite_expiring_query() -> str:
    return """
    SELECT
        c.numero_controle_pncp AS contrato_id,
        c.orgao_cnpj,
        c.orgao_nome,
        c.ni_fornecedor AS fornecedor_cnpj,
        c.nome_fornecedor AS fornecedor_nome,
        c.objeto_contrato,
        c.valor_global AS valor_contrato,
        c.data_assinatura AS data_inicio_contrato,
        c.data_fim_vigencia AS data_fim_contrato,
        CAST(julianday(c.data_fim_vigencia) - julianday('now') AS INTEGER) AS dias_ate_fim,
        c.uf,
        c.municipio,
        u.razao_social AS ente_razao_social
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1
      AND c.data_fim_vigencia IS NOT NULL
      AND c.data_fim_vigencia BETWEEN date('now', '+90 days') AND date('now', '+180 days')
    ORDER BY c.data_fim_vigencia, c.valor_global DESC
    """


def _pg_stats_query() -> str:
    return """
    SELECT 'Entes no raio 200km' AS metrica,
           CAST(COUNT(*) AS TEXT) AS valor
    FROM sc_public_entities WHERE raio_200km IS TRUE AND is_active IS TRUE
    UNION ALL
    SELECT 'Contratos no raio (total)',
           CAST(COUNT(*) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
    UNION ALL
    SELECT 'Fornecedores distintos',
           CAST(COUNT(DISTINCT ni_fornecedor) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
      AND ni_fornecedor IS NOT NULL AND ni_fornecedor != ''
    UNION ALL
    SELECT 'Valor total contratos (R$)',
           CAST(ROUND(SUM(valor_global)::numeric, 2) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
      AND valor_global IS NOT NULL
    UNION ALL
    SELECT 'Contratos com data_fim_vigencia',
           CAST(COUNT(*) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
      AND data_fim_vigencia IS NOT NULL
    UNION ALL
    SELECT 'Data range (assinatura)',
           COALESCE(MIN(data_assinatura)::text, 'N/A') || ' to '
           || COALESCE(MAX(data_assinatura)::text, 'N/A')
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
    """


def _sqlite_stats_query() -> str:
    return """
    SELECT 'Total contracts' AS metrica,
           CAST(COUNT(*) AS TEXT) AS valor
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1
    UNION ALL
    SELECT 'Unique suppliers',
           CAST(COUNT(DISTINCT ni_fornecedor) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1 AND ni_fornecedor IS NOT NULL
    UNION ALL
    SELECT 'Unique entities',
           CAST(COUNT(DISTINCT c.orgao_cnpj) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1
    UNION ALL
    SELECT 'Total value (R$)',
           CAST(ROUND(SUM(valor_global), 2) AS TEXT)
    FROM pncp_supplier_contracts c
    JOIN target_universe u ON c.orgao_cnpj LIKE u.cnpj8 || '%'
    WHERE c.is_active = 1 AND valor_global IS NOT NULL
    """


# Backward-compatible module-level alias for smoke tests.
# Uses SQLite-safe syntax (default). PG callers use _pg_stats_query() directly.
QUERY_STATS = _sqlite_stats_query()

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_table(rows: list[Any], description: Any) -> None:
    """Print rows as formatted table."""
    if not rows:
        print("(no results)")
        return

    cols = [d[0] for d in description]
    widths = [len(c) for c in cols]
    for row in rows:
        for i, val in enumerate(row):
            s = str(val) if val is not None else "NULL"
            widths[i] = max(widths[i], min(len(s), 50))

    header = " | ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "-+-".join("-" * w for w in widths)
    print(header)
    print(sep)

    for row in rows:
        vals = []
        for i, val in enumerate(row):
            s = str(val) if val is not None else "NULL"
            if len(s) > widths[i]:
                s = s[: widths[i] - 3] + "..."
            vals.append(s.ljust(widths[i]))
        print(" | ".join(vals))

    print(f"\n({len(rows)} rows)")


def _output(args: argparse.Namespace, data: Any) -> None:
    """Write output to file or stdout."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(json_str)
        if not getattr(args, "quiet", False):
            print(f"JSON → {args.output}")
    else:
        print(json_str)


def _write_json(args: argparse.Namespace, data: Any) -> None:
    """Write JSON to specified path."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    path = args.output or os.path.join(OUTPUT_DIR, "manifesto.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(json_str)
    print(f"JSON → {path}")


def _write_csv(args: argparse.Namespace, rows: list[dict[str, Any]]) -> None:
    """Write rows as CSV."""
    path = args.output_csv or args.output
    if not path:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not rows:
        with open(path, "w") as f:
            f.write("")
        print(f"CSV (empty) → {path}")
        return

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV → {path}")


# ---------------------------------------------------------------------------
# Commercial metrics commands (precos, desagio)
# ---------------------------------------------------------------------------


def cmd_precos(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Price history and value aggregation for a specific organ."""
    orgao = args.orgao
    periodo = args.periodo

    if backend != "postgresql":
        print("❌ precos command requires PostgreSQL (LOCAL_DATALAKE_DSN).", file=sys.stderr)
        return 1

    queries = {
        "contracts": f"""
            SELECT
                c.numero_controle_pncp AS contrato_id,
                c.valor_global AS valor_contrato,
                c.data_assinatura,
                c.data_fim_vigencia,
                c.orgao_nome,
                c.nr_contrato,
                c.objeto_contrato
            FROM pncp_supplier_contracts c
            WHERE c.orgao_cnpj LIKE '{orgao}%'
              AND c.is_active IS TRUE
              AND c.valor_global > 0
              AND c.data_assinatura >= (CURRENT_DATE - INTERVAL '{periodo} years')
            ORDER BY c.data_assinatura DESC
        """,
        "bids": f"""
            SELECT
                b.numero_controle_pncp,
                b.valor_total_estimado,
                b.modalidade_nome,
                b.data_abertura,
                b.objeto_compra
            FROM pncp_raw_bids b
            WHERE b.orgao_cnpj LIKE '{orgao}%'
              AND b.is_active IS TRUE
              AND b.valor_total_estimado > 0
              AND b.data_publicacao >= (CURRENT_DATE - INTERVAL '{periodo} years')
            ORDER BY b.data_abertura DESC
            LIMIT 50
        """,
        "aggregation": f"""
            SELECT
                'contract' AS tipo,
                'valor_global (PNCP)' AS coluna,
                'valor_contratado' AS semantica,
                COUNT(*) AS total,
                ROUND(SUM(c.valor_global)::numeric, 2) AS soma,
                ROUND(AVG(c.valor_global)::numeric, 2) AS media,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.valor_global)::numeric, 2) AS mediana,
                MIN(c.valor_global) AS minimo,
                MAX(c.valor_global) AS maximo
            FROM pncp_supplier_contracts c
            WHERE c.orgao_cnpj LIKE '{orgao}%'
              AND c.is_active IS TRUE AND c.valor_global > 0
              AND c.data_assinatura >= (CURRENT_DATE - INTERVAL '{periodo} years')
            UNION ALL
            SELECT
                'bid' AS tipo,
                'valor_total_estimado (PNCP)' AS coluna,
                'valor_estimado' AS semantica,
                COUNT(*),
                ROUND(SUM(b.valor_total_estimado)::numeric, 2),
                ROUND(AVG(b.valor_total_estimado)::numeric, 2),
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.valor_total_estimado)::numeric, 2),
                MIN(b.valor_total_estimado),
                MAX(b.valor_total_estimado)
            FROM pncp_raw_bids b
            WHERE b.orgao_cnpj LIKE '{orgao}%'
              AND b.is_active IS TRUE AND b.valor_total_estimado > 0
              AND b.data_publicacao >= (CURRENT_DATE - INTERVAL '{periodo} years')
        """,
    }

    cur = conn.cursor()

    # Entity info
    cur.execute(f"""
        SELECT razao_social, cnpj_8, municipio
        FROM sc_public_entities
        WHERE cnpj_8 = LEFT('{orgao}', 8) AND is_active = TRUE
        LIMIT 1
    """)
    entity = cur.fetchone()

    result: dict[str, Any] = {
        "orgao": orgao,
        "entity_name": entity[0] if entity else "N/A",
        "cnpj8": entity[1] if entity else "",
        "municipio": entity[2] if entity else "",
        "periodo_anos": periodo,
        "contracts": [],
        "bids": [],
        "aggregation": [],
    }

    # Contracts
    cur.execute(queries["contracts"])
    result["contracts"] = _query_to_dicts(cur, cur.fetchall())

    # Bids
    cur.execute(queries["bids"])
    result["bids"] = _query_to_dicts(cur, cur.fetchall())

    # Aggregation
    cur.execute(queries["aggregation"])
    result["aggregation"] = _query_to_dicts(cur, cur.fetchall())

    cur.close()

    if args.format == "json":
        _output(args, result)
    elif args.format == "csv":
        _write_csv(args, result.get("contracts", []))
    else:
        e = result
        print(f"\n  PRECOS — {e['entity_name']} ({e['cnpj8']})")
        print(f"  Orgao CNPJ: {e['orgao']} | Periodo: {e['periodo_anos']} anos")
        print()
        print("  VALUE SEMANTICS:")
        for agg in e.get("aggregation", []):
            print(f"    {agg['semantica']:25s} | {agg['coluna']}")
            print(f"      Total:      R$ {agg['soma']:>15,.2f}")
            print(f"      Media:      R$ {agg['media']:>15,.2f}")
            print(f"      Mediana:    R$ {agg['mediana']:>15,.2f}")
            print(f"      Min-Max:    R$ {agg['minimo']:>12,.2f} — R$ {agg['maximo']:>12,.2f}")
            print(f"      Qtd:        {agg['total']}")
            print()

        ct = e.get("contracts", [])
        if ct:
            print(f"  CONTRACTS (last {min(len(ct), 5)} of {len(ct)}):")
            for c in ct[:5]:
                dt = c.get("data_assinatura", "") or ""
                val = c.get("valor_contrato", 0) or 0
                print(f"    {str(dt)[:10]}  R$ {float(val):>12,.2f}  {c.get('objeto_contrato', '')[:60]}")
            if len(ct) > 5:
                print(f"    ... and {len(ct) - 5} more contracts")

        bids = e.get("bids", [])
        if bids:
            print(f"\n  BIDS (last {min(len(bids), 5)} of {len(bids)}):")
            for b in bids[:5]:
                dt = b.get("data_abertura", "") or ""
                val = b.get("valor_total_estimado", 0) or 0
                print(
                    f"    {str(dt)[:10]}  R$ {float(val):>12,.2f}  {b.get('modalidade_nome', '')[:20]}  {b.get('objeto_compra', '')[:50]}"
                )
            if len(bids) > 5:
                print(f"    ... and {len(bids) - 5} more bids")
        print()

    return 0


def cmd_desagio(conn: Any, args: argparse.Namespace, backend: str) -> int:
    """Average desagio by modality."""
    if backend != "postgresql":
        print("❌ desagio command requires PostgreSQL (LOCAL_DATALAKE_DSN).", file=sys.stderr)
        return 1

    modalidade_filter = ""
    if args.modalidade:
        modalidade_filter = f"AND b.modalidade_nome ILIKE '%{args.modalidade}%'"

    query = f"""
        WITH bid_contract_pairs AS (
            SELECT
                b.matched_entity_id,
                b.modalidade_nome,
                b.valor_total_estimado AS estimado,
                ROUND(AVG(c.valor_global)::numeric, 2) AS contratado_medio
            FROM pncp_raw_bids b
            JOIN sc_public_entities e ON e.id = b.matched_entity_id
            JOIN pncp_supplier_contracts c
              ON c.orgao_cnpj8 = e.cnpj_8
            WHERE b.matched_entity_id IS NOT NULL
              AND b.valor_total_estimado > 0
              AND c.valor_global > 0
              AND c.is_active IS TRUE
              AND b.is_active IS TRUE
              AND e.raio_200km IS TRUE
              AND e.is_active IS TRUE
              AND b.modalidade_nome IS NOT NULL
              {modalidade_filter}
            GROUP BY b.matched_entity_id, b.modalidade_nome, b.valor_total_estimado
        )
        SELECT
            modalidade_nome,
            COUNT(*) AS pares,
            ROUND(AVG(estimado)::numeric, 2) AS avg_estimado,
            ROUND(AVG(contratado_medio)::numeric, 2) AS avg_contratado,
            ROUND(
              (AVG(estimado) - AVG(contratado_medio))
              / NULLIF(AVG(estimado), 0) * 100
            , 2) AS desagio_pct,
            ROUND(
              PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                (estimado - contratado_medio) / NULLIF(estimado, 0) * 100
              )::numeric
            , 2) AS desagio_mediana_pct
        FROM bid_contract_pairs
        GROUP BY modalidade_nome
        ORDER BY desagio_pct DESC
    """

    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()

    if args.format == "json":
        result = _query_to_dicts(cur, rows)
        _output(args, result)
    elif args.format == "csv":
        result = _query_to_dicts(cur, rows)
        _write_csv(args, result)
    else:
        if not rows:
            print("(no data)")
        else:
            print("\n  DESAGIO MEDIO POR MODALIDADE (target universe 200km)")
            print(
                f"  {'Modalidade':<25s} {'Pares':>6s} {'Desagio%':>9s} {'Mediana%':>9s} {'Estimado':>15s} {'Contratado':>15s}"
            )
            print(f"  {'-' * 25} {'-' * 6} {'-' * 9} {'-' * 9} {'-' * 15} {'-' * 15}")
            for r in rows:
                modalidade, pares, est, cont, desagio, mediana = r[:6]
                est_str = f"R$ {float(est or 0):>10,.2f}" if est else "N/A"
                cont_str = f"R$ {float(cont or 0):>10,.2f}" if cont else "N/A"
                desagio_str = f"{float(desagio or 0):>7.2f}%" if desagio else "N/A"
                mediana_str = f"{float(mediana or 0):>7.2f}%" if mediana else "N/A"
                print(
                    f"  {str(modalidade)[:25]:<25s} {int(pares or 0):>6d} {desagio_str:>9s} {mediana_str:>9s} {est_str:>15s} {cont_str:>15s}"
                )
        print()
        print("  Nota: Desagio calculado como (estimado - contratado)/estimado.")
        print("  Compara valor_total_estimado do bid com valor_global medio dos contratos")
        print("  da mesma entidade. Nao e desagio item-a-item homologado.")
        print()

    cur.close()
    return 0


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contract Intelligence Truth v1 — analytical queries for target universe",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # historico
    p_hist = sub.add_parser("historico", help="Historical contracts (3-year window)")
    p_hist.add_argument("--limit", type=int, default=100)
    p_hist.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p_hist.add_argument("--output", default=None, help="Output file path")
    p_hist.add_argument("--output-csv", default=None, help="CSV output path")

    # fornecedores
    p_forn = sub.add_parser("fornecedores", help="Supplier/competitor analytics")
    p_forn.add_argument("--limit", type=int, default=50)
    p_forn.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p_forn.add_argument("--output", default=None, help="Output file path")
    p_forn.add_argument("--output-csv", default=None, help="CSV output path")

    # ativos
    p_ativ = sub.add_parser("ativos", help="Contracts ending in 90-180 days")
    p_ativ.add_argument("--limit", type=int, default=100)
    p_ativ.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p_ativ.add_argument("--output", default=None, help="Output file path")
    p_ativ.add_argument("--output-csv", default=None, help="CSV output path")

    # manifesto
    p_man = sub.add_parser("manifesto", help="Per-capability readiness manifest")
    p_man.add_argument("--format", choices=["table", "json"], default="table")
    p_man.add_argument("--output", default=None, help="JSON output path")
    p_man.add_argument("--output-csv", default=None, help="CSV gaps report path")

    # stats
    p_stats = sub.add_parser("stats", help="Summary statistics")
    p_stats.add_argument("--format", choices=["table", "json"], default="table")
    p_stats.add_argument("--output", default=None, help="Output file path")

    # seed
    _ = sub.add_parser("seed", help="Seed target universe into local DB")

    # precos — Price history for an entity
    p_precos = sub.add_parser("precos", help="Price history and value aggregation for an entity")
    p_precos.add_argument("--orgao", type=str, required=True, help="Organ CNPJ (8 or 14 digits)")
    p_precos.add_argument("--periodo", type=int, default=3, help="Analysis window in years (default: 3)")
    p_precos.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p_precos.add_argument("--output", default=None, help="Output file path")
    p_precos.add_argument("--output-csv", default=None, help="CSV output path")

    # desagio — Average desagio by modality
    p_desagio = sub.add_parser("desagio", help="Average desagio (discount) by modality")
    p_desagio.add_argument("--modalidade", type=str, default=None, help="Filter by modality name")
    p_desagio.add_argument("--format", choices=["table", "json", "csv"], default="table")
    p_desagio.add_argument("--output", default=None, help="Output file path")
    p_desagio.add_argument("--output-csv", default=None, help="CSV output path")

    # DB path (for SQLite)
    parser.add_argument("--db", default=None, help="SQLite database path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    conn, backend = _get_connection(args.db)
    _ensure_tables(conn, backend)

    if backend == "postgresql":
        _ensure_views_pg(conn.cursor())

    try:
        if args.command == "seed":
            count = seed_target_universe(conn, backend)
            print(f"Seeded {count} entities into target_universe.")
            return 0
        elif args.command == "historico":
            return cmd_historico(conn, args, backend)
        elif args.command == "fornecedores":
            return cmd_fornecedores(conn, args, backend)
        elif args.command == "ativos":
            return cmd_ativos(conn, args, backend)
        elif args.command == "manifesto":
            return cmd_manifesto(conn, args, backend)
        elif args.command == "stats":
            return cmd_stats(conn, args, backend)
        elif args.command == "precos":
            return cmd_precos(conn, args, backend)
        elif args.command == "desagio":
            return cmd_desagio(conn, args, backend)
        else:
            parser.print_help()
            return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
