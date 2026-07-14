"""Unit tests for scripts/crawl/pcp_crawler.py."""

from unittest.mock import patch

from scripts.crawl import pcp_crawler as pcp

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_RECORD = {
    "codigoLicitacao": "12345",
    "resumo": "Contratacao de servico de limpeza",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Prefeitura Municipal de Florianopolis",
        "CNPJ": "12345678000199",
        "cidade": "Florianopolis",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-15T10:00:00Z",
    "dataHoraInicioPropostas": "2025-07-01T08:00:00Z",
    "dataHoraFinalPropostas": "2025-07-15T18:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Pregao Eletronico",
    },
}

MOCK_RECORD_MUNICIPAL = {
    "codigoLicitacao": "67890",
    "resumo": "Aquisicao de equipamentos",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Camara Municipal de Sao Jose",
        "CNPJ": "98765432000188",
        "cidade": "Sao Jose",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-20T14:30:00Z",
    "dataHoraInicioPropostas": "2025-07-05T09:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Concorrencia",
    },
}

MOCK_RECORD_ESTADUAL = {
    "codigoLicitacao": "11111",
    "resumo": "Obra de infraestrutura rodoviaria",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "DEINFRA - Departamento de Infraestrutura",
        "CNPJ": "55555555000155",
        "cidade": "Florianopolis",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-25T10:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Tomada de Precos",
    },
}

MOCK_RECORD_NO_CNPJ = {
    "codigoLicitacao": "22222",
    "resumo": "Servico sem CNPJ",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Orgao Sem CNPJ",
        "CNPJ": "",
        "cidade": "Palhoca",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-30T10:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Dispensa de Licitação",
    },
}

# ---------------------------------------------------------------------------
# crawl()
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl()."""

    @patch("scripts.crawl.pcp_crawler._fetch_page", return_value=([], False))
    def test_crawl_incremental_returns_list(self, mock_fetch):
        """crawl('incremental') returns a list even when API returns no data."""
        result = pcp.crawl(mode="incremental")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns an empty list."""
        result = pcp.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_transform_mock_record(self):
        """transform() normalizes a PCP v2 record with all 16 fields."""
        result = pcp.transform([MOCK_RECORD])
        assert len(result) == 1

        record = result[0]

        # Verify all pncp_raw_bids fields are present
        assert record["pncp_id"] == "pcp_12345"
        assert record["objeto_compra"] == "Contratacao de servico de limpeza"
        assert record["valor_total_estimado"] is None  # v2 listing does not include value
        assert record["modalidade_id"] == 5  # Pregao Eletronico
        assert record["modalidade_nome"] == "Pregao Eletronico"
        assert record["esfera_id"] == 3  # Municipal
        assert record["uf"] == "SC"
        assert record["municipio"] == "Florianopolis"
        assert record["codigo_municipio_ibge"] == ""  # PCP v2 does not provide IBGE code
        assert record["orgao_razao_social"] == "Prefeitura Municipal de Florianopolis"
        assert record["orgao_cnpj"] == "12345678000199"
        assert record["data_publicacao"] == "2025-06-15"
        assert record["data_abertura"] == "2025-07-01"
        assert record["data_encerramento"] == "2025-07-15"
        assert record["link_pncp"] is not None
        assert record["content_hash"] is not None

        # Count total fields (16 campos)
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
        }
        assert set(record.keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(record.keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(record.keys())}"
        )

    def test_transform_dedup(self):
        """transform() keeps records with the same pncp_id (DB-level dedup).

        PCP v2 transform does NOT deduplicate in-memory — dedup is handled
        by upsert_pncp_raw_bids at the database level. This test verifies
        that transform preserves both records with the same pncp_id.
        """
        result = pcp.transform([MOCK_RECORD, MOCK_RECORD])
        assert len(result) == 2, f"Expected 2 records (no in-memory dedup), got {len(result)}"


# ---------------------------------------------------------------------------
# modalidade mapping
# ---------------------------------------------------------------------------


