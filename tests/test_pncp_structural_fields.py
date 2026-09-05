"""#546 — official PNCP structural fields persist from the source payload."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.crawl.contracts_crawler import _transform_record
from scripts.crawl.pncp_crawler_adapter import transform_contracts
from scripts.crawl.pncp_structural_fields import (
    STRUCTURAL_FIELD_KEYS,
    extract_pncp_structural_fields,
    plan_structural_backfill,
)
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/107_pncp_structural_fields.sql"

PAYLOAD_ID_NOME = {
    "numeroControlePNCP": "00000000000000000001",
    "tipoContratoId": 1,
    "tipoContratoNome": "Contrato",
    "categoriaProcessoId": 2,
    "categoriaProcessoNome": "Servicos de Engenharia",
    "modalidadeId": 6,
    "modalidadeNome": "Pregao Eletronico",
    "codigoRegimeExecucao": 5,
    "regimeExecucaoNome": "Contratacao integrada",
    "srp": False,
    "numeroRetificacao": 0,
    "objetoContrato": "Registro de precos para material de expediente",
}

PAYLOAD_NESTED_OBJECTS = {
    "numeroControlePNCP": "00000000000000000002",
    "tipoContrato": {"id": 3, "nome": "Empenho"},
    "categoriaProcesso": {"id": 1, "nome": "Obras"},
    "compra": {
        "modalidadeId": 8,
        "modalidadeNome": "Dispensa",
        "srp": True,
        "regimeExecucao": {"id": 1, "nome": "Empreitada por preco global"},
    },
    "numeroRetificacao": 2,
    "objetoContrato": "Execucao de obra de pavimentacao",
}

PAYLOAD_MISSING = {
    "numeroControlePNCP": "00000000000000000003",
    "objetoContrato": "Ata de registro de precos e credenciamento de engenharia",
}

RAW_TRANSFORM = {
    "numeroControlePNCP": "123456780001992026000001",
    "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Prefeitura"},
    "unidadeOrgao": {
        "nomeUnidade": "Secretaria de Obras",
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
    },
    "niFornecedor": "11222333000181",
    "tipoPessoa": "PJ",
    "nomeRazaoSocialFornecedor": "Construtora Exemplo Ltda",
    "valorGlobal": 150000.00,
    "dataAssinatura": "2026-03-01T10:00:00Z",
    "dataPublicacaoPncp": "2026-03-02T12:00:00Z",
    "dataVigenciaInicio": "2026-03-10T00:00:00Z",
    "dataVigenciaFim": "2027-03-09T23:59:59Z",
    "objetoContrato": "Execucao de obra de drenagem urbana",
    "tipoContratoId": 1,
    "tipoContratoNome": "Contrato",
    "categoriaProcessoId": 1,
    "categoriaProcessoNome": "Obras",
    "modalidadeId": 6,
    "modalidadeNome": "Pregao Eletronico",
    "codigoRegimeExecucao": 5,
    "regimeExecucaoNome": "Contratacao integrada",
    "srp": False,
    "numeroRetificacao": 1,
}


def test_mapper_round_trips_id_nome_fields() -> None:
    fields = extract_pncp_structural_fields(PAYLOAD_ID_NOME)
    assert fields["tipo_contrato_id"] == 1
    assert fields["tipo_contrato_nome"] == "Contrato"
    assert fields["categoria_processo_id"] == 2
    assert fields["categoria_processo_nome"] == "Servicos de Engenharia"
    assert fields["modalidade_id"] == 6
    assert fields["modalidade_nome"] == "Pregao Eletronico"
    assert fields["regime_execucao_id"] == 5
    assert fields["regime_execucao_nome"] == "Contratacao integrada"
    assert fields["srp"] is False
    assert fields["numero_retificacao"] == 0


def test_mapper_reads_nested_objects_and_parent_compra() -> None:
    fields = extract_pncp_structural_fields(PAYLOAD_NESTED_OBJECTS)
    assert fields["tipo_contrato_id"] == 3
    assert fields["tipo_contrato_nome"] == "Empenho"
    assert fields["categoria_processo_id"] == 1
    assert fields["categoria_processo_nome"] == "Obras"
    assert fields["modalidade_id"] == 8
    assert fields["modalidade_nome"] == "Dispensa"
    assert fields["regime_execucao_id"] == 1
    assert fields["regime_execucao_nome"] == "Empreitada por preco global"
    assert fields["srp"] is True
    assert fields["numero_retificacao"] == 2


def test_mapper_does_not_infer_from_objeto_text() -> None:
    fields = extract_pncp_structural_fields(PAYLOAD_MISSING)
    for key in STRUCTURAL_FIELD_KEYS:
        assert fields[key] is None, key
    # Official Empenho + SRP wins over objeto wording.
    official = extract_pncp_structural_fields(
        {
            **PAYLOAD_MISSING,
            "tipoContratoNome": "Contrato",
            "srp": False,
            "objetoContrato": "registro de precos, credenciamento, empenho",
        }
    )
    assert official["tipo_contrato_nome"] == "Contrato"
    assert official["srp"] is False


def test_transform_attaches_official_fields() -> None:
    record = _transform_record(RAW_TRANSFORM)
    assert record is not None
    assert record["tipo_contrato_id"] == 1
    assert record["tipo_contrato_nome"] == "Contrato"
    assert record["categoria_processo_id"] == 1
    assert record["categoria_processo_nome"] == "Obras"
    assert record["modalidade_id"] == 6
    assert record["modalidade_nome"] == "Pregao Eletronico"
    assert record["regime_execucao_nome"] == "Contratacao integrada"
    assert record["srp"] is False
    assert record["numero_retificacao"] == 1


def test_adapter_uses_same_mapper() -> None:
    rows = transform_contracts([RAW_TRANSFORM])
    assert len(rows) == 1
    assert rows[0]["tipo_contrato_id"] == 1
    assert rows[0]["categoria_processo_nome"] == "Obras"
    assert rows[0]["modalidade_nome"] == "Pregao Eletronico"
    assert rows[0]["srp"] is False


def test_backfill_is_resumable_limitable_and_idempotent() -> None:
    payloads = [
        {"numeroControlePNCP": "c1", "tipoContratoNome": "Contrato"},
        {"numeroControlePNCP": "c2", "tipoContratoNome": "Empenho"},
        {"numeroControlePNCP": "c3", "tipoContratoNome": "Carta Contrato"},
        {"objetoContrato": "sem id"},
    ]
    first = plan_structural_backfill(payloads, limit=2)
    assert [row["contrato_id"] for row in first] == ["c1", "c2"]
    resumed = plan_structural_backfill(payloads, after_contrato_id="c2", limit=10)
    assert [row["contrato_id"] for row in resumed] == ["c3"]
    again = plan_structural_backfill(payloads, after_contrato_id="c3")
    assert again == []


def test_backfill_refuses_pncp_traffic_by_default() -> None:
    source = (ROOT / "scripts/ops/backfill_pncp_structural_fields.py").read_text(encoding="utf-8")
    assert "refusing --from-pncp" in source
    assert "archived payloads first" in source


def test_migration_persists_and_exposes_fields() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for column in STRUCTURAL_FIELD_KEYS:
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql
        assert column in sql
    assert "COALESCE(EXCLUDED.tipo_contrato_id, target.tipo_contrato_id)" in sql
    assert "CREATE OR REPLACE FUNCTION public.apply_pncp_structural_fields" in sql
    assert "contract.tipo_contrato_id" in sql
    assert "contract.categoria_processo_nome" in sql
    assert "contract.srp" in sql
    assert "contract.numero_retificacao" in sql
    assert "COALESCE(contract.regime_execucao_nome, contract.regime_execucao_id::TEXT) AS regime_execucao" in sql
    assert "Not inferred from objeto" in sql
    # Observations view must consume persisted modalidade, not NULL.
    assert "contract.modalidade_id" in sql
    assert "NULL::INTEGER AS modalidade_id" not in sql.split("UNION ALL")[-1]


def test_upsert_sql_reads_mapped_json_keys() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for key in STRUCTURAL_FIELD_KEYS:
        assert f"rec->>'{key}'" in sql
    assert "objetoContrato" not in sql


@pytest.mark.real_db
def test_upsert_round_trip_persists_structural_fields_on_canonical_view() -> None:
    """Drive transform → upsert_pncp_supplier_contracts → v_contracts_canonical_v2."""
    import psycopg2
    import psycopg2.extras

    record = _transform_record(RAW_TRANSFORM)
    assert record is not None
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'pncp_supplier_contracts' "
                "AND column_name = 'tipo_contrato_id'"
            )
            if cursor.fetchone() is None:
                pytest.fail("migration 107 not applied: tipo_contrato_id missing")
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([record], default=str),),
            )
            cursor.execute(
                """
                SELECT tipo_contrato_id, tipo_contrato_nome, categoria_processo_id,
                       categoria_processo_nome, modalidade_id, modalidade_nome,
                       regime_execucao, srp, numero_retificacao
                FROM v_contracts_canonical_v2
                WHERE contrato_id = %s
                """,
                (record["contrato_id"],),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["tipo_contrato_id"] == 1
            assert row["tipo_contrato_nome"] == "Contrato"
            assert row["categoria_processo_id"] == 1
            assert row["categoria_processo_nome"] == "Obras"
            assert row["modalidade_id"] == 6
            assert row["modalidade_nome"] == "Pregao Eletronico"
            assert row["regime_execucao"] == "Contratacao integrada"
            assert row["srp"] is False
            assert row["numero_retificacao"] == 1
            cursor.execute(
                "SELECT contrato_id FROM apply_pncp_structural_fields(%s::jsonb)",
                (
                    json.dumps(
                        [
                            {
                                "contrato_id": record["contrato_id"],
                                "tipo_contrato_id": 1,
                                "tipo_contrato_nome": "Contrato",
                            }
                        ]
                    ),
                ),
            )
            assert cursor.fetchone()["contrato_id"] == record["contrato_id"]
        conn.commit()
    finally:
        conn.close()
