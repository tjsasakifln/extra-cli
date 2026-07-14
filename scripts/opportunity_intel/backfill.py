#!/usr/bin/env python3
"""Backfill opportunity_intel from pncp_raw_bids.

Reads pncp_raw_bids for potentially open opportunities (within 200 km
of Florianopolis or SC state), computes canonical status using enhanced
heuristics, and upserts into opportunity_intel.

Usage:
    python scripts/opportunity_intel/backfill.py                     # Full backfill
    python scripts/opportunity_intel/backfill.py --dry-run           # Count only
    python scripts/opportunity_intel/backfill.py --days 30           # Last 30 days
    python scripts/opportunity_intel/backfill.py --limit 1000        # Limit rows
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

import psycopg2
import psycopg2.extras

_logger = logging.getLogger(__name__)

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres@127.0.0.1:5433/pncp_datalake",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_conn(dsn: str | None = None):
    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    conn.autocommit = True
    return conn


def _iso(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


# ---------------------------------------------------------------------------
# Status inference SQL generator
# ---------------------------------------------------------------------------


def _build_inferred_status_sql():
    """Build SQL for inferring canonical status from pncp_raw_bids columns."""
    from scripts.opportunity_intel.status import infer_bid_status_sql

    return infer_bid_status_sql()


# ---------------------------------------------------------------------------
# Ranking SQL generator
# ---------------------------------------------------------------------------


def _ranking_score_sql(prefix: str = "i.") -> str:
    """Compute a simplified ranking score for backfilled records."""
    s = prefix  # column prefix (e.g. "i." for CTE references)
    return f"""
    CASE
        WHEN {s}status_canonico = 'open' THEN 30 ELSE 0
    END
    + CASE
        WHEN {s}data_encerramento IS NOT NULL AND {s}data_encerramento >= CURRENT_DATE THEN 15
        WHEN {s}data_encerramento IS NULL AND {s}data_publicacao >= CURRENT_DATE - INTERVAL '30 days' THEN 10
        ELSE 0
    END
    + CASE
        WHEN {s}modalidade IS NOT NULL
             AND LOWER(TRIM({s}modalidade)) IN ('concorrência', 'concorrencia', 'pregão eletrônico', 'pregao eletronico', 'pregão', 'pregao')
        THEN 10
        ELSE 0
    END
    + CASE
        WHEN {s}valor_estimado IS NOT NULL AND {s}valor_estimado > 0 THEN 10
        ELSE 0
    END
    + CASE
        WHEN LOWER(TRIM(COALESCE({s}objeto, ''))) != '' THEN 5
        ELSE 0
    END
    """


def _ranking_tier_sql(prefix: str = "i.") -> str:
    """Map score to ranking tier."""
    return """
    CASE
        WHEN ranking_score >= 50 THEN 'GO'
        WHEN ranking_score >= 25 THEN 'REVIEW'
        ELSE 'NO_GO'
    END
    """


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


def backfill(
    dsn: str | None = None,
    dry_run: bool = False,
    days: int | None = None,
    limit: int | None = None,
) -> dict:
    """Backfill opportunity_intel from pncp_raw_bids.

    Args:
        dsn: Database connection string.
        dry_run: If True, only count records without inserting.
        days: Only process bids published in the last N days.
        limit: Maximum number of records to process.

    Returns:
        Dict with stats.
    """
    dsn = dsn or DEFAULT_DSN
    conn = _get_conn(dsn)
    cur = conn.cursor()

    inferred = _build_inferred_status_sql()

    # Build WHERE clause
    conditions = ["pb.is_active = TRUE"]
    params: list = []

    # Only SC and nearby states (200km radius focus)
    conditions.append("(pb.uf = 'SC' OR pb.matched_entity_id IS NOT NULL)")

    if days:
        conditions.append("pb.data_publicacao >= CURRENT_DATE - INTERVAL %s")
        params.append(f"{days} days")

    # Only potentially open bids
    conditions.append(
        f"""(pb.data_encerramento IS NULL
              OR pb.data_encerramento >= CURRENT_DATE
              OR {inferred} IN ('open', 'upcoming'))"""
    )

    where = " AND ".join(conditions)
    ranking_score = _ranking_score_sql()
    ranking_tier = _ranking_tier_sql()

    # Count first
    count_sql = f"SELECT COUNT(*) FROM pncp_raw_bids pb WHERE {where}"
    _logger.info("Counting backfill candidates...")
    print(f"  SQL: {count_sql[:120]}...")
    cur.execute(count_sql, params)
    total = cur.fetchone()[0]
    print(f"  Total candidates: {total}")

    if dry_run:
        cur.close()
        conn.close()
        return {"dry_run": True, "candidates": total, "inserted": 0, "updated": 0}

    # Backfill query: select raw bids, compute status and ranking
    select_sql = f"""
    WITH inferred AS (
        SELECT
            pb.numero_controle_pncp AS source_id,
            pb.orgao_cnpj,
            pb.orgao_razao_social AS orgao_nome,
            pb.uf,
            pb.municipio,
            pb.codigo_municipio_ibge AS codigo_ibge,
            pb.objeto_compra AS objeto,
            pb.modalidade_nome AS modalidade,
            pb.valor_total_estimado AS valor_estimado,
            pb.data_publicacao,
            pb.data_abertura,
            pb.data_encerramento,
            COALESCE(NULLIF(TRIM(pb.situacao_compra), ''), NULL) AS status_fonte,
            pb.link_sistema_origem AS link_edital,
            pb.link_pncp,
            pb.matched_entity_id,
            {inferred} AS status_canonico
        FROM pncp_raw_bids pb
        WHERE {where}
    ),
    scored AS (
        SELECT
            i.*,
            {ranking_score} AS ranking_score
        FROM inferred i
    )
    SELECT
        s.source_id,
        s.orgao_cnpj,
        s.orgao_nome,
        s.uf,
        s.municipio,
        s.codigo_ibge,
        s.objeto,
        s.modalidade,
        s.valor_estimado,
        s.data_publicacao,
        s.data_abertura,
        s.data_encerramento,
        s.status_fonte,
        s.link_edital,
        s.link_pncp,
        s.matched_entity_id,
        s.status_canonico,
        s.ranking_score,
        CASE
            WHEN s.ranking_score >= 50 THEN 'GO'
            WHEN s.ranking_score >= 25 THEN 'REVIEW'
            ELSE 'NO_GO'
        END AS ranking
    FROM scored s
    ORDER BY s.data_publicacao DESC NULLS LAST
    """

    if limit:
        select_sql += f" LIMIT {limit}"

    _logger.info("Fetching bids for backfill...")
    cur.execute(select_sql, params)

    batch = []
    count = 0
    errors = 0

    for row in cur.fetchall():
        try:
            source_id = str(row[0] or "")
            orgao_cnpj = str(row[1] or "") if row[1] else None
            orgao_nome = str(row[2] or "") if row[2] else None
            uf = str(row[3] or "SC")
            municipio = str(row[4] or "") if row[4] else None
            codigo_ibge = str(row[5] or "") if row[5] else None
            objeto = str(row[6] or "")
            modalidade = str(row[7] or "") if row[7] else None
            valor_estimado = row[8]
            data_publicacao = row[9]
            data_abertura = row[10]
            data_encerramento = row[11]
            status_fonte = str(row[12]) if row[12] else None
            link_edital = str(row[13] or "") if row[13] else None
            status_canonico = str(row[16])
            ranking_score = str(row[17])
            ranking_tier = str(row[18])

            record = {
                "source": "pncp",
                "source_id": source_id,
                "numero_controle_pncp": source_id if source_id else None,
                "orgao_cnpj": orgao_cnpj,
                "orgao_nome": orgao_nome,
                "ente_federativo": _infer_esfera(uf, orgao_cnpj),
                "uf": uf,
                "municipio": municipio,
                "codigo_ibge": codigo_ibge,
                "modalidade": modalidade,
                "objeto": objeto,
                "valor_estimado": str(valor_estimado) if valor_estimado is not None else None,
                "data_publicacao": _iso(data_publicacao),
                "data_abertura": _iso(data_abertura),
                "data_encerramento": _iso(data_encerramento),
                "status_fonte": status_fonte,
                "status_canonico": status_canonico,
                "status_motivo": "backfill: inferred from pncp_raw_bids",
                "status_data": _iso(datetime.now(UTC)),
                "link_edital": link_edital,
                "ranking": ranking_tier,
                "ranking_score": ranking_score,
                "content_hash": source_id,
                "proveniencia": {"source": "pncp", "method": "backfill"},
                "crawl_batch_id": "backfill",
            }
            batch.append(record)
            count += 1

            if len(batch) >= 500:
                _bulk_upsert(conn, batch)
                _logger.info(f"  Inserted/Updated {count} records...")
                batch = []

        except Exception as e:
            _logger.warning("Error processing row: %s", e)
            errors += 1

    # Final batch
    inserted = 0
    updated = 0
    if batch:
        i, u = _bulk_upsert(conn, batch)
        inserted += i
        updated += u

    cur.close()
    conn.close()

    return {
        "candidates": total,
        "processed": count,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
    }


def _bulk_upsert(conn, batch: list[dict]) -> tuple[int, int]:
    """Execute upsert_opportunity_intel RPC."""
    inserted = 0
    updated = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM upsert_opportunity_intel(%s::jsonb)",
            (json.dumps(batch, default=str),),
        )
        for row in cur.fetchall():
            action = row[0]
            if action == "insert":
                inserted += 1
            elif action == "update":
                updated += 1
    return inserted, updated


def _infer_esfera(uf: str, cnpj: str | None) -> str:
    """Infer governmental sphere from UF and CNPJ."""
    if not uf:
        return "desconhecida"
    if uf.upper() == "DF":
        return "distrital"
    if cnpj and len(cnpj) >= 8:
        federal_prefixes = ("00", "01", "02", "03", "04")
        if cnpj[:2] in federal_prefixes:
            return "federal"
    return "municipal"


# ---------------------------------------------------------------------------
# Entity coverage update
# ---------------------------------------------------------------------------


def update_entity_coverage(dsn: str | None = None) -> dict:
    """Update entity_coverage for open tenders.

    Counts entities that have at least one open tender (inferred status).
    """
    from scripts.opportunity_intel.status import infer_bid_status_sql

    dsn = dsn or DEFAULT_DSN
    conn = _get_conn(dsn)
    cur = conn.cursor()

    inferred = infer_bid_status_sql()

    _logger.info("Updating entity_coverage for open tenders...")

    cur.execute(
        f"""UPDATE entity_coverage ec
            SET is_covered = TRUE,
                total_bids = subq.open_count
            FROM (
                SELECT tue.db_entity_id AS id, COUNT(*) as open_count
                FROM target_universe_entities tue
                JOIN pncp_raw_bids pb ON tue.db_entity_id = pb.matched_entity_id
                WHERE tue.universe_run_id = (SELECT MAX(id) FROM target_universe_runs)
                  AND tue.radius_decision = 'included'
                  AND pb.is_active = TRUE
                  AND ({inferred}) IN ('open', 'upcoming')
                GROUP BY tue.db_entity_id
            ) subq
            WHERE ec.entity_id = subq.id AND ec.source = 'pncp'
            RETURNING ec.entity_id, ec.total_bids"""
    )

    updated = cur.rowcount
    _logger.info(f"Updated entity_coverage for {updated} entities")

    rows = cur.fetchall()
    total_bids = sum(row[1] or 0 for row in rows)

    cur.close()
    conn.close()

    return {"entities_updated": updated, "total_open_bids": total_bids}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill opportunity_intel from pncp_raw_bids")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true", help="Count only, no insert")
    parser.add_argument("--days", type=int, default=None, help="Only last N days")
    parser.add_argument("--limit", type=int, default=None, help="Max records")
    parser.add_argument(
        "--skip-update-coverage", action="store_true", help="Skip entity_coverage update after backfill"
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    print("\n=== BACKFILL: pncp_raw_bids -> opportunity_intel ===\n")

    result = backfill(
        dsn=args.dsn,
        dry_run=args.dry_run,
        days=args.days,
        limit=args.limit,
    )

    print("\nResult:")
    for k, v in result.items():
        print(f"  {k}: {v}")

    if not args.dry_run and not args.skip_update_coverage:
        print("\n=== Updating entity_coverage ===\n")
        cov_result = update_entity_coverage(dsn=args.dsn)
        print(f"Entity coverage updated: {cov_result['entities_updated']} entities")
        print(f"Total open bids: {cov_result['total_open_bids']}")

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
