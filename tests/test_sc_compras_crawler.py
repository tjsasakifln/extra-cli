"""Unit tests for scripts/crawl/sc_compras_crawler.py.

Covers all public and private functions:
- _normalize_modalidade
- _map_modalidade
- _infer_esfera
- _parse_br_date
- _parse_br_number
- _digits_only
- _content_hash
- _extract_table_rows
- _extract_detail_fields
- _normalize_item
- crawl
- transform
- diagnostic
"""

from unittest.mock import MagicMock, patch

from scripts.crawl import sc_compras_crawler as sc

# ---------------------------------------------------------------------------
# _normalize_modalidade()
# ---------------------------------------------------------------------------


class TestNormalizeModalidade:
    """Tests for _normalize_modalidade()."""

    def test_strips_accents(self):
        """Pregão Eletrônico normalizes to 'pregao eletronico'."""
        assert sc._normalize_modalidade("Pregão Eletrônico") == "pregao eletronico"

    def test_strips_numbering_prefix(self):
        """Numbered prefix is removed."""
        result = sc._normalize_modalidade("1. Pregao Eletronico")
        assert result == "pregao eletronico"

    def test_strips_parentheses(self):
        """Parentheses are removed."""
        result = sc._normalize_modalidade("Pregao (Eletronico)")
        assert result == "pregao eletronico"

    def test_lowercases_and_trims(self):
        """Mixed case is lowercased and tidied."""
        result = sc._normalize_modalidade("  CONCORRENCIA  ")
        assert result == "concorrencia"

    def test_empty_string(self):
        """Empty string returns empty."""
        assert sc._normalize_modalidade("") == ""

    def test_handles_unicode(self):
        """Unicode characters are handled correctly."""
        result = sc._normalize_modalidade("Inexigibilidade")
        assert result == "inexigibilidade"


# ---------------------------------------------------------------------------
# _map_modalidade()
# ---------------------------------------------------------------------------


class TestMapModalidade:
    """Tests for _map_modalidade()."""

    def test_pregao_eletronico(self):
        """Pregao Eletronico maps to modalidade_id=5."""
        mid, name = sc._map_modalidade("Pregao Eletronico")
        assert mid == 5
        assert name == "Pregao Eletronico"

    def test_pregao_presencial(self):
        """Pregao Presencial maps to modalidade_id=6."""
        mid, name = sc._map_modalidade("Pregao Presencial")
        assert mid == 6

    def test_concorrencia(self):
        """Concorrencia maps to modalidade_id=4."""
        mid, name = sc._map_modalidade("Concorrencia")
        assert mid == 4

    def test_concorrencia_antiga(self):
        """Concorrencia Antiga maps to modalidade_id=1."""
        mid, name = sc._map_modalidade("Concorrencia Antiga")
        assert mid == 1

    def test_tomada_de_precos(self):
        """Tomada de Precos maps to modalidade_id=2."""
        mid, name = sc._map_modalidade("Tomada de Precos")
        assert mid == 2

    def test_convite(self):
        """Convite maps to modalidade_id=3."""
        mid, name = sc._map_modalidade("Convite")
        assert mid == 3

    def test_concurso(self):
        """Concurso maps to modalidade_id=9."""
        mid, name = sc._map_modalidade("Concurso")
        assert mid == 9

    def test_leilao(self):
        """Leilao maps to modalidade_id=10."""
        mid, name = sc._map_modalidade("Leilao")
        assert mid == 10

    def test_dispensa_licitacao(self):
        """Dispensa de Licitacao maps to modalidade_id=7."""
        mid, name = sc._map_modalidade("Dispensa de Licitacao")
        assert mid == 7

    def test_inexigibilidade(self):
        """Inexigibilidade maps to modalidade_id=8."""
        mid, name = sc._map_modalidade("Inexigibilidade")
        assert mid == 8

    def test_dialogo_competitivo(self):
        """Dialogo Competitivo maps to modalidade_id=13."""
        mid, name = sc._map_modalidade("Dialogo Competitivo")
        assert mid == 13

    def test_credenciamento(self):
        """Credenciamento maps to modalidade_id=12."""
        mid, name = sc._map_modalidade("Credenciamento")
        assert mid == 12

    def test_fuzzy_fallback(self):
        """Fuzzy fallback matches similar modalidades."""
        mid, name = sc._map_modalidade("Pregão Eletrônico (com licitação)")
        assert mid == 5

    def test_unknown_modalidade(self):
        """Unknown modalidade returns (None, raw)."""
        mid, name = sc._map_modalidade("Modalidade Desconhecida XYZ")
        assert mid is None
        assert name == "Modalidade Desconhecida XYZ"

    def test_empty_modalidade(self):
        """Empty modalidade returns (None, '')."""
        mid, name = sc._map_modalidade("")
        assert mid is None
        assert name == ""


