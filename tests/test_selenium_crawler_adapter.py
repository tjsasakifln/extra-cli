"""Tests for the Selenium Crawler Adapter (COVERAGE-3.1).

Tests the adapter's data transformation and portal loading logic
without requiring a real Selenium WebDriver (unit tests only).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PORTALS = [
    {
        "slug": "florianopolis",
        "nome": "Florianopolis",
        "ibge": "4205407",
        "url": "https://florianopolis.e-gov.betha.com.br",
        "platform": "e_gov_net",
        "requires_js": True,
        "framework_guess": "React",
    },
    {
        "slug": "sao-jose",
        "nome": "Sao Jose",
        "ibge": "4216602",
        "url": "https://sao-jose.atende.net/transparencia",
        "platform": "portal_transparencia_net",
        "requires_js": True,
        "framework_guess": "React",
    },
    {
        "slug": "blumenau",
        "nome": "Blumenau",
        "ibge": "4202404",
        "url": "https://blumenau.sc.gov.br",
        "platform": "custom",
        "requires_js": True,
        "framework_guess": "Angular",
    },
]


@pytest.fixture
def sample_portals_json(tmp_path: Path) -> Path:
    """Create a temporary portals JSON file for testing."""
    filepath = tmp_path / "js_portals_list.json"
    data = {"generated_at": "2026-07-11", "source": "test", "total": 3, "portals": SAMPLE_PORTALS}
    with open(filepath, "w") as f:
        json.dump(data, f)
    return filepath


@pytest.fixture
def sample_crawl_results() -> list[dict]:
    """Sample results from SeleniumBatchCrawler.run_batch()."""
    return [
        {
            "slug": "florianopolis",
            "municipio": "Florianopolis",
            "ibge": "4205407",
            "url": "https://florianopolis.e-gov.betha.com.br",
            "platform": "e_gov_net",
            "status": "ok",
            "framework": "React",
            "bid_count": 3,
            "bids": [
                {
                    "orgao_nome": "Prefeitura de Florianopolis",
                    "orgao_cnpj": "",
                    "modalidade": "Pregao",
                    "objeto": "Contratacao de servicos de limpeza",
                    "data_publicacao": "2026-07-01",
                    "valor": "R$ 150.000,00",
                    "municipio": "Florianopolis",
                    "codigo_municipio_ibge": "4205407",
                    "uf": "SC",
                    "source": "selenium",
                    "slug": "florianopolis",
                    "framework": "React",
                    "portal_url": "https://florianopolis.e-gov.betha.com.br",
                },
                {
                    "orgao_nome": "Prefeitura de Florianopolis",
                    "orgao_cnpj": "",
                    "modalidade": "Dispensa",
                    "objeto": "Aquisicao de material escolar",
                    "data_publicacao": "2026-07-02",
                    "valor": "R$ 25.000,00",
                    "municipio": "Florianopolis",
                    "codigo_municipio_ibge": "4205407",
                    "uf": "SC",
                    "source": "selenium",
                    "slug": "florianopolis",
                    "framework": "React",
                    "portal_url": "https://florianopolis.e-gov.betha.com.br",
                },
            ],
            "error": None,
            "method": "selenium",
        },
        {
            "slug": "sao-jose",
            "municipio": "Sao Jose",
            "ibge": "4216602",
            "url": "https://sao-jose.atende.net/transparencia",
            "platform": "portal_transparencia_net",
            "status": "ok",
            "framework": "React",
            "bid_count": 1,
            "bids": [
                {
                    "orgao_nome": "Prefeitura de Sao Jose",
                    "orgao_cnpj": "",
                    "modalidade": "Concorrencia",
                    "objeto": "Pavimentacao de ruas",
                    "data_publicacao": "2026-07-03",
                    "valor": "R$ 500.000,00",
                    "municipio": "Sao Jose",
                    "codigo_municipio_ibge": "4216602",
                    "uf": "SC",
                    "source": "selenium",
                    "slug": "sao-jose",
                    "framework": "React",
                    "portal_url": "https://sao-jose.atende.net/transparencia",
                },
            ],
            "error": None,
            "method": "selenium",
        },
        {
            "slug": "blumenau",
            "municipio": "Blumenau",
            "ibge": "4202404",
            "url": "https://blumenau.sc.gov.br",
            "status": "error",
            "framework": "unknown",
            "bid_count": 0,
            "bids": [],
            "error": "Timeout loading page",
            "method": "selenium",
        },
    ]


# ---------------------------------------------------------------------------
# Tests: load_portals
# ---------------------------------------------------------------------------


class TestLoadPortals:
    """Test the portal list loader."""

    def test_load_portals_from_file(self, sample_portals_json: Path, monkeypatch):
        """Should load portals from a valid JSON file."""
        monkeypatch.setenv("SELENIUM_PORTALS_FILE", str(sample_portals_json))
        from scripts.crawl.selenium_crawler_adapter import load_portals

        portals = load_portals()
        assert len(portals) == 3
        assert portals[0]["slug"] == "florianopolis"
        assert portals[1]["slug"] == "sao-jose"

    def test_load_portals_missing_file(self):
        """Should return empty list for missing file."""
        from scripts.crawl.selenium_crawler_adapter import load_portals

        portals = load_portals("/tmp/nonexistent_portals.json")
        assert portals == []

    def test_load_portals_empty_list(self, tmp_path: Path):
        """Should handle empty portal list gracefully."""
        filepath = tmp_path / "empty.json"
        with open(filepath, "w") as f:
            json.dump({"portals": []}, f)
        from scripts.crawl.selenium_crawler_adapter import load_portals

        portals = load_portals(str(filepath))
        assert portals == []

    def test_load_portals_top_level_list(self, tmp_path: Path):
        """Should handle JSON that is a top-level list."""
        filepath = tmp_path / "list.json"
        with open(filepath, "w") as f:
            json.dump(SAMPLE_PORTALS, f)
        from scripts.crawl.selenium_crawler_adapter import load_portals

        portals = load_portals(str(filepath))
        assert len(portals) == 3


# ---------------------------------------------------------------------------
# Tests: _parse_valor
# ---------------------------------------------------------------------------


class TestParseValor:
    """Test Brazilian currency parsing."""

    def test_parse_full_brl(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("R$ 1.234,56") == 1234.56

    def test_parse_without_prefix(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("1.234,56") == 1234.56

    def test_parse_integer(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor(1234) == 1234.0

    def test_parse_float(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor(1234.56) == 1234.56

    def test_parse_empty_returns_none(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("") is None

    def test_parse_none_returns_none(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor(None) is None

    def test_parse_invalid_string(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("N/A") is None

    def test_parse_rs_prefix(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("RS 999,99") == 999.99

    def test_parse_large_value(self):
        from scripts.crawl.selenium_crawler_adapter import _parse_valor

        assert _parse_valor("R$ 12.345.678,90") == 12345678.90


# ---------------------------------------------------------------------------
# Tests: transform
# ---------------------------------------------------------------------------


class TestTransform:
    """Test the transform() function that flattens crawl results to pncp_raw_bids schema."""

    def test_transform_successful_bids(self, sample_crawl_results):
        """Should flatten successful bids to standard schema."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform(sample_crawl_results)

        # Only floripa (2 bids) + sao jose (1 bid) = 3
        assert len(flat) == 3

        # Check schema keys — must match upsert_pncp_raw_bids contract
        required_keys = {
            "pncp_id", "objeto_compra", "valor_total_estimado",
            "modalidade_id", "modalidade_nome", "esfera_id",
            "uf", "municipio", "codigo_municipio_ibge",
            "orgao_razao_social", "orgao_cnpj",
            "data_publicacao", "link_pncp",
            "content_hash", "source_id",
        }
        for record in flat:
            assert required_keys.issubset(record.keys()), f"Missing keys: {required_keys - record.keys()}"

        # Check static values
        for record in flat:
            assert record["uf"] == "SC"
            assert record["esfera_id"] == 3  # Municipal

        # Check values
        florianopolis_records = [r for r in flat if r["municipio"] == "Florianopolis"]
        assert len(florianopolis_records) == 2
        assert florianopolis_records[0]["valor_total_estimado"] == 150000.0
        assert florianopolis_records[1]["valor_total_estimado"] == 25000.0

        sao_jose_records = [r for r in flat if r["municipio"] == "Sao Jose"]
        assert len(sao_jose_records) == 1
        assert sao_jose_records[0]["modalidade_nome"] == "Concorrencia"
        assert sao_jose_records[0]["modalidade_id"] == 4

    def test_transform_excludes_errors(self, sample_crawl_results):
        """Should skip portals with status != 'ok'."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform(sample_crawl_results)
        # blumenau has status "error" — should be excluded
        blumenau_records = [r for r in flat if r["municipio"] == "Blumenau"]
        assert len(blumenau_records) == 0

    def test_transform_empty_results(self):
        """Should handle empty list."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform([])
        assert flat == []

    def test_transform_no_bids_portal(self):
        """Should skip portals with empty bids list."""
        from scripts.crawl.selenium_crawler_adapter import transform

        results = [
            {
                "slug": "empty",
                "municipio": "Empty",
                "status": "ok",
                "bids": [],
                "bid_count": 0,
            }
        ]
        flat = transform(results)
        assert flat == []

    def test_transform_uses_orgao_razao_social(self, sample_crawl_results):
        """Should populate orgao_razao_social for entity matching."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform(sample_crawl_results)
        for record in flat:
            assert record["orgao_razao_social"]  # must be non-empty
            assert isinstance(record["orgao_razao_social"], str)

    def test_transform_source_id(self, sample_crawl_results):
        """Should generate deterministic source_id."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform(sample_crawl_results)
        for record in flat:
            assert "source_id" in record
            assert record["source_id"].startswith("selenium_")

    def test_transform_content_hash(self, sample_crawl_results):
        """Should generate deterministic content_hash."""
        from scripts.crawl.selenium_crawler_adapter import transform

        flat = transform(sample_crawl_results)
        for record in flat:
            assert "content_hash" in record
            assert len(record["content_hash"]) == 32  # md5 hex


