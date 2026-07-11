"""Unit tests for scripts/crawl/transparencia_crawler.py and templates.

Cobre ~1380 linhas de producao distribuidos em:
  - transparencia_crawler.py (detect_platform, transform, _parse_valor,
    _parse_date, _slugify, load_config, _fetch_url, _head_url, etc.)
  - transparencia_templates/base.py (extract_text, extract_link,
    make_record, parse_table_rows, parse_div_list)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from scripts.crawl import transparencia_crawler as tc
from scripts.crawl.transparencia_templates import base as tmpl_base

# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for _slugify()."""

    def test_basic(self):
        """Simple name without accents."""
        assert tc._slugify("Blumenau") == "blumenau"

    def test_with_accents(self):
        """Name with accents is normalized."""
        assert tc._slugify("São José") == "sao-jose"

    def test_multiple_words(self):
        """Multiple words joined by hyphens."""
        assert tc._slugify("Balneário Camboriú") == "balneario-camboriu"

    def test_cedilha(self):
        """Cedilha is normalized."""
        assert tc._slugify("Palhoça") == "palhoca"

    def test_leading_trailing_spaces(self):
        """Spaces are stripped."""
        assert tc._slugify("  Chapecó  ") == "chapeco"

    def test_special_chars(self):
        """Special characters replaced with hyphens."""
        assert tc._slugify("São João Batista") == "sao-joao-batista"

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert tc._slugify("") == ""


# ---------------------------------------------------------------------------
# _parse_valor
# ---------------------------------------------------------------------------


class TestParseValor:
    """Tests for _parse_valor()."""

    def test_brl_format(self):
        """R$ 1.234,56 -> 1234.56."""
        assert tc._parse_valor("R$ 1.234,56") == 1234.56

    def test_no_currency(self):
        """1.234,56 -> 1234.56."""
        assert tc._parse_valor("1.234,56") == 1234.56

    def test_integer_value(self):
        """R$ 1.000,00 -> 1000.0."""
        assert tc._parse_valor("R$ 1.000,00") == 1000.0

    def test_small_value(self):
        """R$ 0,50 -> 0.5."""
        assert tc._parse_valor("R$ 0,50") == 0.5

    def test_large_value(self):
        """R$ 1.234.567,89 -> 1234567.89."""
        assert tc._parse_valor("R$ 1.234.567,89") == 1234567.89

    def test_empty_string(self):
        """Empty string returns None."""
        assert tc._parse_valor("") is None

    def test_only_r(self):
        """'R$ ' alone returns None."""
        assert tc._parse_valor("R$ ") is None

    def test_garbage(self):
        """Non-numeric string returns None."""
        assert tc._parse_valor("gratis") is None


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    """Tests for _parse_date()."""

    def test_dd_mm_yyyy(self):
        """DD/MM/YYYY -> YYYY-MM-DD."""
        assert tc._parse_date("15/06/2025") == "2025-06-15"

    def test_dd_mm_yyyy_with_text(self):
        """Date embedded in text."""
        assert tc._parse_date("Publicado em 01/01/2024") == "2024-01-01"

    def test_dd_mm_yyyy_dashes(self):
        """DD-MM-YYYY -> YYYY-MM-DD."""
        assert tc._parse_date("15-06-2025") == "2025-06-15"

    def test_yyyy_mm_dd(self):
        """YYYY-MM-DD stays YYYY-MM-DD."""
        assert tc._parse_date("2025-06-15") == "2025-06-15"

    def test_iso_format(self):
        """ISO datetime returns date portion."""
        assert tc._parse_date("2025-06-15T10:00:00") == "2025-06-15"

    def test_empty_string(self):
        """Empty string returns None."""
        assert tc._parse_date("") is None

    def test_no_date_pattern(self):
        """String with no date pattern returns the string as-is."""
        assert tc._parse_date("indefinido") == "indefinido"


