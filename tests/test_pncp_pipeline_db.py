"""Database integration coverage for PNCP engineering persistence."""

from __future__ import annotations

import os
import subprocess
from copy import deepcopy

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database tests",
    ),
]


def _get_dsn() -> str:
    return os.getenv("TEST_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")


def _require_db() -> None:
    result = subprocess.run(["psql", _get_dsn(), "-c", "select 1"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return
    if os.getenv("REQUIRE_TEST_DB") == "1":
        pytest.fail(f"Database required but unavailable: {result.stderr or result.stdout}")
    pytest.skip(f"Database not available: {result.stderr or result.stdout}")


def _sample_opportunity() -> dict:
    return {
        "pncp_id": "test_pipeline_db_001",
        "source": "pncp",
        "source_id": "test_pipeline_db_001",
        "objeto_compra": "Reforma e adequacao predial com instalacoes eletricas",
        "orgao_cnpj": "82892282000143",
        "orgao_razao_social": "Municipio de Palhoca",
        "codigo_municipio_ibge": "4211903",
        "municipio": "Palhoca",
        "uf": "SC",
        "modalidade_id": 4,
        "modalidade_nome": "Concorrência - Eletrônica",
        "valor_total_estimado": 1500000.0,
        "data_publicacao": "2026-05-14T12:00:00+00:00",
        "data_abertura": None,
        "data_encerramento": None,
        "link_pncp": "https://pncp.gov.br/app/editais/82892282000143/2026/1",
        "link_sistema_origem": "https://example.test/origem/1",
        "is_engineering": True,
        "engineering_score": 92,
        "engineering_confidence": "engenharia_confirmada",
        "engineering_categories": ["REFORMA", "INSTALACOES_ELETRICAS"],
        "classification_reasons": {
            "matched_terms": ["reforma", "instalacoes eletricas"],
            "excluded_terms": [],
            "fields_used": ["objetoCompra"],
            "category": ["REFORMA", "INSTALACOES_ELETRICAS"],
            "classifier_version": "engineering-rules-v1",
        },
        "classifier_version": "engineering-rules-v1",
        "exclusion_reason": None,
        "distance_from_florianopolis_km": 14.2,
        "within_200km": True,
        "geographic_priority": "PRIORIDADE_1",
        "location_confidence": "codigo_ibge_pncp",
        "content_hash": "test_pipeline_db_hash_001",
    }


class TestPNCPPipelineDB:
    def test_engineering_opportunities_indexes_exist(self):
        _require_db()
        expected = {
            "idx_engineering_opportunities_is_engineering",
            "idx_engineering_opportunities_engineering_score",
            "idx_engineering_opportunities_within_200km",
            "idx_engineering_opportunities_codigo_municipio_ibge",
            "idx_engineering_opportunities_orgao_cnpj",
            "idx_engineering_opportunities_data_publicacao",
            "idx_engineering_opportunities_data_encerramento",
            "idx_engineering_opportunities_modalidade_id",
        }
        query = subprocess.run(
            [
                "psql",
                _get_dsn(),
                "-At",
                "-c",
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'engineering_opportunities'",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert query.returncode == 0, query.stderr or query.stdout
        found = {line.strip() for line in query.stdout.splitlines() if line.strip()}
        assert expected <= found

    def test_persist_engineering_opportunity_is_idempotent(self):
        _require_db()
        first = _sample_opportunity()
        second = deepcopy(first)
        second["engineering_score"] = 96
        second["classification_reasons"]["matched_terms"].append("adequacao predial")
        import json

        payload1 = json.dumps([first], ensure_ascii=False)
        payload2 = json.dumps([second], ensure_ascii=False)
        sql = (
            "WITH payload AS (SELECT %s::jsonb AS body) "
            "INSERT INTO engineering_opportunities ("
            "pncp_id, source, source_id, objeto_compra, orgao_cnpj, orgao_razao_social, "
            "codigo_municipio_ibge, municipio, uf, modalidade_id, modalidade_nome, "
            "valor_total_estimado, data_publicacao, data_abertura, data_encerramento, "
            "link_pncp, link_sistema_origem, is_engineering, engineering_score, "
            "engineering_confidence, engineering_categories, classification_reasons, "
            "classifier_version, exclusion_reason, distance_from_florianopolis_km, "
            "within_200km, geographic_priority, location_confidence, content_hash, first_seen_at, last_seen_at"
            ") "
            "SELECT "
            "x->>'pncp_id', x->>'source', x->>'source_id', x->>'objeto_compra', x->>'orgao_cnpj', x->>'orgao_razao_social', "
            "x->>'codigo_municipio_ibge', x->>'municipio', x->>'uf', (x->>'modalidade_id')::int, x->>'modalidade_nome', "
            "(x->>'valor_total_estimado')::numeric, (x->>'data_publicacao')::timestamptz, NULL, NULL, "
            "x->>'link_pncp', x->>'link_sistema_origem', (x->>'is_engineering')::boolean, (x->>'engineering_score')::int, "
            "x->>'engineering_confidence', ARRAY(SELECT jsonb_array_elements_text(x->'engineering_categories')), x->'classification_reasons', "
            "x->>'classifier_version', NULLIF(x->>'exclusion_reason',''), (x->>'distance_from_florianopolis_km')::numeric, "
            "(x->>'within_200km')::boolean, x->>'geographic_priority', x->>'location_confidence', x->>'content_hash', NOW(), NOW() "
            "FROM payload, jsonb_array_elements(body) AS x "
            "ON CONFLICT (pncp_id) DO UPDATE SET "
            "engineering_score = EXCLUDED.engineering_score, "
            "classification_reasons = EXCLUDED.classification_reasons, "
            "within_200km = EXCLUDED.within_200km, "
            "geographic_priority = EXCLUDED.geographic_priority, "
            "location_confidence = EXCLUDED.location_confidence, "
            "last_seen_at = NOW()"
        )
        ins1 = subprocess.run(
            ["psql", _get_dsn(), "-v", f"payload={payload1}", "-c", sql % ":'payload'"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert ins1.returncode == 0, ins1.stderr or ins1.stdout
        ins2 = subprocess.run(
            ["psql", _get_dsn(), "-v", f"payload={payload2}", "-c", sql % ":'payload'"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert ins2.returncode == 0, ins2.stderr or ins2.stdout

        row_q = subprocess.run(
            [
                "psql",
                _get_dsn(),
                "-At",
                "-c",
                "SELECT engineering_score, within_200km, geographic_priority, location_confidence, COUNT(*) OVER () "
                "FROM engineering_opportunities WHERE pncp_id = 'test_pipeline_db_001'",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert row_q.returncode == 0, row_q.stderr or row_q.stdout
        parts = row_q.stdout.strip().split("|")
        assert parts[0] == "96"
        assert parts[1] == "t"
        assert parts[2] == "PRIORIDADE_1"
        assert parts[3] == "codigo_ibge_pncp"
        assert parts[4] == "1"

        cleanup = subprocess.run(
            ["psql", _get_dsn(), "-c", "DELETE FROM engineering_opportunities WHERE pncp_id = 'test_pipeline_db_001'"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert cleanup.returncode == 0, cleanup.stderr or cleanup.stdout
