"""Unit tests for scripts/crawl/transformer.py.

Covers all public and private functions:
- _date_fallback_iso
- compute_content_hash
- transform_pncp_item
- transform_batch
"""

import hashlib
from datetime import datetime, timezone

import pytest

from scripts.crawl import transformer as tr


# ---------------------------------------------------------------------------
# _date_fallback_iso()
# ---------------------------------------------------------------------------


class TestDateFallbackIso:
    """Tests for _date_fallback_iso()."""

    def test_returns_valid_iso_format(self):
        """_date_fallback_iso() returns a string parseable as ISO datetime."""
        result = tr._date_fallback_iso()
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)

    def test_returns_utc_timezone(self):
        """_date_fallback_iso() includes Z or +00:00 timezone."""
        result = tr._date_fallback_iso()
        assert result.endswith("+00:00") or result.endswith("Z") or "+00:00" in result

    def test_is_approximately_yesterday(self):
        """_date_fallback_iso() returns ~24h before now."""
        result = tr._date_fallback_iso()
        parsed = datetime.fromisoformat(result)
        now = datetime.now(timezone.utc)
        diff = now - parsed
        # Should be between 23h and 25h ago
        assert 82800 <= diff.total_seconds() <= 90000, (
            f"Expected ~24h ago, got {diff.total_seconds():.0f}s"
        )


# ---------------------------------------------------------------------------
# compute_content_hash()
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    """Tests for compute_content_hash()."""

    def test_known_input_returns_expected_hash(self):
        """compute_content_hash() returns deterministic SHA-256 for known inputs."""
        item = {
            "objetoCompra": "Aquisicao de equipamentos",
            "valorTotalEstimado": 50000.00,
            "situacaoCompraNome": "Divulgado",
        }
        canonical = "aquisicao de equipamentos|50000.0|divulgado"
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert tr.compute_content_hash(item) == expected

    def test_different_inputs_different_hashes(self):
        """Different inputs produce different hashes."""
        item_a = {"objetoCompra": "Item A", "valorTotalEstimado": 1000.00}
        item_b = {"objetoCompra": "Item B", "valorTotalEstimado": 2000.00}
        assert tr.compute_content_hash(item_a) != tr.compute_content_hash(item_b)

    def test_case_insensitive_comparison(self):
        """Hash uses lowercase — case differences should produce same hash."""
        item_upper = {"objetoCompra": "SERVICO DE LIMPEZA", "valorTotalEstimado": 100.0}
        item_lower = {"objetoCompra": "servico de limpeza", "valorTotalEstimado": 100.0}
        assert tr.compute_content_hash(item_upper) == tr.compute_content_hash(item_lower)

    def test_missing_fields_default_to_empty(self):
        """Missing fields default to empty string / None gracefully."""
        item: dict = {}
        # Should not raise
        result = tr.compute_content_hash(item)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hexdigest length

    def test_situacao_fallback(self):
        """situacaoCompraNome is tried first, then situacaoCompra, then empty."""
        item_nome = {"situacaoCompraNome": "Ativo", "situacaoCompra": "Antigo"}
        item_short = {"situacaoCompra": "Antigo"}
        item_empty: dict = {}
        hash_nome = tr.compute_content_hash(item_nome)
        hash_short = tr.compute_content_hash(item_short)
        hash_empty = tr.compute_content_hash(item_empty)
        # hash_nome should differ from both
        assert hash_nome != hash_short
        assert hash_nome != hash_empty


# ---------------------------------------------------------------------------
# transform_pncp_item()
# ---------------------------------------------------------------------------