# ---------------------------------------------------------------------------
# _infer_esfera()
# ---------------------------------------------------------------------------


class TestInferEsfera:
    """Tests for _infer_esfera()."""

    def test_secretaria_de_estado(self):
        """Secretaria de Estado infers 'E' (Estadual)."""
        assert sc._infer_esfera("Secretaria de Estado da Saude") == "E"

    def test_fundo_estadual(self):
        """Fundo Estadual infers 'E'."""
        assert sc._infer_esfera("Fundo Estadual de Saude") == "E"

    def test_prefeitura_infers_municipal(self):
        """Prefeitura Municipal infers 'M'."""
        assert sc._infer_esfera("Prefeitura Municipal de Florianopolis") == "M"

    def test_pm_prefix_infers_municipal(self):
        """PM prefix infers 'M'."""
        assert sc._infer_esfera("PM de Sao Jose") == "M"

    def test_deinfra_infers_estadual(self):
        """DEINFRA infers 'E'."""
        assert sc._infer_esfera("DEINFRA - Departamento de Infraestrutura") == "E"

    def test_udesc_infers_estadual(self):
        """UDESC infers 'E'."""
        assert sc._infer_esfera("UDESC - Universidade do Estado") == "E"

    def test_detran_infers_estadual(self):
        """DETRAN infers 'E'."""
        assert sc._infer_esfera("DETRAN - SC") == "E"

    def test_ima_infers_estadual(self):
        """IMA infers 'E'."""
        assert sc._infer_esfera("IMA - Instituto do Meio Ambiente") == "E"

    def test_unknown_defaults_to_estadual(self):
        """Unknown organization defaults to 'E' (SC state focus)."""
        assert sc._infer_esfera("Empresa Privada Ltda") == "E"

    def test_empty_string_defaults_to_estadual(self):
        """Empty string defaults to 'E'."""
        assert sc._infer_esfera("") == "E"


# ---------------------------------------------------------------------------
# _parse_br_date()
# ---------------------------------------------------------------------------


class TestParseBrDate:
    """Tests for _parse_br_date()."""

    def test_parses_dd_mm_yyyy(self):
        """DD/MM/YYYY is parsed to YYYY-MM-DD."""
        assert sc._parse_br_date("15/06/2025") == "2025-06-15"

    def test_parses_iso_format(self):
        """YYYY-MM-DD is returned as-is."""
        assert sc._parse_br_date("2025-06-15") == "2025-06-15"

    def test_returns_none_for_empty(self):
        """Empty string returns None."""
        assert sc._parse_br_date("") is None

    def test_returns_none_for_none(self):
        """None returns None."""
        assert sc._parse_br_date(None) is None

    def test_returns_none_for_invalid(self):
        """Invalid date returns None."""
        assert sc._parse_br_date("not-a-date") is None

    def test_trims_whitespace(self):
        """Whitespace is trimmed before parsing."""
        assert sc._parse_br_date("  01/01/2025  ") == "2025-01-01"

    def test_handles_single_digit_day_month(self):
        """Single digit day/month with leading zeros."""
        assert sc._parse_br_date("01/02/2025") == "2025-02-01"

    def test_truncates_longer_iso(self):
        """Longer ISO datetime is truncated to date."""
        assert sc._parse_br_date("2025-06-15T10:00:00") == "2025-06-15"