# ---------------------------------------------------------------------------
# detect_platform (with mocked HTTP)
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    """Tests for detect_platform() with mocked HTTP."""

    @patch("scripts.crawl.transparencia_crawler._fetch_url")
    def test_betha(self, mock_fetch):
        """Betha URL pattern (atende.net) detected."""
        mock_fetch.return_value = (200, "<html><body>atende.net transparencia</body></html>")

        result = tc.detect_platform("chapeco", municipio="Chapeco")

        assert result["platform"] == "betha"
        assert result["status"] == "detected"
        assert "atende.net" in result["url"]
        assert result["municipio"] == "Chapeco"

    @patch("scripts.crawl.transparencia_crawler._fetch_url")
    def test_ipam(self, mock_fetch):
        """Ipam URL pattern (ipm.org.br) detected."""
        # Betha and E-gov fail (or timeout), Ipam succeeds
        def side_effect(url, timeout=None):
            if "atende.net" in url:
                return (0, "timeout")
            if "e-gov.betha" in url:
                return (0, "timeout")
            if "ipm.org.br" in url:
                return (200, "<html><body>ipm transparencia</body></html>")
            return (0, "not found")
        mock_fetch.side_effect = side_effect

        result = tc.detect_platform("itajai", municipio="Itajai")

        assert result["platform"] == "ipam"
        assert result["status"] == "detected"
        assert "ipm.org.br" in result["url"]

    @patch("scripts.crawl.transparencia_crawler._fetch_url")
    def test_egov(self, mock_fetch):
        """E-gov URL pattern (e-gov.betha.com.br) detected."""
        def side_effect(url, timeout=None):
            if "atende.net" in url:
                return (0, "timeout")
            if "e-gov.betha" in url:
                return (200, "<html><body>e-gov portal transparencia</body></html>")
            if "ipm.org.br" in url:
                return (0, "timeout")
            return (0, "not found")
        mock_fetch.side_effect = side_effect

        result = tc.detect_platform("florianopolis", municipio="Florianopolis")

        assert result["platform"] == "egov"
        assert result["status"] == "detected"
        assert "e-gov.betha" in result["url"]

    @patch("scripts.crawl.transparencia_crawler._fetch_url")
    def test_not_found(self, mock_fetch):
        """No platform detected returns status 'not_found'."""
        mock_fetch.return_value = (0, "connection refused")

        result = tc.detect_platform("cidade-inexistente", municipio="Cidade Inexistente")

        assert result["status"] == "not_found"
        assert result["platform"] is None

    @patch("scripts.crawl.transparencia_crawler._fetch_url")
    @patch("scripts.crawl.transparencia_crawler._search_portal")
    def test_detect_platform_from_url(self, mock_search, mock_fetch):
        """_detect_platform_from_url correctly identifies platforms."""
        assert tc._detect_platform_from_url("https://chapeco.atende.net/transparencia") == "betha"
        assert tc._detect_platform_from_url("https://itajai.ipm.org.br/transparencia") == "ipam"
        assert tc._detect_platform_from_url("https://florianopolis.e-gov.betha.com.br") == "egov"
        assert tc._detect_platform_from_url("https://betha.com.br/transparencia") == "egov"
        assert tc._detect_platform_from_url("https://tubarao.sc.gov.br") is None


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_empty(self):
        """transform([]) returns an empty list."""
        result = tc.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_no_record_type(self):
        """Records without 'portal_url' or 'platform' are skipped."""
        result = tc.transform([{"unknown": "data"}])
        assert len(result) == 0

    def test_with_subtype_betha(self):
        """Transform preserves source_subtype='betha' from template module."""
        record = {
            "municipio": "Chapeco",
            "slug": "chapeco",
            "portal_url": "https://chapeco.atende.net/transparencia",
            "template_module": "betha",
            "records": [
                {
                    "modalidade": "Pregao",
                    "objeto": "Servico de limpeza",
                    "data_publicacao": "15/06/2025",
                    "valor": "R$ 50.000,00",
                    "content_hash": "abc123",
                    "_source_subtype": "betha",
                }
            ],
        }

        result = tc.transform([record])
        assert len(result) == 1

        r = result[0]
        assert r["source"] == "transparencia"
        assert r["source_subtype"] == "betha"
        assert r["municipio"] == "Chapeco"
        assert r["objeto_compra"] == "Servico de limpeza"
        assert r["valor_total_estimado"] == 50000.0
        assert r["data_publicacao"] == "2025-06-15"
        assert r["uf"] == "SC"

    def test_with_subtype_ipam(self):
        """Transform preserves source_subtype='ipam'."""
        record = {
            "municipio": "Itajai",
            "slug": "itajai",
            "portal_url": "https://itajai.ipm.org.br/transparencia",
            "template_module": "ipam",
            "records": [
                {
                    "modalidade": "Concorrencia",
                    "objeto": "Obra de pavimentacao",
                    "data_publicacao": "01/01/2025",
                    "valor": "",
                    "content_hash": "def456",
                    "_source_subtype": "ipam",
                }
            ],
        }

        result = tc.transform([record])
        assert len(result) == 1
        assert result[0]["source_subtype"] == "ipam"
        assert result[0]["valor_total_estimado"] is None

    def test_with_subtype_egov(self):
        """Transform preserves source_subtype='egov'."""
        record = {
            "municipio": "Florianopolis",
            "slug": "florianopolis",
            "portal_url": "https://florianopolis.e-gov.betha.com.br",
            "template_module": "egov",
            "records": [
                {
                    "modalidade": "Pregao",
                    "objeto": "Servico de TI",
                    "data_publicacao": "10/03/2025",
                    "valor": "R$ 100.000,00",
                    "content_hash": "ghi789",
                    "_source_subtype": "egov",
                }
            ],
        }

        result = tc.transform([record])
        assert len(result) == 1
        assert result[0]["source_subtype"] == "egov"

    def test_with_subtype_generico(self):
        """Transform uses 'generico' when template_module is empty and URL unknown."""
        record = {
            "municipio": "Tubarao",
            "slug": "tubarao",
            "portal_url": "https://tubarao.sc.gov.br",
            "records": [
                {
                    "modalidade": "Pregão",
                    "objeto": "Servico",
                    "data_publicacao": "20/07/2025",
                    "valor": "",
                    "content_hash": "jkl012",
                }
            ],
        }

        result = tc.transform([record])
        assert len(result) == 1
        assert result[0]["source_subtype"] == "generico"

    def test_multiple_records_in_one_municipio(self):
        """Multiple sub-records are all normalized."""
        record = {
            "municipio": "Chapeco",
            "slug": "chapeco",
            "portal_url": "https://chapeco.atende.net/transparencia",
            "template_module": "betha",
            "records": [
                {
                    "modalidade": "Pregao",
                    "objeto": "Item 1",
                    "data_publicacao": "15/06/2025",
                    "valor": "R$ 10.000,00",
                    "content_hash": "h1",
                    "_source_subtype": "betha",
                },
                {
                    "modalidade": "Concorrencia",
                    "objeto": "Item 2",
                    "data_publicacao": "20/06/2025",
                    "valor": "R$ 20.000,00",
                    "content_hash": "h2",
                    "_source_subtype": "betha",
                },
            ],
        }

        result = tc.transform([record])
        assert len(result) == 2
        assert result[0]["source_subtype"] == "betha"
        assert result[1]["source_subtype"] == "betha"
        assert result[0]["objeto_compra"] == "Item 1"
        assert result[1]["objeto_compra"] == "Item 2"

    def test_platform_detection_records_skipped(self):
        """Platform detection records (no 'records' key) are skipped."""
        record = {
            "municipio": "Chapeco",
            "slug": "chapeco",
            "platform": "betha",
            "status": "detected",
        }
        result = tc.transform([record])
        assert len(result) == 0

    def test_source_id_format(self):
        """source_id follows expected format."""
        record = {
            "municipio": "Sao Jose",
            "slug": "sao-jose",
            "portal_url": "https://sao-jose.atende.net/transparencia",
            "template_module": "betha",
            "records": [
                {
                    "modalidade": "Pregao",
                    "objeto": "Teste",
                    "data_publicacao": "01/01/2025",
                    "valor": "",
                    "content_hash": "h3",
                    "_source_subtype": "betha",
                }
            ],
        }

        result = tc.transform([record])
        assert len(result) == 1
        assert result[0]["source_id"] == "transparencia_sao-jose"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config()."""

    def test_12_municipios(self):
        """load_config() returns config with 12 municipios."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)

        municipios = config.get("municipios", {})
        # The config has exactly 12 municipios
        assert len(municipios) == 12, f"Expected 12 municipios, got {len(municipios)}"

        templates = config.get("templates", {})
        assert "portal_transparencia_net" in templates
        assert "e_gov_net" in templates
        assert "custom" in templates

    def test_config_not_found(self):
        """Non-existent path returns empty structure."""
        config = tc.load_config("/tmp/nonexistent_config.yaml")
        assert config == {"templates": {}, "municipios": {}}

    def test_betha_municipios_present(self):
        """Betha municipios (chapeco, sao-jose, blumenau) are configured."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug in ("chapeco", "sao-jose", "blumenau"):
            assert slug in municipios, f"Missing Betha municipio: {slug}"
            assert municipios[slug]["template"] == "portal_transparencia_net"

    def test_ipam_municipios_present(self):
        """Ipam municipios (itajai, criciuma, lages) are configured."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug in ("itajai", "criciuma", "lages"):
            assert slug in municipios, f"Missing Ipam municipio: {slug}"

    def test_egov_municipios_present(self):
        """E-gov municipios (florianopolis, joinville, balneario-camboriu) configured."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug in ("florianopolis", "joinville", "balneario-camboriu"):
            assert slug in municipios, f"Missing E-gov municipio: {slug}"

    def test_custom_municipios_present(self):
        """Custom municipios (tubarao, brusque, rio-do-sul) are configured."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug in ("tubarao", "brusque", "rio-do-sul"):
            assert slug in municipios, f"Missing custom municipio: {slug}"
            assert municipios[slug]["template"] == "custom"

    def test_each_municipio_has_ibge(self):
        """Each municipio has a 7-digit IBGE code."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug, cfg in municipios.items():
            ibge = cfg.get("ibge", "")
            assert len(ibge) == 7, f"{slug}: IBGE '{ibge}' is not 7 digits"
            assert ibge.isdigit(), f"{slug}: IBGE '{ibge}' is not numeric"

    def test_custom_selectors_defined(self):
        """Custom municipios have selectors defined."""
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "transparencia_config.yaml")
        config = tc.load_config(config_path)
        municipios = config.get("municipios", {})

        for slug in ("tubarao", "brusque", "rio-do-sul"):
            assert "selectors" in municipios[slug], f"{slug} missing selectors"
            sel = municipios[slug]["selectors"]
            assert "lista_licitacoes" in sel, f"{slug} missing lista_licitacoes selector"


# ---------------------------------------------------------------------------
# extract_text_from_html (template base)
# ---------------------------------------------------------------------------


class TestExtractTextFromHtml:
    """Tests for extract_text() from template base module."""

    def test_extract_simple_text(self):
        """extract_text returns text content of an element."""
        soup = BeautifulSoup("<div>Hello World</div>", "html.parser")
        assert tmpl_base.extract_text(soup.div) == "Hello World"

    def test_extract_with_selector(self):
        """extract_text with CSS selector returns text from matched child."""
        html = """
        <div class="container">
            <span class="data">15/06/2025</span>
            <span class="valor">R$ 1.000,00</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert tmpl_base.extract_text(soup.div, ".data") == "15/06/2025"
        assert tmpl_base.extract_text(soup.div, ".valor") == "R$ 1.000,00"

    def test_extract_none_element(self):
        """None element returns empty string."""
        assert tmpl_base.extract_text(None) == ""

    def test_extract_missing_selector(self):
        """Non-existent selector returns empty string."""
        soup = BeautifulSoup("<div>Text</div>", "html.parser")
        assert tmpl_base.extract_text(soup.div, ".nao-existe") == ""

    def test_extract_nested_elements(self):
        """extract_text returns stripped text of nested elements."""
        html = '<td><a href="#">  Link Text  </a></td>'
        soup = BeautifulSoup(html, "html.parser")
        result = tmpl_base.extract_text(soup.td)
        assert result == "Link Text"

    def test_extract_with_table(self):
        """extract_text works on table cells."""
        html = """
        <table>
            <tr>
                <td>Pregao</td>
                <td>15/06/2025</td>
                <td>Servico de limpeza</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        tr = soup.find("tr")
        assert tmpl_base.extract_text(tr, "td:nth-child(1)") == "Pregao"
        assert tmpl_base.extract_text(tr, "td:nth-child(2)") == "15/06/2025"
        assert tmpl_base.extract_text(tr, "td:nth-child(3)") == "Servico de limpeza"

    def test_extract_link(self):
        """extract_link returns href from anchor."""
        html = '<a href="https://example.com/licitacao">Detalhes</a>'
        soup = BeautifulSoup(html, "html.parser")
        result = tmpl_base.extract_link(soup.a, "", "https://example.com")
        assert result == "https://example.com/licitacao"

    def test_extract_link_relative(self):
        """Relative URL is resolved against base_url."""
        html = '<a href="/transparencia/123">Detalhes</a>'
        soup = BeautifulSoup(html, "html.parser")
        result = tmpl_base.extract_link(soup.a, "", "https://chapeco.atende.net/transparencia")
        assert result == "https://chapeco.atende.net/transparencia/123"


# ---------------------------------------------------------------------------
# _load_entities and _detect_platform_from_url
# ---------------------------------------------------------------------------


class TestLoadEntities:
    """Tests for _load_entities()."""

    def test_stub_fallback(self):
        """Missing file returns stub list of SC municipios."""
        entities = tc._load_entities("/tmp/nonexistent_entities_file.json")
        assert len(entities) > 0
        assert entities[0]["nome"] == "Florianopolis"

    def test_stub_has_ibge(self):
        """Stub entities have IBGE codes."""
        entities = tc._load_entities("/tmp/nonexistent_entities_file.json")
        for e in entities:
            assert "ibge" in e, f"Entity {e['nome']} missing ibge"

    def test_list_json_format(self):
        """List of dicts is accepted directly."""
        data = [{"nome": "Teste", "ibge": "4200000"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            entities = tc._load_entities(path)
            assert len(entities) == 1
            assert entities[0]["nome"] == "Teste"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_dict_with_municipios_key(self):
        """Dict with 'municipios' key is accepted."""
        data = {"municipios": [{"nome": "Teste", "ibge": "4200000"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            entities = tc._load_entities(path)
            assert len(entities) == 1
            assert entities[0]["nome"] == "Teste"
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# _extract_row (internal row extraction)
# ---------------------------------------------------------------------------


class TestExtractRow:
    """Tests for the internal _extract_row() helper."""

    def test_extract_row_basic(self):
        """Extract row with all columns."""
        html = """
        <tr>
            <td>15/06/2025</td>
            <td>Pregao</td>
            <td>Servico de limpeza</td>
            <td>Prefeitura</td>
            <td>R$ 1.000,00</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        tr = soup.find("tr")
        selectors = {
            "modalidade": "td:nth-child(2)",
            "data": "td:nth-child(1)",
            "objeto": "td:nth-child(3)",
            "orgao": "td:nth-child(4)",
            "valor": "td:nth-child(5)",
            "link": "",
        }
        result = tc._extract_row(tr, selectors, "chapeco", "4204202", "https://chapeco.atende.net")
        assert result is not None
        assert result["modalidade"] == "Pregao"
        assert result["data_publicacao"] == "15/06/2025"
        assert result["objeto"] == "Servico de limpeza"
        assert result["orgao"] == "Prefeitura"
        assert result["valor"] == "R$ 1.000,00"
        assert result["slug"] == "chapeco"
        assert result["codigo_municipio_ibge"] == "4204202"
        assert result["content_hash"] is not None

    def test_extract_row_empty(self):
        """Empty row returns None."""
        html = "<tr><td></td><td></td><td></td></tr>"
        soup = BeautifulSoup(html, "html.parser")
        tr = soup.find("tr")
        selectors = {
            "modalidade": "td:nth-child(2)",
            "data": "td:nth-child(1)",
            "objeto": "td:nth-child(3)",
            "orgao": "",
            "valor": "",
            "link": "",
        }
        result = tc._extract_row(tr, selectors, "teste", "4200000", "https://teste.sc.gov.br")
        assert result is None

    def test_extract_row_with_link(self):
        """Extract row with absolute link."""
        html = '<tr><td>Pregao</td><td>15/06/2025</td><td>Servico</td><td><a href="/detalhes/123">Link</a></td></tr>'
        soup = BeautifulSoup(html, "html.parser")
        tr = soup.find("tr")
        selectors = {
            "modalidade": "td:nth-child(1)",
            "data": "td:nth-child(2)",
            "objeto": "td:nth-child(3)",
            "orgao": "",
            "valor": "",
            "link": "a",
        }
        result = tc._extract_row(tr, selectors, "chapeco", "4204202", "https://chapeco.atende.net")
        assert result is not None
        assert result["link"] == "https://chapeco.atende.net/detalhes/123"


