"""Regression coverage for migration 108 contract refresh semantics."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "db/migrations/108_contract_upsert_mutable_fields.sql"
TRIGGER_MIGRATION = (
    Path(__file__).resolve().parents[1] / "db/migrations/110_disable_contract_versioning_trigger.sql"
)


def test_migration_refreshes_all_material_mutable_fields() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    expected_assignments = {
        "orgao_cnpj",
        "orgao_nome",
        "fornecedor_nome",
        "objeto_contrato",
        "valor_total",
        "data_inicio",
        "data_fim",
        "data_publicacao",
        "uf",
        "municipio",
        "source",
        "source_id",
        "data_assinatura",
        "data_publicacao_fonte",
        "source_event_date",
        "source_date_semantics",
    }
    for field in expected_assignments:
        assert f"{field} = CASE WHEN public.fn_contract_observation_not_older(" in sql

    assert "data_atualizacao_fonte = CASE" in sql
    assert "source_updated_at = CASE" in sql
    assert "last_seen_at = CASE" in sql


def test_migration_is_partial_safe_and_freshness_monotonic() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "COALESCE(EXCLUDED.objeto_contrato, target.objeto_contrato)" in sql
    assert "COALESCE(EXCLUDED.valor_total, target.valor_total)" in sql
    assert "EXCLUDED.supplier_identifier IS NOT NULL" in sql
    assert "EXCLUDED.data_atualizacao_fonte > target.data_atualizacao_fonte" in sql
    assert "EXCLUDED.source_updated_at > target.source_updated_at" in sql
    assert "EXCLUDED.query_window_end >= target.query_window_end" in sql
    assert "Missing incoming freshness cannot replace" in sql


def test_migration_keeps_identity_derivation_server_side() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "digest(" in sql
    assert "fn_contract_valid_cnpj" in sql
    assert "fn_contract_valid_cpf" in sql
    assert "rec->>'supplier_identifier_hash' AS supplier_identifier_hash" not in sql
    assert "rec->>'supplier_identifier_export'" not in sql


def test_contract_version_history_trigger_is_explicitly_disabled() -> None:
    sql = TRIGGER_MIGRATION.read_text(encoding="utf-8")

    assert "DISABLE TRIGGER trg_contract_versioning" in sql
    assert "DROP TRIGGER" not in sql


@pytest.mark.real_db
def test_rpc_refreshes_newer_fields_without_regressing_or_erasing() -> None:
    import psycopg2

    from scripts.contracts_truth import stamp_contract_truth_labels

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    assert dsn, "LOCAL_DATALAKE_DSN or DATABASE_URL is required for real_db"
    conn = psycopg2.connect(dsn)
    contract_id = "test-108-mutable-refresh"
    valid_cnpj = "11222333000181"
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT tgenabled
                FROM pg_trigger
                WHERE tgrelid = 'public.pncp_supplier_contracts'::regclass
                  AND tgname = 'trg_contract_versioning'
                """
            )
            assert cursor.fetchone() == ("D",)

            base = {
                "contrato_id": contract_id,
                "orgao_cnpj": "12345678000199",
                "orgao_nome": "Órgão original",
                "supplier_id_type": "CNPJ",
                "supplier_identifier": valid_cnpj,
                "fornecedor_nome": "Fornecedor original",
                "objeto_contrato": "Objeto original",
                "valor_total": "100.00",
                "data_inicio": "2026-01-01",
                "data_fim": "2026-12-31",
                "data_publicacao": "2026-01-02",
                "data_atualizacao_fonte": "2026-09-10",
                "source_updated_at": "2026-09-10T12:00:00Z",
                "uf": "SC",
                "municipio": "Florianópolis",
                "query_window_start": "2026-09-10",
                "query_window_end": "2026-09-10",
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([base]),),
            )

            newer_partial = {
                "contrato_id": contract_id,
                "orgao_nome": "",
                "supplier_id_type": "UNKNOWN",
                "supplier_identifier": None,
                "fornecedor_nome": None,
                "objeto_contrato": "Objeto corrigido",
                "valor_total": "250.00",
                "data_atualizacao_fonte": "2026-09-11",
                "source_updated_at": "2026-09-11T12:00:00Z",
                "query_window_start": "2026-09-11",
                "query_window_end": "2026-09-11",
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([newer_partial]),),
            )

            same_day_older = {
                "contrato_id": contract_id,
                "objeto_contrato": "Objeto anterior no mesmo dia",
                "valor_total": "2.00",
                "data_atualizacao_fonte": "2026-09-11",
                "source_updated_at": "2026-09-11T11:59:59Z",
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([same_day_older]),),
            )

            stale = {
                "contrato_id": contract_id,
                "objeto_contrato": "Objeto obsoleto",
                "valor_total": "1.00",
                "data_atualizacao_fonte": "2026-09-01",
                "source_updated_at": "2026-09-01T12:00:00Z",
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([stale]),),
            )

            no_clock = {
                "contrato_id": contract_id,
                "objeto_contrato": "Sem relógio da fonte",
                "valor_total": None,
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([no_clock]),),
            )

            assert stamp_contract_truth_labels(
                conn,
                [
                    {
                        "contrato_id": contract_id,
                        "status_normalized": "ACTIVE",
                        "quality_state": "VALID",
                        "quality_reasons": [],
                        "report_ready": True,
                        "source_updated_at": "2026-09-11T12:00:00Z",
                        "data_atualizacao_fonte": "2026-09-11",
                    }
                ],
            ) == 1
            assert stamp_contract_truth_labels(
                conn,
                [
                    {
                        "contrato_id": contract_id,
                        "status_normalized": "UNKNOWN",
                        "quality_state": "QUARANTINED",
                        "quality_reasons": ["stale"],
                        "report_ready": False,
                        "source_updated_at": "2026-09-11T11:59:59Z",
                        "data_atualizacao_fonte": "2026-09-11",
                    }
                ],
            ) == 0

            cursor.execute(
                """
                SELECT orgao_nome, fornecedor_nome, fornecedor_cnpj,
                       supplier_id_type, objeto_contrato, valor_total,
                       data_atualizacao_fonte, source_updated_at,
                       query_window_start, query_window_end,
                       status_normalized, quality_state
                FROM public.pncp_supplier_contracts
                WHERE contrato_id = %s
                """,
                (contract_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Órgão original"
            assert row[1] == "Fornecedor original"
            assert row[2] == valid_cnpj
            assert row[3] == "CNPJ"
            assert row[4] == "Objeto corrigido"
            assert str(row[5]) == "250.00"
            assert row[6].isoformat() == "2026-09-11"
            assert row[7].isoformat() == "2026-09-11T12:00:00+00:00"
            assert row[8].isoformat() == "2026-09-11"
            assert row[9].isoformat() == "2026-09-11"
            assert row[10:] == ("ACTIVE", "VALID")
    finally:
        conn.rollback()
        conn.close()
