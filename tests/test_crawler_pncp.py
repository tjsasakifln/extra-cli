"""Unit tests for scripts/crawl/pncp_crawler_adapter.py.

Tests the sync adapter that is the single PNCP crawler implementation
after TD-3.2 consolidation (BidsCrawler was deprecated).
"""

import hashlib
from unittest.mock import Mock, patch

import pytest

from scripts.crawl import pncp_crawler_adapter as pca

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_RAW_RECORD = {
    "objetoCompra": "Construcao de escola municipal",
    "valorTotalEstimado": 500000.00,
    "modalidadeId": 4,
    "modalidadeNome": "Concorrencia",
    "orgaoEntidade": {
        "cnpj": "12345678000199",
        "razaoSocial": "Prefeitura Municipal de Exemplo",
    },
    "unidadeOrgao": {
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
        "codigoIbge": "4205407",
    },
    "dataPublicacao": "2026-07-01T10:00:00Z",
    "dataAbertura": "2026-08-01T09:00:00Z",
    "dataEncerramento": "2026-08-15T18:00:00Z",
    "linkSistemaOrigem": "https://pncp.gov.br/contratacoes/123",
}

MOCK_RAW_NO_CNPJ = {
    "objetoCompra": "Servico de limpeza",
    "valorTotalEstimado": 10000.00,
    "modalidadeId": 5,
    "modalidadeNome": "Pregao Eletronico",
    "dataPublicacao": "2026-07-01",
}


# ---------------------------------------------------------------------------
# _generate_content_hash()
# ---------------------------------------------------------------------------


class TestGenerateContentHash:
    """Tests for _generate_content_hash()."""

    def test_generates_deterministic_hash(self):
        """Same input produces same hash."""
        h1 = pca._generate_content_hash(MOCK_RAW_RECORD)
        h2 = pca._generate_content_hash(MOCK_RAW_RECORD)
        assert h1 == h2
        assert len(h1) == 32  # MD5 hex digest

    def test_different_inputs_different_hashes(self):
        """Different inputs produce different hashes."""
        # Use normalized records (as produced by _transform_record)
        rec1 = pca._transform_record(MOCK_RAW_RECORD)
        rec2 = dict(MOCK_RAW_RECORD)
        rec2["objetoCompra"] = "Reforma de predio publico"
        rec2 = pca._transform_record(rec2)
        assert rec1 is not None and rec2 is not None
        h1 = pca._generate_content_hash(rec1)
        h2 = pca._generate_content_hash(rec2)
        assert h1 != h2


# ---------------------------------------------------------------------------
# _transform_record()
# ---------------------------------------------------------------------------


class TestTransformRecord:
    """Tests for _transform_record()."""

    def test_happy_path(self):
        """_transform_record() normalizes a complete record."""
        result = pca._transform_record(MOCK_RAW_RECORD)
        assert result is not None
        assert result["objeto_compra"] == "Construcao de escola municipal"
        assert result["orgao_cnpj"] == "12345678000199"
        assert result["uf"] == "SC"
        assert result["data_publicacao"] == "2026-07-01"
        assert result["valor_total_estimado"] == 500000.00

    def test_missing_cnpj_returns_record(self):
        """_transform_record() still returns a record even without CNPJ
        (the CNPJ filter happens in transform(), not _transform_record)."""
        result = pca._transform_record(MOCK_RAW_NO_CNPJ)
        assert result is not None
        assert result["orgao_cnpj"] == ""  # Empty but record still returned

    def test_returns_content_hash(self):
        """_transform_record() includes a content_hash field."""
        result = pca._transform_record(MOCK_RAW_RECORD)
        assert "content_hash" in result
        assert len(result["content_hash"]) == 32

    def test_synthetic_pncp_id_when_missing(self):
        """_transform_record() generates synthetic ID when pncp_id is missing."""
        rec = dict(MOCK_RAW_RECORD)
        rec.pop("linkSistemaOrigem", None)
        result = pca._transform_record(rec)
        assert result is not None
        assert len(result["pncp_id"]) == 32


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns empty list."""
        assert pca.transform([]) == []

    def test_transform_filters_by_keyword(self):
        """transform() filters non-engineering records."""
        non_eng = dict(MOCK_RAW_RECORD)
        non_eng["objetoCompra"] = "Material de escritorio"
        result = pca.transform([MOCK_RAW_RECORD, non_eng])
        # Only the engineering record should pass
        assert len(result) == 1
        assert "Construcao" in result[0]["objeto_compra"]

    def test_transform_skips_records_without_cnpj(self):
        """transform() skips records without orgao_cnpj."""
        result = pca.transform([MOCK_RAW_NO_CNPJ])
        assert len(result) == 0