# ---------------------------------------------------------------------------
# health_check (mocked)
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for health_check()."""

    @patch("scripts.crawl.transparencia_crawler._head_url")
    def test_health_check_200(self, mock_head):
        """health_check returns 200 when portal is up."""
        mock_head.return_value = 200
        assert tc.health_check("https://chapeco.atende.net/transparencia") == 200

    @patch("scripts.crawl.transparencia_crawler._head_url")
    def test_health_check_unreachable(self, mock_head):
        """health_check returns 0 when portal is unreachable."""
        mock_head.return_value = 0
        assert tc.health_check("https://inexistente.sc.gov.br") == 0


# ---------------------------------------------------------------------------
# _resolve_selectors
# ---------------------------------------------------------------------------


class TestResolveSelectors:
    """Tests for _resolve_selectors()."""

    def test_custom_selectors_take_priority(self):
        """Municipio-level selectors override template selectors."""
        config = {
            "templates": {
                "custom": {"selectors": {}},
                "portal_transparencia_net": {"selectors": {"lista_licitacoes": "table.licitacao"}},
            },
            "municipios": {},
        }
        cfg = {
            "template": "custom",
            "selectors": {"lista_licitacoes": "table.custom-table"},
        }
        result = tc._resolve_selectors(cfg, config)
        assert result["lista_licitacoes"] == "table.custom-table"

    def test_template_selectors_resolved(self):
        """Template selectors are resolved when no custom selectors."""
        config = {
            "templates": {
                "portal_transparencia_net": {
                    "selectors": {"lista_licitacoes": "table.licitacao", "modalidade": "td:nth-child(1)"},
                },
            },
            "municipios": {},
        }
        cfg = {"template": "portal_transparencia_net"}
        result = tc._resolve_selectors(cfg, config)
        assert result["lista_licitacoes"] == "table.licitacao"

    def test_no_resolution(self):
        """Returns None when no selectors can be resolved."""
        config = {"templates": {}, "municipios": {}}
        cfg = {"template": "unknown"}
        result = tc._resolve_selectors(cfg, config)
        assert result is None

    def test_custom_without_selectors_falls_back(self):
        """Template 'custom' without selectors falls through."""
        config = {
            "templates": {
                "custom": {"selectors": {}},
                "portal_transparencia_net": {"selectors": {"lista_licitacoes": "table.licitacao"}},
            },
            "municipios": {},
        }
        cfg = {"template": "custom"}
        result = tc._resolve_selectors(cfg, config)
        assert result is None


# ---------------------------------------------------------------------------
# _head_url and _fetch_url
# ---------------------------------------------------------------------------


class TestHttpHelpers:
    """Tests for HTTP helper functions with mocked urllib.

    Since ``urllib`` is imported locally inside ``_fetch_url`` / ``_head_url``,
    we patch ``urllib.request.urlopen`` at the global level.
    """

    @patch("urllib.request.urlopen")
    def test_head_url_success(self, mock_urlopen):
        """_head_url returns 200 on successful HEAD."""
        mock_urlopen.return_value.__enter__.return_value.status = 200
        assert tc._head_url("https://example.com") == 200

    @patch("urllib.request.urlopen")
    def test_head_url_error(self, mock_urlopen):
        """_head_url returns 0 on connection error."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("test error")
        assert tc._head_url("https://example.com") == 0

    @patch("urllib.request.urlopen")
    def test_fetch_url_success(self, mock_urlopen):
        """_fetch_url returns (200, body) on success."""
        mock_urlopen.return_value.__enter__.return_value.status = 200
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"<html>OK</html>"
        status, body = tc._fetch_url("https://example.com")
        assert status == 200
        assert body == "<html>OK</html>"

    @patch("urllib.request.urlopen")
    def test_fetch_url_http_error(self, mock_urlopen):
        """_fetch_url returns HTTP error code on 4xx/5xx."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 404, "Not Found", {}, None,
        )
        status, body = tc._fetch_url("https://example.com")
        assert status == 404
        assert body == ""


# ---------------------------------------------------------------------------
# make_record (template base)
# ---------------------------------------------------------------------------


class TestMakeRecord:
    """Tests for make_record() from template base."""

    def test_make_record_basic(self):
        """make_record creates a record with content hash."""
        record = tmpl_base.make_record(
            slug="chapeco",
            ibge="4204202",
            portal_url="https://chapeco.atende.net",
            modalidade="Pregao",
            data_publicacao="15/06/2025",
            objeto="Servico de limpeza",
            orgao="Prefeitura",
            valor="R$ 1.000,00",
        )
        assert record is not None
        assert record["slug"] == "chapeco"
        assert record["modalidade"] == "Pregao"
        assert record["content_hash"] is not None

    def test_make_record_empty_returns_none(self):
        """make_record returns None when all fields are empty."""
        record = tmpl_base.make_record(
            slug="teste",
            ibge="",
            portal_url="",
        )
        assert record is None

    def test_make_record_consistency(self):
        """Same inputs produce same content_hash."""
        r1 = tmpl_base.make_record(
            slug="a", ibge="1", portal_url="u",
            modalidade="M", data_publicacao="D", objeto="O",
        )
        r2 = tmpl_base.make_record(
            slug="b", ibge="2", portal_url="v",
            modalidade="M", data_publicacao="D", objeto="O",
        )
        assert r1 is not None and r2 is not None
        # Content hash ignores slug/ibge/portal_url
        assert r1["content_hash"] == r2["content_hash"]


# ---------------------------------------------------------------------------
# parse_table_rows (template base)
# ---------------------------------------------------------------------------


class TestParseTableRows:
    """Tests for parse_table_rows() from template base."""

    def test_parse_table_rows(self):
        """parse_table_rows extracts records from an HTML table."""
        html = """
        <table class="licitacao">
            <tr><th>Data</th><th>Modalidade</th><th>Objeto</th></tr>
            <tr><td>15/06/2025</td><td>Pregao</td><td>Servico de limpeza</td></tr>
            <tr><td>20/06/2025</td><td>Concorrencia</td><td>Obra</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        records = tmpl_base.parse_table_rows(
            soup, "table.licitacao",
            url="https://example.com",
            slug="teste",
            ibge="4200000",
            data_sel="td:nth-child(1)",
            modalidade_sel="td:nth-child(2)",
            objeto_sel="td:nth-child(3)",
        )
        assert len(records) == 2
        assert records[0]["data_publicacao"] == "15/06/2025"
        assert records[0]["modalidade"] == "Pregao"
        assert records[1]["modalidade"] == "Concorrencia"

    def test_parse_table_skip_header(self):
        """First row is skipped when skip_header=True (default)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr><td>Data row</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        records = tmpl_base.parse_table_rows(
            soup, "table",
            url="", slug="t", ibge="",
            modalidade_sel="td:nth-child(1)",
        )
        assert len(records) == 1

    def test_parse_table_no_table(self):
        """Missing table returns empty list."""
        soup = BeautifulSoup("<div></div>", "html.parser")
        records = tmpl_base.parse_table_rows(soup, "table.nao-existe")
        assert records == []


# ---------------------------------------------------------------------------
# crawl() interface
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl()."""

    @patch("scripts.crawl.transparencia_crawler._load_entities")
    @patch("scripts.crawl.transparencia_crawler._load_existing_results")
    @patch("scripts.crawl.transparencia_crawler.detect_platform")
    def test_crawl_full(self, mock_detect, mock_existing, mock_entities):
        """crawl('full') iterates over entities and returns results."""
        mock_entities.return_value = [
            {"nome": "Chapeco", "slug": "chapeco", "ibge": "4204202"},
            {"nome": "Blumenau", "slug": "blumenau", "ibge": "4202404"},
        ]
        mock_existing.return_value = {"detected": [], "metadata": {"version": 1}}
        mock_detect.side_effect = lambda slug, municipio: {
            "municipio": municipio,
            "slug": slug,
            "platform": "betha",
            "status": "detected",
            "detected_at": "2025-01-01",
        }

        results = tc.crawl(mode="full")
        assert len(results) == 2
        assert results[0]["municipio"] == "Chapeco"
        assert results[1]["municipio"] == "Blumenau"
        assert mock_detect.call_count == 2

    @patch("scripts.crawl.transparencia_crawler._load_entities")
    @patch("scripts.crawl.transparencia_crawler._load_existing_results")
    @patch("scripts.crawl.transparencia_crawler.detect_platform")
    def test_crawl_incremental_skips_existing(
        self, mock_detect, mock_existing, mock_entities,
    ):
        """crawl('incremental') skips already-detected slugs."""
        mock_entities.return_value = [
            {"nome": "Chapeco", "slug": "chapeco", "ibge": "4204202"},
            {"nome": "Blumenau", "slug": "blumenau", "ibge": "4202404"},
        ]
        mock_existing.return_value = {
            "detected": [
                {"slug": "chapeco", "platform": "betha", "status": "detected"},
            ],
            "metadata": {"version": 1},
        }
        mock_detect.return_value = {
            "municipio": "Blumenau",
            "slug": "blumenau",
            "platform": "betha",
            "status": "detected",
            "detected_at": "2025-01-01",
        }

        results = tc.crawl(mode="incremental")
        # 1 existing + 1 new = 2 results
        assert len(results) == 2
        assert mock_detect.call_count == 1  # Only Blumenau was detected

    def test_crawl_template_delegates(self):
        """crawl('template') delegates to crawl_template()."""
        with patch("scripts.crawl.transparencia_crawler.crawl_template") as mock_ct:
            mock_ct.return_value = [{"status": "ok", "count": 5}]
            results = tc.crawl(mode="template")
            assert len(results) == 1
            mock_ct.assert_called_once()
