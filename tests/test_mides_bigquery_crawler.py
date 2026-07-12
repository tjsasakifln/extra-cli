"""Unit tests for scripts/crawl/mides_bigquery_crawler.py.

All BigQuery calls are mocked. No real network or database access.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from scripts.crawl import mides_bigquery_crawler as mides

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bq_row():
    """Create a mock BigQuery row-like object."""

    def _make_row(**kwargs):
        """Return a dict-like object that supports .items() and .get()."""
        return kwargs

    return _make_row


@pytest.fixture
def sample_empenho(mock_bq_row):
    """A single SC empenho record (non-null id_municipio)."""
    return mock_bq_row(
        ano=2024,
        mes=1,
        data=date(2024, 1, 4),
        sigla_uf="SC",
        id_municipio="4200051",
        orgao="1",
        id_unidade_gestora=None,
        id_licitacao_bd=None,
        id_licitacao="78511052000110#PR56/2022",
        modalidade_licitacao=None,
        id_empenho_bd="1 1 4200051 24",
        id_empenho=None,
        numero="1",
        descricao="valor que se empenha para pagamento de servicos de TI",
        modalidade=None,
        funcao="1",
        subfuncao="31",
        programa=None,
        acao=None,
        elemento_despesa="334008",
        valor_inicial=0.0,
        valor_reforco=0.0,
        valor_anulacao=0.0,
        valor_ajuste=0.0,
        valor_final=6248.40,
    )


@pytest.fixture
def sample_empenho_no_cnpj(mock_bq_row):
    """SC empenho record without id_licitacao CNPJ."""
    return mock_bq_row(
        ano=2023,
        mes=6,
        data=date(2023, 6, 15),
        sigla_uf="SC",
        id_municipio="4205407",
        orgao="3",
        id_unidade_gestora=None,
        id_licitacao_bd=None,
        id_licitacao="PR2/2023",
        modalidade_licitacao=None,
        id_empenho_bd=None,
        id_empenho=None,
        numero="1520",
        descricao="aquisicao de material de escritorio",
        modalidade=None,
        funcao="4",
        subfuncao="122",
        programa=None,
        acao=None,
        elemento_despesa="334099",
        valor_inicial=0.0,
        valor_reforco=0.0,
        valor_anulacao=0.0,
        valor_ajuste=0.0,
        valor_final=3500.00,
    )


@pytest.fixture
def mock_municipio_cache():
    """Mock municipality name cache with known SC IBGE codes."""
    return {
        "4200051": "Abdon Batista",
        "4205407": "Campos Novos",
        "4204558": "Chapeco",
    }


# ---------------------------------------------------------------------------
# Tests: _make_pncp_id
# ---------------------------------------------------------------------------


class TestMakePncpId:
    def test_with_id_empenho_bd(self, sample_empenho):
        """Should use id_empenho_bd when available."""
        doc_id = mides._make_pncp_id(sample_empenho)
        assert doc_id == "mides-empenho-1-1-4200051-24"

    def test_without_id_empenho_bd(self, sample_empenho_no_cnpj):
        """Should fall back to composite key."""
        doc_id = mides._make_pncp_id(sample_empenho_no_cnpj)
        assert "mides-empenho-4205407-3-2023-1520" == doc_id


# ---------------------------------------------------------------------------
# Tests: _make_content_hash
# ---------------------------------------------------------------------------


class TestMakeContentHash:
    def test_consistent_hashing(self, sample_empenho):
        """Same input should produce same hash."""
        h1 = mides._make_content_hash(sample_empenho)
        h2 = mides._make_content_hash(sample_empenho)
        assert h1 == h2
        assert len(h1) == 32  # md5 hexdigest

    def test_different_records_different_hash(self, sample_empenho, sample_empenho_no_cnpj):
        """Different records should produce different hashes."""
        h1 = mides._make_content_hash(sample_empenho)
        h2 = mides._make_content_hash(sample_empenho_no_cnpj)
        assert h1 != h2


# ---------------------------------------------------------------------------
# Tests: _extract_cnpj_from_id_licitacao
# ---------------------------------------------------------------------------


class TestExtractCnpj:
    def test_cnpj_hash_format(self):
        """Should extract CNPJ from 'CNPJ#process' format."""
        result = mides._extract_cnpj_from_id_licitacao("78511052000110#PR56/2022")
        assert result == "78511052000110"

    def test_no_cnpj(self):
        """Should return None when no CNPJ pattern found."""
        assert mides._extract_cnpj_from_id_licitacao("PR2/2023") is None
        assert mides._extract_cnpj_from_id_licitacao(None) is None
        assert mides._extract_cnpj_from_id_licitacao("") is None

    def test_cnpj_without_hash(self):
        """Should extract 14-digit CNPJ even without # separator."""
        result = mides._extract_cnpj_from_id_licitacao("78511052000110")
        assert result == "78511052000110"