class TestTransformPncpItem:
    """Tests for transform_pncp_item()."""

    def test_happy_path_returns_all_fields(self, sample_pncp_item):
        """transform_pncp_item() returns a dict with all expected fields."""
        result = tr.transform_pncp_item(sample_pncp_item)

        assert result["pncp_id"] == "98765432100001"
        assert result["objeto_compra"] == "Aquisicao de equipamentos de informatica"
        assert result["valor_total_estimado"] == 150000.00
        assert result["modalidade_id"] == 5
        assert result["modalidade_nome"] == "Pregao Eletronico"
        assert result["situacao_compra"] == "Divulgado"
        assert result["esfera_id"] == 3
        assert result["uf"] == "SC"
        assert result["municipio"] == "Florianopolis"
        assert result["codigo_municipio_ibge"] == "4205407"
        assert result["orgao_razao_social"] == "Prefeitura Municipal de Florianopolis"
        assert result["orgao_cnpj"] == "12345678000199"
        assert result["data_publicacao"] == "2026-07-10T10:00:00Z"
        assert result["data_abertura"] == "2026-08-01T09:00:00Z"
        assert result["data_encerramento"] == "2026-08-15T18:00:00Z"
        assert result["link_sistema_origem"] == "https://sistema-origem.example.gov/98765432100001"
        assert result["link_pncp"] == "https://pncp.gov.br/app/editais/98765432100001"
        assert result["source"] == "pncp"
        assert result["crawl_batch_id"] is None
        assert result["raw_payload"] is sample_pncp_item
        assert isinstance(result["content_hash"], str)
        assert len(result["content_hash"]) == 64

    def test_missing_pncp_id_raises_value_error(self):
        """Missing numeroControlePNCP raises ValueError."""
        item = {"objetoCompra": "Item sem ID"}
        with pytest.raises(ValueError, match="numeroControlePNCP"):
            tr.transform_pncp_item(item)

    def test_empty_pncp_id_raises_value_error(self):
        """Empty string numeroControlePNCP raises ValueError."""
        item = {"numeroControlePNCP": ""}
        with pytest.raises(ValueError, match="numeroControlePNCP"):
            tr.transform_pncp_item(item)

    def test_missing_publicacao_uses_fallback(self):
        """Missing dataPublicacaoPncp triggers _date_fallback_iso()."""
        item = {"numeroControlePNCP": "99999999999999"}
        result = tr.transform_pncp_item(item)
        # Should have a valid ISO string
        parsed = datetime.fromisoformat(result["data_publicacao"])
        assert isinstance(parsed, datetime)

    def test_abertura_fallback_to_publicacao(self):
        """When dataAberturaProposta is missing, it mirrors data_publicacao."""
        item = {
            "numeroControlePNCP": "88888888888888",
            "dataPublicacaoPncp": "2026-07-10T10:00:00Z",
        }
        result = tr.transform_pncp_item(item)
        assert result["data_abertura"] == result["data_publicacao"]

    def test_encerramento_none_when_missing(self):
        """Missing dataEncerramentoProposta results in None."""
        item = {"numeroControlePNCP": "77777777777777"}
        result = tr.transform_pncp_item(item)
        assert result["data_encerramento"] is None

    def test_custom_source_and_batch_id(self):
        """Source and crawl_batch_id parameters are propagated."""
        item = {"numeroControlePNCP": "66666666666666"}
        result = tr.transform_pncp_item(item, source="test-source", crawl_batch_id="batch-001")
        assert result["source"] == "test-source"
        assert result["crawl_batch_id"] == "batch-001"

    def test_modalidade_fallback_fields(self):
        """modalidadeId falls back to codigoModalidadeContratacao."""
        item = {
            "numeroControlePNCP": "55555555555555",
            "codigoModalidadeContratacao": 3,
            "modalidadeNome": "Concorrencia",
        }
        result = tr.transform_pncp_item(item)
        assert result["modalidade_id"] == 3
        assert result["modalidade_nome"] == "Concorrencia"

    def test_geography_from_unidade(self):
        """Geography fields from unidadeOrgao take precedence."""
        item = {
            "numeroControlePNCP": "44444444444444",
            "unidadeOrgao": {
                "ufSigla": "SC",
                "municipioNome": "Sao Jose",
                "codigoMunicipioIbge": "4205400",
            },
            "uf": "PR",  # Should be overridden by unidade
        }
        result = tr.transform_pncp_item(item)
        assert result["uf"] == "SC"
        assert result["municipio"] == "Sao Jose"
        assert result["codigo_municipio_ibge"] == "4205400"

    def test_geography_fallback_to_root(self):
        """Geography falls back to root-level fields when unidadeOrgao missing."""
        item = {
            "numeroControlePNCP": "33333333333333",
            "uf": "RS",
            "municipioNome": "Porto Alegre",
            "codigoMunicipioIbge": "4314902",
        }
        result = tr.transform_pncp_item(item)
        assert result["uf"] == "RS"
        assert result["municipio"] == "Porto Alegre"
        assert result["codigo_municipio_ibge"] == "4314902"

    def test_content_hash_computed(self):
        """content_hash is computed from objetoCompra, valor, situacao."""
        item = {
            "numeroControlePNCP": "22222222222222",
            "objetoCompra": "Contratacao de servico",
            "valorTotalEstimado": 99999.99,
            "situacaoCompraNome": "Publicado",
        }
        result = tr.transform_pncp_item(item)
        expected_hash = tr.compute_content_hash(item)
        assert result["content_hash"] == expected_hash

    def test_unidade_nome(self):
        """unidade_nome is populated from unidadeOrgao.nomeUnidade."""
        item = {
            "numeroControlePNCP": "11111111111111",
            "unidadeOrgao": {"nomeUnidade": "Departamento de Compras"},
        }
        result = tr.transform_pncp_item(item)
        assert result["unidade_nome"] == "Departamento de Compras"

    def test_esfera_id_from_orgao(self):
        """esferaId is extracted from orgaoEntidade when present."""
        item = {
            "numeroControlePNCP": "10101010101010",
            "orgaoEntidade": {"esferaId": 2},
        }
        result = tr.transform_pncp_item(item)
        assert result["esfera_id"] == 2

    def test_esfera_none_when_missing(self):
        """esfera_id is None when not provided."""
        item = {"numeroControlePNCP": "20202020202020"}
        result = tr.transform_pncp_item(item)
        assert result["esfera_id"] is None or result["esfera_id"] == ""