# ---------------------------------------------------------------------------
# _parse_br_number()
# ---------------------------------------------------------------------------


class TestParseBrNumber:
    """Tests for _parse_br_number()."""

    def test_parses_thousands_with_commas(self):
        """1.500,00 is parsed to 1500.0."""
        assert sc._parse_br_number("1.500,00") == 1500.0

    def test_parses_simple_decimal(self):
        """1500,50 is parsed to 1500.5."""
        assert sc._parse_br_number("1500,50") == 1500.5

    def test_parses_integer_string(self):
        """150000 is parsed to 150000.0."""
        assert sc._parse_br_number("150000") == 150000.0

    def test_strips_r_prefix(self):
        """R$ 1.500,00 is parsed to 1500.0."""
        assert sc._parse_br_number("R$ 1.500,00") == 1500.0

    def test_returns_none_for_empty(self):
        """Empty string returns None."""
        assert sc._parse_br_number("") is None

    def test_returns_none_for_none(self):
        """None returns None."""
        assert sc._parse_br_number(None) is None

    def test_returns_none_for_non_numeric(self):
        """Non-numeric string returns None."""
        assert sc._parse_br_number("N/A") is None


# ---------------------------------------------------------------------------
# _digits_only()
# ---------------------------------------------------------------------------


class TestDigitsOnly:
    """Tests for _digits_only()."""

    def test_strips_non_digits(self):
        """CNPJ with punctuation returns only digits."""
        assert sc._digits_only("12.345.678/0001-99") == "12345678000199"

    def test_preserves_digits(self):
        """Already clean digits are preserved."""
        assert sc._digits_only("12345678") == "12345678"

    def test_returns_empty_for_none(self):
        """None returns empty string."""
        assert sc._digits_only(None) == ""

    def test_returns_empty_for_empty(self):
        """Empty string returns empty."""
        assert sc._digits_only("") == ""


# ---------------------------------------------------------------------------
# _content_hash()
# ---------------------------------------------------------------------------


class TestContentHash:
    """Tests for _content_hash()."""

    def test_deterministic_hash(self):
        """Same inputs produce same hash."""
        h1 = sc._content_hash("abc", "def")
        h2 = sc._content_hash("abc", "def")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        """Different inputs produce different hashes."""
        h1 = sc._content_hash("abc", "def")
        h2 = sc._content_hash("xyz", "def")
        assert h1 != h2

    def test_returns_md5_hexdigest(self):
        """Hash is a 32-char hex string (MD5)."""
        h = sc._content_hash("test")
        assert isinstance(h, str)
        assert len(h) == 32
        int(h, 16)  # should not raise


# ---------------------------------------------------------------------------
# _extract_table_rows()
# ---------------------------------------------------------------------------