# ---------------------------------------------------------------------------
# Tests: build_sc_query
# ---------------------------------------------------------------------------


class TestBuildScQuery:
    def test_basic_query(self):
        """Should include SC filter, year, and non-null id_municipio."""
        q = mides.build_sc_query(2024)
        assert "sigla_uf = 'SC'" in q
        assert "ano = 2024" in q
        assert "id_municipio IS NOT NULL" in q
        assert "LIMIT" not in q

    def test_with_limit_offset(self):
        """Should add LIMIT and OFFSET when provided."""
        q = mides.build_sc_query(2024, limit=100, offset=200)
        assert "LIMIT 100" in q
        assert "OFFSET 200" in q

    def test_query_in_pncp_monitor_project(self):
        """Query should reference the correct table."""
        q = mides.build_sc_query(2021)
        assert "basedosdados.world_wb_mides.empenho" in q


# ---------------------------------------------------------------------------
# Tests: transform
# ---------------------------------------------------------------------------


class TestTransform:
    @patch.object(mides, "_load_municipio_cache")
    def test_transform_single_record(
        self,
        mock_cache,
        sample_empenho,
        mock_municipio_cache,
    ):
        """Should correctly map a single empenho record to pncp_raw_bids."""
        mock_cache.return_value = mock_municipio_cache

        result = mides.transform([sample_empenho])

        assert len(result) == 1
        r = result[0]

        assert r["pncp_id"] == "mides-empenho-1-1-4200051-24"
        assert r["objeto_compra"] == "valor que se empenha para pagamento de servicos de TI"
        assert r["valor_total_estimado"] == 6248.40
        assert r["modalidade_id"] == 0
        assert r["uf"] == "SC"
        assert r["municipio"] == "Abdon Batista"
        assert r["codigo_municipio_ibge"] == "4200051"
        assert r["orgao_cnpj"] == "78511052000110"
        assert r["orgao_razao_social"] is None
        assert r["data_publicacao"] == "2024-01-04"
        assert r["data_abertura"] is None
        assert r["source"] == "mides-bigquery"
        assert r["is_active"] is True
        assert len(r["content_hash"]) == 32
        # esfera_id derived from CNPJ (78511052000110 starts with 7 → private → default 3)
        assert r["esfera_id"] == 3

    @patch.object(mides, "_load_municipio_cache")
    def test_transform_record_without_cnpj(
        self,
        mock_cache,
        sample_empenho_no_cnpj,
        mock_municipio_cache,
    ):
        """Should handle records without CNPJ."""
        mock_cache.return_value = mock_municipio_cache

        result = mides.transform([sample_empenho_no_cnpj])

        assert len(result) == 1
        r = result[0]

        assert r["orgao_cnpj"] is None  # No CNPJ in id_licitacao
        assert r["municipio"] == "Campos Novos"
        assert r["codigo_municipio_ibge"] == "4205407"
        assert r["valor_total_estimado"] == 3500.00

    @patch.object(mides, "_load_municipio_cache")
    def test_transform_empty_list(self, mock_cache):
        """Empty input should return empty output."""
        mock_cache.return_value = {}
        result = mides.transform([])
        assert result == []

    @patch.object(mides, "_load_municipio_cache")
    def test_transform_unknown_municipio(
        self,
        mock_cache,
        mock_bq_row,
    ):
        """Should handle municipio not in cache gracefully."""
        mock_cache.return_value = {}  # Empty cache
        rec = mock_bq_row(
            ano=2024,
            mes=1,
            data=date(2024, 1, 4),
            sigla_uf="SC",
            id_municipio="9999999",
            orgao="1",
            id_licitacao=None,
            id_empenho_bd=None,
            numero="1",
            descricao="teste",
            valor_final=100.0,
        )
        result = mides.transform([rec])
        assert result[0]["municipio"] == ""  # Unknown IBGE -> empty name
        assert result[0]["codigo_municipio_ibge"] == "9999999"

    @patch.object(mides, "_load_municipio_cache")
    def test_transform_dedup_pncp_id(
        self,
        mock_cache,
        mock_bq_row,
        mock_municipio_cache,
    ):
        """Should add #N suffix to duplicate pncp_ids within same batch."""
        mock_cache.return_value = mock_municipio_cache

        # Two records with same id_empenho_bd=None and same composite key
        rec1 = mock_bq_row(
            ano=2024, mes=1, data="2024-01-04", sigla_uf="SC",
            id_municipio=4200051, orgao="1", id_licitacao=None,
            id_empenho_bd=None, numero="1",
            descricao="primeiro item", valor_final=100.0,
        )
        rec2 = mock_bq_row(
            ano=2024, mes=1, data="2024-01-04", sigla_uf="SC",
            id_municipio=4200051, orgao="1", id_licitacao=None,
            id_empenho_bd=None, numero="1",
            descricao="segundo item", valor_final=200.0,
        )

        result = mides.transform([rec1, rec2])
        assert len(result) == 2
        base_id = "mides-empenho-4200051-1-2024-1"
        assert result[0]["pncp_id"] == base_id  # First occurrence, no suffix
        assert result[1]["pncp_id"] == f"{base_id}#1"  # Second, dedup suffix
        assert result[0]["pncp_id"] != result[1]["pncp_id"]


