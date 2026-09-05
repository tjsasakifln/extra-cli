"""#545 — PNCP resultados before signature; no invented contrato_id."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.crawl.pncp_procurement_results import (
    HOMOLOGATED,
    RESULT_PUBLISHED,
    map_pncp_item_result,
    plan_result_ingest,
)
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]

PAYLOAD = {
    "numeroControlePNCPCompra": "12345678000199-1-000010/2026",
    "numeroItem": 1,
    "niFornecedor": "11222333000181",
    "tipoPessoa": "PJ",
    "nomeRazaoSocialFornecedor": "Construtora Vencedora Ltda",
    "valorNegociado": 350000.0,
    "situacao": "Homologado",
    "dataResultado": "2026-02-10",
    "dataPublicacaoPncp": "2026-02-11",
}


def test_mapper_preserves_winner_and_never_sets_contrato_id() -> None:
    row = map_pncp_item_result(PAYLOAD)
    assert row is not None
    assert row["contrato_id"] is None
    assert row["parent_procurement_id"] == "12345678000199-1-000010/2026"
    assert row["event_type"] == HOMOLOGATED
    assert row["winner_nome"] == "Construtora Vencedora Ltda"
    assert row["valor_homologado"] == 350000.0
    assert row["situacao"] == "Homologado"
    assert row["event_at"] == "2026-02-10"
    assert row["source_published_at"] == "2026-02-11"


def test_reobservation_is_idempotent_on_result_id() -> None:
    a = map_pncp_item_result(PAYLOAD)
    b = map_pncp_item_result(PAYLOAD)
    assert a["result_id"] == b["result_id"]
    planned = plan_result_ingest([PAYLOAD, PAYLOAD])
    assert len(planned) == 1


def test_result_published_without_homologacao() -> None:
    row = map_pncp_item_result({**PAYLOAD, "situacao": "Adjudicado", "homologado": False})
    assert row["event_type"] == RESULT_PUBLISHED


def test_migration_forbids_invented_contract_semantics() -> None:
    sql = (ROOT / "db/migrations/111_pncp_procurement_results.sql").read_text(encoding="utf-8")
    assert "Never invented" in sql
    assert "RESULT_PUBLISHED" in sql
    assert "HOMOLOGATED" in sql
    assert "parent_procurement_id" in sql


@pytest.mark.real_db
def test_ingest_idempotent_and_link_only_when_contract_exists() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    row = map_pncp_item_result(PAYLOAD)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'pncp_procurement_results'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 111 not applied")
            cur.execute(
                "SELECT action FROM apply_pncp_procurement_results(%s::jsonb)",
                (json.dumps([row], default=str),),
            )
            first = [r["action"] for r in cur.fetchall()]
            cur.execute(
                "SELECT action FROM apply_pncp_procurement_results(%s::jsonb)",
                (json.dumps([row], default=str),),
            )
            second = [r["action"] for r in cur.fetchall()]
            assert first == ["inserted"]
            assert second == ["updated"]
            cur.execute(
                "SELECT contrato_id, winner_cnpj, valor_homologado, event_type "
                "FROM pncp_procurement_results WHERE result_id = %s",
                (row["result_id"],),
            )
            stored = cur.fetchone()
            assert stored["contrato_id"] is None
            assert stored["event_type"] == HOMOLOGATED
            assert float(stored["valor_homologado"]) == 350000.0
            fake = dict(row)
            fake["contrato_id"] = "does-not-exist"
            cur.execute(
                "SELECT 1 FROM apply_pncp_procurement_results(%s::jsonb)",
                (json.dumps([fake], default=str),),
            )
            cur.execute(
                "SELECT contrato_id FROM pncp_procurement_results WHERE result_id = %s",
                (row["result_id"],),
            )
            assert cur.fetchone()["contrato_id"] is None
        conn.commit()
    finally:
        conn.close()