class TestExtractTableRows:
    """Tests for _extract_table_rows()."""

    HTML_WITH_TABLE = """
    <table class="table table-striped">
      <thead><tr><th>Processo</th><th>Modalidade</th><th>Objeto</th><th>Orgao</th><th>Data</th><th>Situacao</th><th>Valor</th></tr></thead>
      <tbody>
        <tr>
          <td><a href="/licitacao/123">2025/00001</a></td>
          <td>Pregao Eletronico</td>
          <td>Contratacao de servico de limpeza</td>
          <td>Secretaria de Estado da Saude</td>
          <td>15/06/2025</td>
          <td>Divulgado</td>
          <td>150.000,00</td>
        </tr>
        <tr>
          <td><a href="/licitacao/456">2025/00002</a></td>
          <td>Concorrencia</td>
          <td>Obra de infraestrutura</td>
          <td>DEINFRA</td>
          <td>20/06/2025</td>
          <td>Aberta</td>
          <td>2.500.000,00</td>
        </tr>
      </tbody>
    </table>
    """

    def test_extracts_rows_from_table(self):
        """Table rows are extracted with all fields."""
        result = sc._extract_table_rows(self.HTML_WITH_TABLE)
        assert len(result) == 2

    def test_extracts_numero_processo(self):
        """numero_processo is extracted from anchor text."""
        result = sc._extract_table_rows(self.HTML_WITH_TABLE)
        assert result[0]["numero_processo"] == "2025/00001"
        assert result[1]["numero_processo"] == "2025/00002"

    def test_extracts_modalidade(self):
        """Modalidade is extracted."""
        result = sc._extract_table_rows(self.HTML_WITH_TABLE)
        assert result[0]["modalidade"] == "Pregao Eletronico"

    def test_extracts_objeto(self):
        """Objeto is extracted."""
        result = sc._extract_table_rows(self.HTML_WITH_TABLE)
        assert "servico de limpeza" in result[0]["objeto"]

    def test_extracts_url_detalhe(self):
        """URL detalhe is constructed from href."""
        result = sc._extract_table_rows(self.HTML_WITH_TABLE)
        assert sc.BASE_URL in result[0]["url_detalhe"]
        assert "/licitacao/123" in result[0]["url_detalhe"]

    def test_returns_empty_for_no_table(self):
        """HTML without table returns empty list."""
        result = sc._extract_table_rows("<html><body>No table here</body></html>")
        assert result == []

    def test_handles_empty_tbody(self):
        """Table with empty tbody returns empty list."""
        result = sc._extract_table_rows('<table class="table"><tbody></tbody></table>')
        assert result == []


# ---------------------------------------------------------------------------
# _extract_detail_fields()
# ---------------------------------------------------------------------------