# ---------------------------------------------------------------------------
# Tests: build_incremental_query
# ---------------------------------------------------------------------------


class TestBuildIncrementalQuery:
    def test_incremental_uses_days_back(self):
        """Should use DATE_SUB with correct days_back."""
        q = mides.build_incremental_query(days_back=90)
        assert "INTERVAL 90 DAY" in q
        assert "sigla_uf = 'SC'" in q

    def test_incremental_orders_by_data(self):
        q = mides.build_incremental_query()
        assert "ORDER BY data" in q


# ---------------------------------------------------------------------------
# Tests: _infer_esfera_from_cnpj
# ---------------------------------------------------------------------------


class TestInferEsferaFromCNPJ:
    def test_federal_cnpj(self):
        """CNPJ starting with 1 should return 1 (Federal)."""
        assert mides._infer_esfera_from_cnpj("10785623000190") == 1

    def test_estadual_cnpj(self):
        """CNPJ starting with 2 should return 2 (Estadual)."""
        assert mides._infer_esfera_from_cnpj("20867493000100") == 2

    def test_municipal_cnpj(self):
        """CNPJ starting with 3 should return 3 (Municipal)."""
        assert mides._infer_esfera_from_cnpj("30765432000190") == 3

    def test_private_cnpj_defaults_municipal(self):
        """CNPJ starting with 4-9 should default to 3 (Municipal)."""
        assert mides._infer_esfera_from_cnpj("50765432000190") == 3
        assert mides._infer_esfera_from_cnpj("80765432000190") == 3

    def test_none_cnpj_defaults_municipal(self):
        """None CNPJ should default to 3 (Municipal)."""
        assert mides._infer_esfera_from_cnpj(None) == 3

    def test_empty_cnpj_defaults_municipal(self):
        """Empty CNPJ should default to 3 (Municipal)."""
        assert mides._infer_esfera_from_cnpj("") == 3

    def test_cnpj_with_formatting(self):
        """Should handle CNPJ with formatting characters."""
        assert mides._infer_esfera_from_cnpj("10.785.623/0001-90") == 1
        assert mides._infer_esfera_from_cnpj("20.867.493/0001-00") == 2
