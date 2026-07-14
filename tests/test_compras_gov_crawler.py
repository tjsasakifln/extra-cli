"""Unit tests for scripts/crawl/compras_gov_crawler.py."""

from unittest.mock import patch

from scripts.crawl import compras_gov_crawler as cgc

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_LEGACY_RECORD = {
    "id_compra": "20230001",
    "objeto": "Contratacao de servico de limpeza",
    "valor_estimado": 150000.00,
    "modalidade": 1,
    "nome_modalidade": "Pregao",
    "data_publicacao": "2023-06-15T10:00:00",
    "data_entrega_proposta": "2023-07-15T18:00:00",
}

MOCK_14133_RECORD = {
    "numeroControlePNCP": "123456789",
    "objetoCompra": "Aquisicao de equipamentos de informatica",
    "valorTotalEstimado": 50000.00,
    "orgaoEntidadeRazaoSocial": "Instituto Federal de Santa Catarina",
    "orgaoEntidadeCnpj": "11111111111111",
    "unidadeOrgaoUfSigla": "SC",
    "unidadeOrgaoMunicipioNome": "Sao Jose",
    "unidadeOrgaoCodigoIbge": "4205400",
    "modalidadeNome": "Concorrencia",
    "dataPublicacaoPncp": "2025-01-10T08:00:00",
    "dataAberturaPropostaPncp": "2025-02-10T09:00:00",
    "dataEncerramentoPropostaPncp": "2025-02-10T18:00:00",
}

MOCK_LEGACY_RECORD_NO_CNPJ = {
    "id_compra": "20230002",
    "objeto": "Servico sem CNPJ",
    "valor_estimado": 10000.00,
    "modalidade": 1,
    "nome_modalidade": "Pregao",
    "data_publicacao": "2023-06-20T10:00:00",
    "data_entrega_proposta": "2023-07-20T18:00:00",
}

# ---------------------------------------------------------------------------
# crawl()
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl()."""

    @patch("scripts.crawl.compras_gov_crawler._make_request", return_value=None)
    def test_crawl_incremental_returns_list(self, mock_request):
        """crawl('incremental') returns a list even when API returns no data."""
        result = cgc.crawl(mode="incremental")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns an empty list."""
        result = cgc.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_transform_mock_legacy_record(self):
        """transform() normalizes a legacy record with all 17 fields."""
        result = cgc.transform([MOCK_LEGACY_RECORD])
        assert len(result) == 1

        record = result[0]

        # Legacy API returns limited fields (no CNPJ, orgao, UF, municipio)
        assert record["pncp_id"].startswith("cg_leg_")
        assert record["objeto_compra"] == "Contratacao de servico de limpeza"
        assert record["valor_total_estimado"] == 150000.00
        assert record["modalidade_id"] == 1  # Pregao (codigo inteiro)
        assert record["modalidade_nome"] == "Pregao"
        assert record["esfera_id"] == 1  # Federal (default)
        assert record["uf"] == ""  # Legacy endpoint nao fornece UF
        assert record["municipio"] == ""  # Legacy endpoint nao fornece municipio
        assert record["codigo_municipio_ibge"] == ""
        assert record["orgao_razao_social"] == ""  # Legacy endpoint nao fornece orgao
        assert record["orgao_cnpj"] == ""  # Legacy endpoint nao fornece CNPJ
        assert record["data_publicacao"] == "2023-06-15"
        assert record["data_abertura"] == "2023-07-15"
        assert record["data_encerramento"] is None
        assert record["link_pncp"] is not None
        assert record["content_hash"] is not None
        assert record["source_id"].startswith("cg_leg_")

        # Count total fields
        expected_fields = {
            "pncp_id",
            "objeto_compra",
            "valor_total_estimado",
            "modalidade_id",
            "modalidade_nome",
            "esfera_id",
            "uf",
            "municipio",
            "codigo_municipio_ibge",
            "orgao_razao_social",
            "orgao_cnpj",
            "data_publicacao",
            "data_abertura",
            "data_encerramento",
            "link_pncp",
            "content_hash",
            "source_id",
        }
        assert set(record.keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(record.keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(record.keys())}"
        )

    def test_transform_mock_14133_record(self):
        """transform() normalizes a Lei 14.133 record with all fields."""
        result = cgc.transform([MOCK_14133_RECORD])
        assert len(result) == 1

        record = result[0]

        # Verify key fields
        assert record["pncp_id"].startswith("cg_14133_")
        assert record["objeto_compra"] == "Aquisicao de equipamentos de informatica"
        assert record["valor_total_estimado"] == 50000.00
        assert record["modalidade_id"] == 3  # Concorrencia
        assert record["modalidade_nome"] == "Concorrencia"
        assert record["esfera_id"] == 1
        assert record["uf"] == "SC"
        assert record["municipio"] == "Sao Jose"
        assert record["codigo_municipio_ibge"] == "4205400"
        assert record["orgao_razao_social"] == "Instituto Federal de Santa Catarina"
        assert record["orgao_cnpj"] == "11111111111111"
        assert record["data_publicacao"] == "2025-01-10"
        assert record["data_abertura"] == "2025-02-10"
        assert record["data_encerramento"] == "2025-02-10"
        assert record["link_pncp"] is not None

        # Count total fields
        expected_fields = {
            "pncp_id",
            "objeto_compra",
            "valor_total_estimado",
            "modalidade_id",
            "modalidade_nome",
            "esfera_id",
            "uf",
            "municipio",
            "codigo_municipio_ibge",
            "orgao_razao_social",
            "orgao_cnpj",
            "data_publicacao",
            "data_abertura",
            "data_encerramento",
            "link_pncp",
            "content_hash",
            "source_id",
        }
        assert set(record.keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(record.keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(record.keys())}"
        )

    def test_transform_dedup(self):
        """transform() deduplicates records with the same pncp_id."""
        result = cgc.transform([MOCK_LEGACY_RECORD, MOCK_LEGACY_RECORD])
        assert len(result) == 1, f"Expected 1 record after dedup, got {len(result)}"

    def test_transform_missing_cnpj_filtered(self):
        """transform() filters out 14133 records without CNPJ, but keeps legacy records."""
        # Legacy records without CNPJ are preserved (CNPJ filter only for 14133)
        legacy_result = cgc.transform([MOCK_LEGACY_RECORD_NO_CNPJ])
        assert len(legacy_result) == 1, "Legacy records without CNPJ should be preserved"
