"""Unit tests for scripts/crawl/dados_abertos_sc_crawler.py.

All network I/O is mocked. Fixtures under tests/fixtures/ckan/ are sanitized
captures from live discovery (no secrets).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl import dados_abertos_sc_crawler as das

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ckan"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixture_search_diario() -> dict:
    return _load("dados_sc_package_search_diario.json")


@pytest.fixture
def fixture_show_publicacoes() -> dict:
    return _load("dados_sc_package_show_publicacoes.json")


@pytest.fixture
def fixture_status() -> dict:
    return _load("dados_sc_status_show.json")


def _mock_urlopen_sequence(responses: list[dict]):
    """Build a side_effect for urllib.request.urlopen returning JSON bodies."""
    calls = iter(responses)

    def _open(req, timeout=None):  # noqa: ANN001
        payload = next(calls)
        body = json.dumps(payload).encode("utf-8")
        cm = MagicMock()
        cm.read.return_value = body
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.headers = {"Content-Type": "application/json"}
        return cm

    return _open


class TestCkanClient:
    def test_package_search_returns_result(self, fixture_search_diario):
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence([fixture_search_diario])):
            result = das.package_search("diario", rows=3)
        assert result is not None
        assert result["count"] == fixture_search_diario["result"]["count"]
        names = [p["name"] for p in result["results"]]
        assert "diario-oficial-sc-publicacoes" in names

    def test_package_show_lists_resources(self, fixture_show_publicacoes):
        with patch(
            "urllib.request.urlopen",
            side_effect=_mock_urlopen_sequence([fixture_show_publicacoes]),
        ):
            pkg = das.package_show("diario-oficial-sc-publicacoes")
        assert pkg is not None
        assert pkg["name"] == "diario-oficial-sc-publicacoes"
        resources = das.list_resources(pkg)
        assert len(resources) >= 2
        formats = {r["format"] for r in resources}
        assert "CSV" in formats or "XLSX" in formats
        assert all(r.get("id") and r.get("url") for r in resources)

    def test_status_show(self, fixture_status):
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence([fixture_status])):
            status = das.status_show()
        assert status is not None

    def test_ckan_get_http_error(self):
        import urllib.error

        def _raise(req, timeout=None):  # noqa: ANN001
            raise urllib.error.HTTPError(req.full_url, 500, "err", hdrs=None, fp=None)  # type: ignore[arg-type]

        with patch("urllib.request.urlopen", side_effect=_raise):
            assert das.package_show("x") is None


class TestCrawlSmoke:
    def test_crawl_smoke_lists_resources(
        self,
        fixture_status,
        fixture_search_diario,
        fixture_show_publicacoes,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        # status + search + package_show
        seq = [fixture_status, fixture_search_diario, fixture_show_publicacoes]
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence(seq)):
            records = das.crawl(mode="smoke", dry_run=True)

        types = {r.get("record_type") for r in records}
        assert "ckan_status" in types
        assert "package_search" in types
        assert "ckan_resource" in types

        resources = [r for r in records if r["record_type"] == "ckan_resource"]
        assert len(resources) == len(fixture_show_publicacoes["result"]["resources"])
        assert all(r.get("resource_id") for r in resources)
        assert all(r.get("url") for r in resources)

        # checkpoint written
        cps = list(tmp_path.glob("*.json"))
        assert cps
        cp = json.loads(cps[0].read_text(encoding="utf-8"))
        assert cp["source"] == das.SOURCE_NAME
        assert cp["resource_count"] == len(resources)

    def test_crawl_incremental_primary_only(
        self, fixture_show_publicacoes, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)
        with patch(
            "urllib.request.urlopen",
            side_effect=_mock_urlopen_sequence([fixture_show_publicacoes]),
        ):
            records = das.crawl(mode="incremental", dry_run=True)
        assert all(
            r.get("record_type") != "package_search" for r in records
        )  # incremental skips search
        resources = [r for r in records if r.get("record_type") == "ckan_resource"]
        assert len(resources) > 0


class TestTransform:
    def test_transform_resource_row(self):
        raw = {
            "record_type": "ckan_resource",
            "resource_id": "abc-123",
            "name": "publicacoes_2025.csv",
            "format": "CSV",
            "package_id": "diario-oficial-sc-publicacoes",
            "url": "https://portal.doe.sea.sc.gov.br/repositorio/dadosabertos/publicacoes_2025.csv",
            "last_modified": "2025-07-21T00:00:00",
        }
        out = das.transform_record(raw)
        assert out is not None
        assert out["source"] == das.SOURCE_NAME
        assert out["pncp_id"]
        assert out["uf"] == "SC"
        assert out["esfera_id"] == das.ESFERA_ID_ESTADUAL
        assert "publicacoes_2025" in out["objeto_compra"]
        assert out["metadata_only"] is True

    def test_transform_skips_invalid(self):
        assert das.transform_record({}) is None
        assert das.transform_record({"record_type": "ckan_resource"}) is None

    def test_transform_batch(self):
        records = [
            {
                "record_type": "ckan_resource",
                "resource_id": "1",
                "name": "a.csv",
                "format": "CSV",
                "package_id": "diario-oficial-sc-publicacoes",
                "url": "https://example.com/a.csv",
            },
            {"record_type": "package_search", "q": "diario", "count": 7},
        ]
        out = das.transform(records)
        assert len(out) == 2
        assert out[0]["source_id"] == "1"
        assert out[1]["metadata_only"] is True


class TestConstants:
    def test_source_name(self):
        assert das.SOURCE_NAME == "dados_abertos_sc"

    def test_primary_package(self):
        assert das.PRIMARY_PACKAGE == "diario-oficial-sc-publicacoes"

    def test_user_agent_imported(self):
        assert "Extra-Consultoria" in das.USER_AGENT
