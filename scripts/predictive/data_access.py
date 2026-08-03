"""Load contract rows from PostgreSQL for dataset building."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any


def get_dsn(explicit: str | None = None) -> str:
    return (
        explicit
        or os.environ.get("DATABASE_URL")
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or "postgresql://test:test@127.0.0.1:5433/extra_test"
    )


def connect(dsn: str | None = None):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(get_dsn(dsn))
    conn.cursor_factory = RealDictCursor
    return conn


def fetch_aec_contracts(
    dsn: str | None = None,
    *,
    limit: int | None = None,
    uf: str | None = None,
    min_year: int = 2019,
    max_year: int = 2030,
) -> list[dict[str, Any]]:
    """Fetch contracts likely AEC from pncp_supplier_contracts."""
    sql = """
    SELECT
        contrato_id,
        orgao_cnpj,
        orgao_nome,
        fornecedor_cnpj,
        fornecedor_nome,
        objeto_contrato,
        valor_total,
        data_inicio,
        data_fim,
        data_publicacao,
        data_assinatura,
        data_publicacao_fonte,
        source_event_date,
        uf,
        municipio,
        source
    FROM pncp_supplier_contracts
    WHERE is_active IS DISTINCT FROM FALSE
      AND (
        objeto_contrato ILIKE '%%obra%%'
        OR objeto_contrato ILIKE '%%constru%%'
        OR objeto_contrato ILIKE '%%paviment%%'
        OR objeto_contrato ILIKE '%%edific%%'
        OR objeto_contrato ILIKE '%%reforma%%'
        OR objeto_contrato ILIKE '%%drenagem%%'
        OR objeto_contrato ILIKE '%%saneamento%%'
        OR objeto_contrato ILIKE '%%terraplen%%'
        OR objeto_contrato ILIKE '%%infraestrutura%%'
      )
      AND COALESCE(data_assinatura, data_publicacao, data_inicio, source_event_date)
          >= %(min_dt)s
      AND COALESCE(data_assinatura, data_publicacao, data_inicio, source_event_date)
          < %(max_dt)s
    """
    params: dict[str, Any] = {
        "min_dt": datetime(min_year, 1, 1),
        "max_dt": datetime(max_year + 1, 1, 1),
    }
    if uf:
        sql += " AND uf = %(uf)s"
        params["uf"] = uf
    sql += " ORDER BY COALESCE(data_assinatura, data_publicacao, data_inicio) ASC"
    if limit:
        sql += " LIMIT %(limit)s"
        params["limit"] = int(limit)

    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def corpus_stats(dsn: str | None = None) -> dict[str, Any]:
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM pncp_supplier_contracts")
            n_contracts = cur.fetchone()["n"]
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM pncp_supplier_contracts
                WHERE objeto_contrato ILIKE '%%obra%%'
                   OR objeto_contrato ILIKE '%%constru%%'
                   OR objeto_contrato ILIKE '%%paviment%%'
                """
            )
            n_aec_like = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM opportunity_intel")
            n_opp = cur.fetchone()["n"]
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM opportunity_intel
                WHERE valor_estimado IS NOT NULL AND valor_estimado > 0
                  AND valor_homologado IS NOT NULL AND valor_homologado > 0
                """
            )
            n_disc_pairs = cur.fetchone()["n"]
            # participant lists
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM information_schema.tables
                WHERE table_schema='public' AND table_name IN (
                  'process_participants', 'bid_participants', 'proposta_participantes'
                )
                """
            )
            n_part_tables = cur.fetchone()["n"]
        return {
            "n_contracts": n_contracts,
            "n_aec_like_objects": n_aec_like,
            "n_opportunity_intel": n_opp,
            "n_discount_pairs_opp": n_disc_pairs,
            "participant_tables_present": n_part_tables > 0,
            "p2b_supported": n_part_tables > 0,
        }
    finally:
        conn.close()


def fetch_discount_pairs_from_opportunities(
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    """Attempt P3 pairs from opportunity_intel when both values exist."""
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id::text AS procurement_id,
                    orgao_cnpj AS entity_id,
                    valor_estimado AS estimated_value,
                    valor_homologado AS outcome_value,
                    valor_semantica,
                    data_homologacao,
                    data_publicacao,
                    data_encerramento,
                    modalidade
                FROM opportunity_intel
                WHERE valor_estimado IS NOT NULL AND valor_estimado > 0
                  AND valor_homologado IS NOT NULL AND valor_homologado > 0
                """
            )
            rows = cur.fetchall()
        pairs: list[dict[str, Any]] = []
        for r in rows:
            event = r.get("data_homologacao") or r.get("data_encerramento") or r.get("data_publicacao")
            if event is None:
                continue
            # Only accept if semantics are clear; valor_homologado is allowed
            pairs.append(
                {
                    "procurement_id": r["procurement_id"],
                    "entity_id": r["entity_id"],
                    "estimated_value": float(r["estimated_value"]),
                    "outcome_value": float(r["outcome_value"]),
                    "estimated_value_semantics": "valor_estimado",
                    "outcome_value_semantics": "valor_homologado",
                    "same_process": True,
                    "event_at": event,
                    "hist_discounts": [],
                }
            )
        return pairs
    finally:
        conn.close()