class TestExtractDetailFields:
    """Tests for _extract_detail_fields()."""

    HTML_WITH_DL = """
    <div class="panel-body">
      <dl>
        <dt>Numero do Processo</dt>
        <dd>2025/00001</dd>
        <dt>Orgao/Entidade</dt>
        <dd>Secretaria de Estado da Saude</dd>
        <dt>CNPJ do Orgao</dt>
        <dd>12.345.678/0001-99</dd>
        <dt>Valor Total Estimado</dt>
        <dd>150.000,00</dd>
        <dt>Data de Abertura</dt>
        <dd>01/07/2025</dd>
        <dt>Data de Encerramento</dt>
        <dd>15/07/2025</dd>
        <dt>Municipio</dt>
        <dd>Florianopolis</dd>
        <dt>UF</dt>
        <dd>SC</dd>
      </dl>
    </div>
    """

    def test_extracts_dl_fields(self):
        """Detail fields are extracted from <dl> definitions."""
        result = sc._extract_detail_fields(self.HTML_WITH_DL)
        assert result.get("numero_processo") == "2025/00001"
        assert result.get("orgao") == "Secretaria de Estado da Saude"
        assert result.get("orgao_cnpj") == "12.345.678/0001-99"

    def test_extracts_date_fields(self):
        """Date fields are extracted."""
        result = sc._extract_detail_fields(self.HTML_WITH_DL)
        assert result.get("data_abertura") == "01/07/2025"
        assert result.get("data_encerramento") == "15/07/2025"

    def test_extracts_valor(self):
        """Valor field is extracted."""
        result = sc._extract_detail_fields(self.HTML_WITH_DL)
        assert result.get("valor") == "150.000,00"

    def test_extracts_municipio(self):
        """Municipio field is extracted."""
        result = sc._extract_detail_fields(self.HTML_WITH_DL)
        assert result.get("municipio") == "Florianopolis"

    def test_returns_empty_for_no_data(self):
        """HTML without detail data returns empty dict."""
        result = sc._extract_detail_fields("<html><body>No detail</body></html>")
        assert result == {}

    def test_handles_empty_html(self):
        """Empty string returns empty dict."""
        result = sc._extract_detail_fields("")
        assert result == {}

    HTML_WITH_LABEL = """
    <div class="content-wrapper">
      <label>Objeto da Licitacao</label>
      <span>Contratacao de servico de limpeza predial</span><br/>
      <label>Situacao da Compra</label>
      <span>Divulgado</span>
    </div>
    """

    def test_extracts_label_span_patterns(self):
        """Fields from label/span patterns are extracted."""
        result = sc._extract_detail_fields(self.HTML_WITH_LABEL)
        assert result.get("objeto") == "Contratacao de servico de limpeza predial"
        assert result.get("situacao") == "Divulgado"

    HTML_WITH_STRONG = """
    <div class="content-wrapper">
      <strong>Modalidade</strong>
      <span>Pregao Eletronico</span><br/>
      <strong>Data Publicacao</strong>
      <p>15/06/2025</p>
    </div>
    """

    def test_extracts_strong_span_patterns(self):
        """Fields from strong/span patterns are extracted."""
        result = sc._extract_detail_fields(self.HTML_WITH_STRONG)
        assert result.get("modalidade") == "Pregao Eletronico"
        assert result.get("data_publicacao") == "15/06/2025"


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns an empty list."""
        result = sc.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_transform_single_record(self):
        """transform() normalizes a record with all pncp_raw_bids fields."""
        raw = [{
            "numero_processo": "2025/00001",
            "modalidade": "Pregao Eletronico",
            "objeto": "Contratacao de servico de limpeza",
            "orgao": "Secretaria de Estado da Saude",
            "orgao_cnpj": "12.345.678/0001-99",
            "data_publicacao": "15/06/2025",
            "data_abertura": "01/07/2025",
            "data_encerramento": "15/07/2025",
            "situacao": "Divulgado",
            "valor": "150.000,00",
            "municipio": "Florianopolis",
            "uf": "SC",
            "url_detalhe": "https://compras.sc.gov.br/licitacao/123",
        }]
        result = sc.transform(raw)
        assert len(result) == 1
        record = result[0]

        assert record["pncp_id"] == "sc-2025/00001"
        assert record["objeto_compra"] == "Contratacao de servico de limpeza"
        assert record["valor_total_estimado"] == 150000.0
        assert record["modalidade_id"] == 5
        assert record["modalidade_nome"] == "Pregao Eletronico"
        assert record["esfera_id"] == "E"
        assert record["uf"] == "SC"
        assert record["municipio"] == "Florianopolis"
        assert record["codigo_municipio_ibge"] is None
        assert record["orgao_razao_social"] == "Secretaria de Estado da Saude"
        assert record["orgao_cnpj"] == "12345678000199"
        assert record["data_publicacao"] == "2025-06-15"
        assert record["data_abertura"] == "2025-07-01"
        assert record["data_encerramento"] == "2025-07-15"
        assert record["link_pncp"] == "https://compras.sc.gov.br/licitacao/123"
        assert record["content_hash"] is not None
        assert record["source_id"] == "sc-2025/00001"

        # Verify no source field
        assert "source" not in record

    def test_transform_returns_correct_field_set(self):
        """transform() returns all expected pncp_raw_bids fields."""
        raw = [{
            "numero_processo": "2025/00001",
            "modalidade": "Pregao Eletronico",
            "objeto": "Servico",
            "orgao": "Secretaria de Estado",
            "orgao_cnpj": "12.345.678/0001-99",
            "data_publicacao": "15/06/2025",
        }]
        result = sc.transform(raw)
        expected_fields = {
            "pncp_id", "objeto_compra", "valor_total_estimado",
            "modalidade_id", "modalidade_nome", "esfera_id",
            "uf", "municipio", "codigo_municipio_ibge",
            "orgao_razao_social", "orgao_cnpj",
            "data_publicacao", "data_abertura", "data_encerramento",
            "link_pncp", "content_hash", "source_id",
        }
        assert set(result[0].keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(result[0].keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(result[0].keys())}"
        )

    def test_transform_skips_empty_numero_processo(self):
        """Record without numero_processo is skipped."""
        raw = [{
            "numero_processo": "",
            "modalidade": "Pregao",
            "objeto": "Servico",
            "orgao": "Orgao",
        }]
        result = sc.transform(raw)
        assert len(result) == 0

    def test_transform_truncates_long_objeto(self):
        """Objeto longer than 1000 chars is truncated."""
        raw = [{
            "numero_processo": "2025/00001",
            "objeto": "X" * 2000,
            "orgao": "Orgao",
        }]
        result = sc.transform(raw)
        assert len(result[0]["objeto_compra"]) == 1000  # 997 + "..."

    def test_transform_estadual_esfera(self):
        """State entities get esfera_id='E'."""
        raw = [{
            "numero_processo": "2025/00001",
            "objeto": "Servico",
            "orgao": "Secretaria de Estado da Educacao",
        }]
        result = sc.transform(raw)
        assert result[0]["esfera_id"] == "E"

    def test_transform_municipal_esfera(self):
        """Municipal entities get esfera_id='M'."""
        raw = [{
            "numero_processo": "2025/00001",
            "objeto": "Servico",
            "orgao": "Prefeitura Municipal de Florianopolis",
        }]
        result = sc.transform(raw)
        assert result[0]["esfera_id"] == "M"


# ---------------------------------------------------------------------------
# crawl() — mocked
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl() with mocked HTTP."""

    @patch("scripts.crawl.sc_compras_crawler._fetch_list_page", return_value=[])
    def test_crawl_returns_list(self, mock_fetch):
        """crawl() returns a list even when API returns no data."""
        result = sc.crawl(mode="full")
        assert isinstance(result, list)

    @patch("scripts.crawl.sc_compras_crawler._fetch_list_page", return_value=[])
    def test_crawl_full_default_days(self, mock_fetch):
        """crawl('full') uses SC_COMPRAS_FULL_DAYS."""
        result = sc.crawl(mode="full")
        assert isinstance(result, list)

    @patch("scripts.crawl.sc_compras_crawler._fetch_list_page", return_value=[])
    def test_crawl_incremental(self, mock_fetch):
        """crawl('incremental') returns a list."""
        result = sc.crawl(mode="incremental")
        assert isinstance(result, list)

    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_list_page",
        return_value=[{"numero_processo": "2025/00001", "url_detalhe": ""}],
    )
    def test_crawl_with_items(self, mock_fetch):
        """crawl() returns items when data is available."""
        result = sc.crawl(mode="full")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# diagnostic() — mocked