class TestModalidadeMapping:
    """Tests for _map_modalidade()."""

    def test_pregao_eletronico(self):
        """Pregao Eletronico maps to modalidade_id=5."""
        mid, name = pcp._map_modalidade("Pregao Eletronico")
        assert mid == 5
        assert name == "Pregao Eletronico"

    def test_pregao_presencial(self):
        """Pregao Presencial maps to modalidade_id=6."""
        mid, name = pcp._map_modalidade("Pregao Presencial")
        assert mid == 6

    def test_concorrencia(self):
        """Concorrencia maps to modalidade_id=4."""
        mid, name = pcp._map_modalidade("Concorrencia")
        assert mid == 4

    def test_concorrencia_antiga(self):
        """Concorrencia Antiga maps to modalidade_id=1."""
        mid, name = pcp._map_modalidade("Concorrencia Antiga")
        assert mid == 1

    def test_tomada_de_precos(self):
        """Tomada de Precos maps to modalidade_id=2."""
        mid, name = pcp._map_modalidade("Tomada de Precos")
        assert mid == 2

    def test_convite(self):
        """Convite maps to modalidade_id=3."""
        mid, name = pcp._map_modalidade("Convite")
        assert mid == 3

    def test_inexigibilidade(self):
        """Inexigibilidade maps to modalidade_id=8."""
        mid, name = pcp._map_modalidade("Inexigibilidade")
        assert mid == 8

    def test_dispensa_licitacao(self):
        """Dispensa de Licitação maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Dispensa de Licitação")
        assert mid == 7

    def test_dispensa_shorthand(self):
        """'Dispensa' shorthand maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Dispensa")
        assert mid == 7

    def test_leilao(self):
        """Leilao maps to modalidade_id=10."""
        mid, name = pcp._map_modalidade("Leilao")
        assert mid == 10

    def test_contratacao_direta(self):
        """Contratacao Direta maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Contratacao Direta")
        assert mid == 7

    def test_unknown_modalidade(self):
        """Unknown modalidade returns (0, raw)."""
        mid, name = pcp._map_modalidade("Modalidade Desconhecida XYZ")
        assert mid == 0
        assert name == "Modalidade Desconhecida XYZ"

    def test_empty_modalidade(self):
        """Empty modalidade returns (0, '')."""
        mid, name = pcp._map_modalidade("")
        assert mid == 0
        assert name == ""

    def test_modalidade_with_numbering(self):
        """Modalidade with numbering prefix is normalized correctly."""
        mid, name = pcp._map_modalidade("1. Pregao Eletronico")
        assert mid == 5

    def test_modalidade_with_accent(self):
        """Modalidade with accents is normalized correctly."""
        mid, name = pcp._map_modalidade("Pregão Eletrônico")
        assert mid == 5


# ---------------------------------------------------------------------------
# esfera inference
# ---------------------------------------------------------------------------


class TestEsferaInference:
    """Tests for _infer_esfera()."""

    def test_municipal_prefeitura(self):
        """'Prefeitura Municipal de ...' infers esfera_id=3."""
        assert pcp._infer_esfera("Prefeitura Municipal de Florianopolis") == 3

    def test_municipal_camara(self):
        """'Camara Municipal de ...' infers esfera_id=3."""
        assert pcp._infer_esfera("Camara Municipal de Sao Jose") == 3

    def test_estadual_secretaria(self):
        """'Secretaria de Estado de ...' infers esfera_id=2."""
        assert pcp._infer_esfera("Secretaria de Estado da Saude") == 2

    def test_estadual_deinfra(self):
        """'DEINFRA' infers esfera_id=2."""
        assert pcp._infer_esfera("DEINFRA - Departamento de Infraestrutura") == 2

    def test_federal_ministerio(self):
        """'Ministerio da ...' infers esfera_id=1."""
        assert pcp._infer_esfera("Ministerio da Saude") == 1

    def test_federal_universidade(self):
        """'Universidade Federal ...' infers esfera_id=1."""
        assert pcp._infer_esfera("Universidade Federal do Rio Grande do Sul") == 1

    def test_estadual_udesc(self):
        """'UDESC' infers esfera_id=2."""
        assert pcp._infer_esfera("UDESC - Universidade do Estado") == 2

    def test_default_municipal(self):
        """Unknown organization defaults to esfera_id=3."""
        assert pcp._infer_esfera("Empresa Privada Ltda") == 3

    def test_empty_string(self):
        """Empty string defaults to esfera_id=3."""
        assert pcp._infer_esfera("") == 3
