"""#550 — commercial_read_v1 column contract and independent clocks."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "docs/contracts/commercial-read/v1/commercial_read_v1.json").read_text(encoding="utf-8")
)
SQL = (ROOT / "db/migrations/115_commercial_read_v1.sql").read_text(encoding="utf-8")


def test_column_contract_is_stable() -> None:
    for col in CONTRACT["columns"]:
        assert col in SQL
    assert "v_recent_engineering_wins" in SQL
    assert "confenge_commercial_read_v1" in SQL
    assert "contract_engineering_class" in SQL
    assert "ILIKE" not in SQL


def test_clocks_are_independent_in_sql() -> None:
    assert "DATA_FRESHNESS" in SQL
    assert "EVENT_RECENCY" in SQL
    assert "COMMERCIAL_ACTIONABILITY" in SQL
    assert "NOT_ACTIONABLE" in SQL
    assert "REVOGACAO" in SQL
    assert "c.first_seen_at::date - c.data_publicacao_fonte" in SQL
    assert "CURRENT_DATE - coalesce(c.data_assinatura" in SQL


def test_role_is_select_only_without_credentials() -> None:
    assert "NOLOGIN" in SQL
    assert "GRANT SELECT" in SQL
    assert "password" not in SQL.lower()
    assert "GRANT INSERT" not in SQL
    assert "GRANT UPDATE" not in SQL


@pytest.mark.real_db
def test_revoked_contract_is_not_actionable_on_wins_view() -> None:
    """NOT_ACTIONABLE must come from persisted lifecycle, not from grepping SQL."""
    import psycopg2
    import psycopg2.extras

    from scripts.crawl.pncp_contract_terms import map_pncp_term
    from scripts.testing.real_db_guard import canonical_dsn

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    contrato_id = "term-550-not-actionable"
    contract = {
        "contrato_id": contrato_id,
        "orgao_cnpj": "12345678000199",
        "orgao_nome": "Prefeitura de Teste",
        "objeto_contrato": "Execucao de obra de pavimentacao urbana",
        "data_publicacao": "2026-03-01",
        "data_assinatura": "2026-03-05",
        "valor_total": 250000,
        "source": "pncp",
        "source_id": contrato_id,
        "supplier_id_type": "UNKNOWN",
        "fornecedor_cnpj": "11222333000181",
        "fornecedor_nome": "Construtora Revogada Ltda",
        "uf": "SC",
        "municipio": "Florianopolis",
    }
    engineering = {
        "contrato_id": contrato_id,
        "engineering_class": "OBRA_EXECUCAO",
        "confidence": 0.91,
        "categories": ["obra"],
        "evidence": ["objeto_obra_execucao"],
        "rule_version": "engineering-class-v1",
    }
    term = map_pncp_term(
        {
            "numeroControlePNCP": contrato_id,
            "tipoTermoNome": "Revogacao",
            "numeroTermo": "1",
            "dataAssinatura": "2026-04-10",
        }
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.views WHERE table_name = 'v_recent_engineering_wins'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 115 not applied")
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([contract]),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_engineering_class(%s::jsonb)",
                (json.dumps([engineering]),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([term], default=str),),
            )
            cur.execute(
                """
                UPDATE pncp_supplier_contracts
                SET quality_state = COALESCE(NULLIF(quality_state, 'QUARANTINED'), 'VALID'),
                    data_publicacao_fonte = COALESCE(data_publicacao_fonte, %s::date),
                    data_assinatura = COALESCE(data_assinatura, %s::date)
                WHERE contrato_id = %s
                """,
                ("2026-03-01", "2026-03-05", contrato_id),
            )
            cur.execute(
                "SELECT lifecycle_event_last FROM pncp_supplier_contracts WHERE contrato_id = %s",
                (contrato_id,),
            )
            persisted = cur.fetchone()
            assert persisted is not None
            assert persisted["lifecycle_event_last"] == "REVOGACAO"
            cur.execute(
                """
                SELECT commercial_actionability, lifecycle_status, data_freshness, commercial_age_days
                FROM v_recent_engineering_wins
                WHERE contract_id = %s
                """,
                (contrato_id,),
            )
            row = cur.fetchone()
            assert row is not None, "revoked engineering contract must appear on the wins view"
            assert row["lifecycle_status"] == "REVOGACAO"
            assert row["commercial_actionability"] == "NOT_ACTIONABLE"
        conn.commit()
    finally:
        conn.close()
