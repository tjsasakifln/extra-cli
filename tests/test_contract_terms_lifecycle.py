"""#548 — terms are distinct; revoked contract is not a silent win."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.crawl.pncp_contract_terms import classify_term_type, map_pncp_term
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]


def test_term_types_are_distinct() -> None:
    assert classify_term_type("Termo Aditivo") == "ADITIVO"
    assert classify_term_type("Retificacao") == "RETIFICACAO"
    assert classify_term_type("Rescisao Unilateral") == "RESCISAO"
    assert classify_term_type("Revogacao") == "REVOGACAO"
    assert classify_term_type("Anulacao do contrato") == "ANULACAO"


def test_mapper_is_idempotent() -> None:
    payload = {
        "numeroControlePNCP": "term-548",
        "tipoTermoNome": "Termo Aditivo",
        "numeroTermo": "1",
        "dataAssinatura": "2026-04-01",
        "valorGlobal": 10000,
    }
    a = map_pncp_term(payload)
    b = map_pncp_term(payload)
    assert a["term_id"] == b["term_id"]
    assert a["tipo_termo"] == "ADITIVO"
    assert a["is_terminal"] is False
    assert map_pncp_term({**payload, "tipoTermoNome": "Anulacao"})["is_terminal"] is True


@pytest.mark.real_db
def test_revoked_contract_is_marked_on_lifecycle() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    contract = {
        "contrato_id": "term-548-revoked",
        "orgao_cnpj": "12345678000199",
        "objeto_contrato": "Execucao de obra",
        "data_publicacao": "2026-03-01",
        "source": "pncp",
        "source_id": "term-548-revoked",
        "supplier_id_type": "UNKNOWN",
    }
    term = map_pncp_term(
        {
            "numeroControlePNCP": "term-548-revoked",
            "tipoTermoNome": "Revogacao",
            "numeroTermo": "1",
            "dataAssinatura": "2026-04-10",
        }
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'contract_terms'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 112 not applied")
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([contract]),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([term], default=str),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([term], default=str),),
            )
            cur.execute(
                "SELECT lifecycle_event_last FROM pncp_supplier_contracts WHERE contrato_id = %s",
                ("term-548-revoked",),
            )
            assert cur.fetchone()["lifecycle_event_last"] == "REVOGACAO"
        conn.commit()
    finally:
        conn.close()