# ---------------------------------------------------------------------------
# Tests: crawl (mock mode — no real Selenium)
# ---------------------------------------------------------------------------


class TestCrawl:
    """Test the crawl() function with mocked SeleniumBatchCrawler."""

    def test_crawl_dry_run(self, monkeypatch):
        """Should list portals without executing crawl."""
        # Point to real portals file but use dry-run mode (no browser needed)
        from scripts.crawl.selenium_crawler_adapter import crawl

        results = crawl(mode="dry-run")
        assert len(results) >= 1
        for r in results:
            assert r["status"] == "dry-run"
            assert r["method"] == "dry_run"

    def test_crawl_no_portals(self, tmp_path: Path, monkeypatch):
        """Should handle empty portal list gracefully."""
        empty_file = tmp_path / "empty.json"
        with open(empty_file, "w") as f:
            json.dump({"portals": []}, f)
        monkeypatch.setattr(
            "scripts.crawl.selenium_crawler_adapter.SELENIUM_PORTALS_FILE",
            str(empty_file),
        )
        from scripts.crawl.selenium_crawler_adapter import crawl

        results = crawl(mode="full")
        assert results == []

    def test_crawl_missing_portals_file(self, monkeypatch):
        """Should handle missing portals file gracefully."""
        monkeypatch.setattr(
            "scripts.crawl.selenium_crawler_adapter.SELENIUM_PORTALS_FILE",
            "/tmp/nonexistent_portals.json",
        )
        from scripts.crawl.selenium_crawler_adapter import crawl

        results = crawl(mode="full")
        assert results == []

    @patch("scripts.crawl.selenium_crawler.SeleniumBatchCrawler")
    def test_crawl_mocked_batch(self, mock_batch_class, monkeypatch):
        """Should call SeleniumBatchCrawler.run_batch with loaded portals."""
        # Point to real portals file for proper loading
        mock_instance = mock_batch_class.return_value
        mock_instance.run_batch.return_value = {
            "extracted": 5,
            "failed": 0,
            "portal_count": 3,
            "results": [
                {"slug": "florianopolis", "status": "ok", "bid_count": 5},
            ],
        }

        from scripts.crawl.selenium_crawler_adapter import crawl

        results = crawl(mode="full")
        mock_batch_class.assert_called_once()
        mock_instance.run_batch.assert_called_once()
        assert len(results) == 1
        assert results[0]["status"] == "ok"