# ---------------------------------------------------------------------------
# transform_batch()
# ---------------------------------------------------------------------------


class TestTransformBatch:
    """Tests for transform_batch()."""

    def test_empty_list_returns_empty(self):
        """transform_batch([]) returns an empty list."""
        result = tr.transform_batch([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_single_item(self, sample_pncp_item):
        """transform_batch() transforms a single valid item."""
        result = tr.transform_batch([sample_pncp_item])
        assert len(result) == 1
        assert result[0]["pncp_id"] == "98765432100001"

    def test_multiple_items(self, sample_pncp_item):
        """transform_batch() transforms multiple valid items."""
        items = [sample_pncp_item, dict(sample_pncp_item, numeroControlePNCP="11111111111111")]
        result = tr.transform_batch(items)
        assert len(result) == 2

    def test_skips_invalid_items_gracefully(self):
        """transform_batch() skips items that fail validation (missing pncp_id)."""
        items = [
            {"numeroControlePNCP": "12345678901234", "objetoCompra": "Item valido"},
            {"objetoCompra": "Item invalido sem ID"},  # Should be skipped
            {"numeroControlePNCP": "56789012345678", "objetoCompra": "Outro valido"},
        ]
        result = tr.transform_batch(items)
        assert len(result) == 2
        assert result[0]["pncp_id"] == "12345678901234"
        assert result[1]["pncp_id"] == "56789012345678"

    def test_all_invalid_returns_empty(self):
        """transform_batch() returns empty list when all items are invalid."""
        items = [
            {"objetoCompra": "Item 1 sem ID"},
            {"objetoCompra": "Item 2 sem ID"},
        ]
        result = tr.transform_batch(items)
        assert len(result) == 0

    def test_preserves_source_and_batch_id(self):
        """transform_batch() propagates source and crawl_batch_id."""
        items = [{"numeroControlePNCP": "99999999999999"}]
        result = tr.transform_batch(items, source="custom", crawl_batch_id="batch-999")
        assert result[0]["source"] == "custom"
        assert result[0]["crawl_batch_id"] == "batch-999"


# ---------------------------------------------------------------------------
# Empty / boundary fields
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    """Edge cases and boundary conditions for transform functions."""

    def test_none_valor(self):
        """None valorTotalEstimado is handled without raising."""
        item = {
            "numeroControlePNCP": "00000000000000",
            "objetoCompra": "Item com valor None",
            "valorTotalEstimado": None,
            "situacaoCompraNome": None,
        }
        result = tr.transform_pncp_item(item)
        assert result["valor_total_estimado"] is None

    def test_orgao_cnpj_empty_when_missing(self):
        """orgao_cnpj is empty string when no CNPJ data available."""
        item = {"numeroControlePNCP": "99999999999998"}
        result = tr.transform_pncp_item(item)
        assert result["orgao_cnpj"] == ""

    def test_orgao_razao_social_fallback_chain(self):
        """orgao_razao_social falls through orgao → unidade → root."""
        # Fallback to unidade
        item_unidade = {
            "numeroControlePNCP": "88888888888887",
            "unidadeOrgao": {"nomeUnidade": "Unidade Via Unidade"},
        }
        assert tr.transform_pncp_item(item_unidade)["orgao_razao_social"] == "Unidade Via Unidade"

        # Fallback to root
        item_root = {
            "numeroControlePNCP": "77777777777776",
            "razaoSocial": "Orgao Via Root",
        }
        assert tr.transform_pncp_item(item_root)["orgao_razao_social"] == "Orgao Via Root"

        # Empty when nothing available
        item_empty = {"numeroControlePNCP": "66666666666665"}
        assert tr.transform_pncp_item(item_empty)["orgao_razao_social"] == ""
