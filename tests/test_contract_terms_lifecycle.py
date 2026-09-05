"""#548 — terms are distinct; revoked contract is not a silent win."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.crawl.ingestion._base.crawler import FetchResult
from scripts.crawl.pncp_contract_terms import (
    classify_term_type,
    contract_terms_url,
    expand_term_payloads,
    map_pncp_term,
    parse_pncp_controle_id,
    plan_term_ingest,
)
from scripts.ops.ingest_pncp_contract_terms import fetch_terms_for_contrato, run_ingest
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


def test_parse_controle_id_and_termos_url() -> None:
    parsed = parse_pncp_controle_id("12345678000199-2-000193/2026")
    assert parsed == ("12345678000199", 2026, 193)
    assert contract_terms_url(*parsed).endswith("/orgaos/12345678000199/contratos/2026/193/termos")


def test_expand_termos_envelope_is_idempotent() -> None:
    payload = {
        "numeroControlePNCP": "12345678000199-2-000193/2026",
        "tipoTermoNome": "Termo Aditivo",
        "numeroTermo": "1",
        "dataAssinatura": "2026-04-01",
        "valorGlobal": 10000,
    }
    expanded = expand_term_payloads([{"contrato_id": payload["numeroControlePNCP"], "termos": [payload]}])
    planned = plan_term_ingest(expanded + expanded)
    assert len(planned) == 1
    assert planned[0]["tipo_termo"] == "ADITIVO"


def test_from_pncp_fetch_path_calls_contratos_termos() -> None:
    contrato_id = "12345678000199-2-000193/2026"
    calls: list[tuple[str, int, int]] = []

    def fake_terms(cnpj: str, ano: int, seq: int) -> FetchResult:
        calls.append((cnpj, ano, seq))
        return FetchResult(
            records=[
                {
                    "tipoTermoNome": "Revogacao",
                    "numeroTermo": "1",
                    "dataAssinatura": "2026-04-10",
                }
            ],
            request_completed=True,
            http_status=200,
        )

    payloads = fetch_terms_for_contrato(contrato_id, fetch_terms=fake_terms)
    assert calls == [("12345678000199", 2026, 193)]
    planned = plan_term_ingest(payloads, contrato_id=contrato_id)
    assert planned[0]["tipo_termo"] == "REVOGACAO"
    result = run_ingest(
        conn=None,
        documents=[],
        contrato_ids=[contrato_id],
        after=None,
        limit=5,
        dry_run=True,
        fetch_terms=fake_terms,
    )
    assert result["planned"] == 1
    assert result["updated"] == 0
    assert result["cursor"] == contrato_id


def test_migration_keeps_terminal_lifecycle_sticky() -> None:
    sql = (ROOT / "db/migrations/112_contract_terms_lifecycle.sql").read_text(encoding="utf-8")
    assert "sticky" in sql.lower()
    assert "term.data_assinatura IS NOT NULL" in sql
    assert "NOT IN (" in sql
    assert "REVOGACAO" in sql


@pytest.mark.real_db
def test_undated_aditivo_does_not_clobber_revogacao() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    contrato_id = "term-548-sticky-revoked"
    contract = {
        "contrato_id": contrato_id,
        "orgao_cnpj": "12345678000199",
        "objeto_contrato": "Execucao de obra",
        "data_publicacao": "2026-03-01",
        "source": "pncp",
        "source_id": contrato_id,
        "supplier_id_type": "UNKNOWN",
    }
    revogacao = map_pncp_term(
        {
            "numeroControlePNCP": contrato_id,
            "tipoTermoNome": "Revogacao",
            "numeroTermo": "1",
            "dataAssinatura": "2026-04-10",
        }
    )
    undated_aditivo = map_pncp_term(
        {
            "numeroControlePNCP": contrato_id,
            "tipoTermoNome": "Termo Aditivo",
            "numeroTermo": "2",
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
                (json.dumps([revogacao], default=str),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([undated_aditivo], default=str),),
            )
            cur.execute(
                "SELECT lifecycle_event_last, lifecycle_event_at "
                "FROM pncp_supplier_contracts WHERE contrato_id = %s",
                (contrato_id,),
            )
            stored = cur.fetchone()
            assert stored["lifecycle_event_last"] == "REVOGACAO"
            assert str(stored["lifecycle_event_at"]) == "2026-04-10"
        conn.commit()
    finally:
        conn.close()


@pytest.mark.real_db
def test_newer_dated_term_replaces_terminal() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    contrato_id = "term-548-newer-dated"
    contract = {
        "contrato_id": contrato_id,
        "orgao_cnpj": "12345678000199",
        "objeto_contrato": "Execucao de obra",
        "data_publicacao": "2026-03-01",
        "source": "pncp",
        "source_id": contrato_id,
        "supplier_id_type": "UNKNOWN",
    }
    revogacao = map_pncp_term(
        {
            "numeroControlePNCP": contrato_id,
            "tipoTermoNome": "Revogacao",
            "numeroTermo": "1",
            "dataAssinatura": "2026-04-10",
        }
    )
    later = map_pncp_term(
        {
            "numeroControlePNCP": contrato_id,
            "tipoTermoNome": "Termo Aditivo",
            "numeroTermo": "2",
            "dataAssinatura": "2026-05-01",
        }
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([contract]),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([revogacao], default=str),),
            )
            cur.execute(
                "SELECT action FROM apply_contract_terms(%s::jsonb)",
                (json.dumps([later], default=str),),
            )
            cur.execute(
                "SELECT lifecycle_event_last FROM pncp_supplier_contracts WHERE contrato_id = %s",
                (contrato_id,),
            )
            assert cur.fetchone()["lifecycle_event_last"] == "ADITIVO"
        conn.commit()
    finally:
        conn.close()


@pytest.mark.real_db
def test_ingest_cli_applies_jsonl_via_apply_contract_terms() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    contrato_id = "term-548-cli-ingest"
    contract = {
        "contrato_id": contrato_id,
        "orgao_cnpj": "12345678000199",
        "objeto_contrato": "Execucao de obra",
        "data_publicacao": "2026-03-01",
        "source": "pncp",
        "source_id": contrato_id,
        "supplier_id_type": "UNKNOWN",
    }
    term_payload = {
        "numeroControlePNCP": contrato_id,
        "tipoTermoNome": "Anulacao do contrato",
        "numeroTermo": "1",
        "dataAssinatura": "2026-04-20",
    }
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([contract]),),
            )
        result = run_ingest(
            conn,
            documents=[term_payload],
            contrato_ids=[],
            after=None,
            limit=None,
            dry_run=False,
        )
        assert result["updated"] >= 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lifecycle_event_last FROM pncp_supplier_contracts WHERE contrato_id = %s",
                (contrato_id,),
            )
            assert cur.fetchone()["lifecycle_event_last"] == "ANULACAO"
    finally:
        conn.close()