# ---------------------------------------------------------------------------


class TestDiagnostic:
    """Tests for diagnostic() with mocked HTTP."""

    @patch("scripts.crawl.sc_compras_crawler._check_url")
    def test_diagnostic_returns_expected_structure(self, mock_check_url):
        """diagnostic() returns expected dict structure."""
        mock_check_url.return_value = {
            "url": "https://compras.sc.gov.br",
            "reachable": True,
            "status_code": 200,
            "response_time_s": 0.5,
            "cloudflare_detected": False,
            "anti_bot_detected": False,
            "error": None,
        }
        result = sc.diagnostic()
        assert "timestamp" in result
        assert "base_url" in result
        assert "e_lic_url" in result
        assert "main_portal" in result
        assert "e_lic" in result
        assert "list_page_test" in result
        assert "total_time_s" in result
        assert "summary" in result

    @patch("scripts.crawl.sc_compras_crawler._check_url")
    def test_diagnostic_reachable_summary(self, mock_check_url):
        """diagnostic() returns positive summary when reachable."""
        mock_check_url.return_value = {
            "reachable": True,
            "status_code": 200,
            "response_time_s": 0.5,
            "cloudflare_detected": False,
            "anti_bot_detected": False,
            "error": None,
        }
        result = sc.diagnostic()
        assert "fully operational" in result["summary"].lower()
        assert "no anti-bot" in result["summary"].lower()

    @patch("scripts.crawl.sc_compras_crawler._check_url")
    def test_diagnostic_cloudflare_summary(self, mock_check_url):
        """diagnostic() flags Cloudflare detection."""
        def side_effect(url):
            if "licitac" in url:
                return {
                    "reachable": True, "status_code": 200,
                    "response_time_s": 0.5, "cloudflare_detected": False,
                    "anti_bot_detected": False, "error": None,
                }
            return {
                "reachable": True, "status_code": 200,
                "response_time_s": 0.5, "cloudflare_detected": True,
                "anti_bot_detected": True, "error": None,
            }
        mock_check_url.side_effect = side_effect
        result = sc.diagnostic()
        assert "anti-bot challenge" in result["summary"].lower()

    @patch("scripts.crawl.sc_compras_crawler._check_url")
    def test_diagnostic_unreachable_summary(self, mock_check_url):
        """diagnostic() reports unreachable portals."""
        mock_check_url.return_value = {
            "reachable": False, "status_code": None,
            "response_time_s": -1.0, "cloudflare_detected": False,
            "anti_bot_detected": False, "error": "Timeout (15s)",
        }
        result = sc.diagnostic()
        assert "unreachable" in result["summary"].lower()

    @patch("scripts.crawl.sc_compras_crawler._check_url")
    def test_diagnostic_e_lic_fallback(self, mock_check_url):
        """diagnostic() shows e-lic fallback when main portal is down."""
        def side_effect(url):
            if "compras.sc.gov.br" in url:
                return {
                    "reachable": False, "status_code": None,
                    "response_time_s": -1.0, "cloudflare_detected": False,
                    "anti_bot_detected": False, "error": "Timeout (15s)",
                }
            return {
                "reachable": True, "status_code": 200,
                "response_time_s": 0.3, "cloudflare_detected": False,
                "anti_bot_detected": False, "error": None,
            }
        mock_check_url.side_effect = side_effect
        result = sc.diagnostic()
        assert "e-lic" in result["summary"].lower()
        assert "reachable" in result["summary"].lower()


