"""#552 — absurd dates must not win MAX; status_observed_at is real observation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts_truth import (
    QUARANTINED,
    annotate_transformed_contract,
    classify_contract_quality,
)
from scripts.crawl.date_semantics import null_implausible_contract_dates
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/109_contract_date_hygiene.sql"


def test_year_8406_is_nulled_before_max_contamination() -> None:
    record = {
        "data_assinatura": "8406-05-16",
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
        "source_event_date": "8406-05-16",
    }
    quality = classify_contract_quality(
        data_assinatura=record["data_assinatura"],
        data_inicio=record["data_inicio"],
        data_fim=record["data_fim"],
        valor=1000,
    )
    assert quality.state == QUARANTINED
    null_implausible_contract_dates(record)
    assert record["data_assinatura"] is None
    assert record["source_event_date"] is None
    assert record["data_inicio"] == "2026-01-01"


def test_inferred_status_does_not_get_fabricated_observed_at() -> None:
    record = annotate_transformed_contract(
        {
            "contrato_id": "hygiene-inferred",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "data_assinatura": "2026-01-01",
            "valor_total": 1000,
        },
        raw={"objetoContrato": "obra"},
    )
    assert not record.get("status_raw")
    # Python annotate must not invent now(); persist trigger fills only official status.
    assert record.get("status_observed_at") is None


def test_official_status_does_not_invent_now() -> None:
    record = annotate_transformed_contract(
        {
            "contrato_id": "hygiene-official",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "valor_total": 1000,
        },
        raw={"situacaoContrato": "vigente"},
    )
    assert record["status_raw"]
    assert "status_observed_at" not in record or record["status_observed_at"] is None


def test_migration_quarantines_and_declares_non_operational_surfaces() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "fn_quarantine_implausible_contract_dates" in sql
    assert "quality_state := 'QUARANTINED'" in sql
    assert "NEW.status_observed_at := NULL" in sql
    assert "Never a fabricated now()" in sql
    assert "v_contract_dates_sane" in sql
    assert "canonical_surface_operational_status" in sql
    for name in (
        "canonical_public_events_v1",
        "canonical_public_observations",
        "canonical_event_observation_links",
        "canonical_suppliers",
        "observed_supplier_relations",
        "official_acts",
    ):
        assert name in sql
    assert "NON_OPERATIONAL" in sql
    assert "#545" in sql


@pytest.mark.real_db
def test_absurd_date_does_not_win_max_and_status_observed_at_stays_null() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_proc WHERE proname = 'fn_quarantine_implausible_contract_dates'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 109 not applied")
            record = {
                "contrato_id": "hygiene-8406",
                "orgao_cnpj": "12345678000199",
                "orgao_nome": "Orgao",
                "fornecedor_nome": "Fornecedor",
                "supplier_id_type": "UNKNOWN",
                "objeto_contrato": "contrato com data absurda",
                "valor_total": 1000,
                "data_assinatura": "8406-05-16",
                "data_inicio": "2026-01-01",
                "data_fim": "2026-12-31",
                "data_publicacao": "2026-01-02",
                "source": "pncp",
                "source_id": "hygiene-8406",
            }
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([record]),),
            )
            cur.execute(
                """
                SELECT data_assinatura, quality_state, status_observed_at
                FROM pncp_supplier_contracts
                WHERE contrato_id = 'hygiene-8406'
                """
            )
            row = cur.fetchone()
            assert row["data_assinatura"] is None
            assert row["quality_state"] == "QUARANTINED"
            assert row["status_observed_at"] is None
            cur.execute(
                "SELECT MAX(data_assinatura) AS mx FROM v_contract_dates_sane"
            )
            mx = cur.fetchone()["mx"]
            assert mx is None or mx.year < 8000
            cur.execute(
                """
                SELECT object_name, decision FROM canonical_surface_operational_status
                WHERE object_name = 'canonical_public_events_v1'
                """
            )
            status = cur.fetchone()
            assert status["decision"] == "NON_OPERATIONAL"
        conn.commit()
    finally:
        conn.close()