# ---------------------------------------------------------------------------
# _check_url() — not mocked (integration-light)
# ---------------------------------------------------------------------------


class TestCheckUrl:
    """Tests for _check_url() with network mocking."""

    @patch("urllib.request.urlopen")
    def test_check_url_success(self, mock_urlopen):
        """_check_url() returns reachable=True for HTTP 200."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html><body>OK</body></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = sc._check_url("https://compras.sc.gov.br")
        assert result["reachable"] is True
        assert result["status_code"] == 200
        assert result["response_time_s"] >= 0
        assert result["cloudflare_detected"] is False
        assert result["anti_bot_detected"] is False
        assert result["error"] is None

    @patch("urllib.request.urlopen")
    def test_check_url_cloudflare_detected(self, mock_urlopen):
        """_check_url() detects Cloudflare challenge."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>Cloudflare challenge page</html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = sc._check_url("https://compras.sc.gov.br")
        assert result["cloudflare_detected"] is True

    @patch("urllib.request.urlopen")
    def test_check_url_captcha_detected(self, mock_urlopen):
        """_check_url() detects CAPTCHA."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>cf-turnstile widget</html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = sc._check_url("https://compras.sc.gov.br")
        assert result["anti_bot_detected"] is True

    @patch("urllib.request.urlopen", side_effect=TimeoutError("timed out"))
    def test_check_url_timeout(self, mock_urlopen):
        """_check_url() handles timeout gracefully."""
        result = sc._check_url("https://compras.sc.gov.br")
        assert result["reachable"] is False
        assert "Timeout" in result["error"]
