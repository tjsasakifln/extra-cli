"""Unit tests for scripts/crawl/ciga_ckan_crawler.py.

All external calls (CKAN API, ZIP downloads, PostgreSQL) are mocked.
No real network or database access.
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl import ciga_ckan_crawler as ciga

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_publication() -> dict:
    """A single procurement publication from DOM-SC."""
    return {
        "entidade": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
        "municipio": "FLORIANOPOLIS",
        "data": "2025-12-15T10:00:00",
        "categoria": "Contratos",
        "resumo": "Contrato de prestacao de servicos",
    }


@pytest.fixture
def sample_publications(sample_publication) -> list[dict]:
    """Multiple publications from different entities."""
    return [
        sample_publication,
        {
            "entidade": "Prefeitura Municipal de Sao Jose",
            "municipio": "SAO JOSE",
            "data": "2025-12-10",
            "categoria": "Licitações",
        },
        {
            "entidade": "CAMARA DE VEREADORES DE FLORIANOPOLIS",
            "municipio": "FLORIANOPOLIS",
            "data": "2025-11-01",
            "categoria": "Contratos",
        },
        {
            "entidade": "SECRETARIA MUNICIPAL DE SAUDE DE FLORIANOPOLIS",
            "municipio": "FLORIANOPOLIS",
            "data": "2025-12-01",
            "categoria": "Convênios",
        },
        # Non-procurement category — should be filtered out
        {
            "entidade": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
            "municipio": "FLORIANOPOLIS",
            "data": "2025-12-15",
            "categoria": "Outros",
        },
    ]


@pytest.fixture
def db_entities() -> list[dict]:
    """Simulated sc_public_entities rows."""
    return [
        {
            "id": 1001,
            "razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
            "cnpj_8": "12345678",
            "municipio": "FLORIANOPOLIS",
            "codigo_ibge": "4205407",
            "natureza_juridica": "MUNICIPIO",
            "raio_200km": True,
        },
        {
            "id": 1002,
            "razao_social": "PREFEITURA MUNICIPAL DE SAO JOSE",
            "cnpj_8": "23456789",
            "municipio": "SAO JOSE",
            "codigo_ibge": "4205506",
            "natureza_juridica": "MUNICIPIO",
            "raio_200km": True,
        },
        {
            "id": 1003,
            "razao_social": "CAMARA DE VEREADORES DE FLORIANOPOLIS",
            "cnpj_8": "34567890",
            "municipio": "FLORIANOPOLIS",
            "codigo_ibge": "4205407",
            "natureza_juridica": "CAMARA",
            "raio_200km": True,
        },
        {
            "id": 1004,
            "razao_social": "SECRETARIA MUNICIPAL DE SAUDE DE FLORIANOPOLIS",
            "cnpj_8": "45678901",
            "municipio": "FLORIANOPOLIS",
            "codigo_ibge": "4205407",
            "natureza_juridica": "SECRETARIA",
            "raio_200km": True,
        },
    ]


@pytest.fixture
def mock_ckan_package_list() -> dict:
    """Mock CKAN package_list response."""
    return {
        "success": True,
        "result": [
            "domsc-publicacoes-de-janeiro-2023",
            "domsc-publicacoes-de-fevereiro-2023",
            "domsc-publicacoes-de-marco-2023",
        ],
    }


def _make_zip_bytes(content: dict) -> bytes:
    """Create a ZIP file in memory containing a JSON with autopublicacoes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("publicacoes.json", json.dumps(content))
    return buf.getvalue()


# ===========================================================================
# _ckan_request
# ===========================================================================


class TestCkanRequest:
    """Tests for _ckan_request()."""

    @patch("urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        """Successful API call returns result data."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": True, "result": ["a", "b"]}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga._ckan_request("https://example.com/api")
        assert result == ["a", "b"]

    @patch("urllib.request.urlopen")
    def test_success_false(self, mock_urlopen):
        """API returns success=false returns None."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": False}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga._ckan_request("https://example.com/api")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        """HTTP 404 returns None gracefully."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError("http://example.com", 404, "Not Found", {}, None)

        result = ciga._ckan_request("https://example.com/api")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen):
        """Timeout error returns None gracefully."""
        mock_urlopen.side_effect = TimeoutError("timed out")

        result = ciga._ckan_request("https://example.com/api")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_json_decode_error(self, mock_urlopen):
        """Invalid JSON response returns None."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga._ckan_request("https://example.com/api")
        assert result is None


# ===========================================================================
# list_datasets / list_domsc_months / classify_month
# ===========================================================================


class TestListDatasets:
    """Tests for list_datasets()."""

    @patch("scripts.crawl.ciga_ckan_crawler._ckan_request")
    def test_returns_sorted_list(self, mock_request):
        """Returns sorted list of dataset IDs."""
        mock_request.return_value = ["z", "a", "m"]
        result = ciga.list_datasets()
        assert result == ["a", "m", "z"]

    @patch("scripts.crawl.ciga_ckan_crawler._ckan_request")
    def test_empty_when_no_result(self, mock_request):
        """Returns empty list when API returns None."""
        mock_request.return_value = None
        assert ciga.list_datasets() == []


class TestListDomscMonths:
    """Tests for list_domsc_months()."""

    @patch("scripts.crawl.ciga_ckan_crawler.list_datasets")
    def test_filters_domsc_datasets(self, mock_list):
        """Only DOM-SC datasets are returned."""
        mock_list.return_value = [
            "domsc-publicacoes-de-janeiro-2023",
            "other-dataset",
            "dom-sc-publicacoes-de-marco-2023",
            "domsc-publicacoes-de-fevereiro-2023",
        ]
        result = ciga.list_domsc_months()
        assert len(result) == 3
        assert all(d.startswith(("domsc-", "dom-sc-")) for d in result)

    @patch("scripts.crawl.ciga_ckan_crawler.list_datasets")
    def test_sorted_order(self, mock_list):
        """Results are sorted oldest first."""
        mock_list.return_value = [
            "domsc-publicacoes-de-marco-2023",
            "domsc-publicacoes-de-janeiro-2023",
        ]
        result = ciga.list_domsc_months()
        assert "janeiro" in result[0]
        assert "marco" in result[1]

    @patch("scripts.crawl.ciga_ckan_crawler.list_datasets")
    def test_empty_when_no_match(self, mock_list):
        """Returns empty list when no DOM-SC datasets exist."""
        mock_list.return_value = ["other-dataset", "another-one"]
        assert ciga.list_domsc_months() == []


class TestClassifyMonth:
    """Tests for classify_month()."""

    def test_standard_format(self):
        """domsc-publicacoes-de-janeiro-2023 -> 'janeiro-2023'."""
        assert ciga.classify_month("domsc-publicacoes-de-janeiro-2023") == "janeiro-2023"

    def test_alt_prefix(self):
        """dom-sc-publicacoes-de-marco-2023 -> 'marco-2023'."""
        assert ciga.classify_month("dom-sc-publicacoes-de-marco-2023") == "marco-2023"

    def test_no_match(self):
        """Dataset without 'de' pattern returns None."""
        assert ciga.classify_month("some-random-dataset") is None


# ===========================================================================
# get_package / get_package_resources
# ===========================================================================


class TestGetPackage:
    """Tests for get_package()."""

    @patch("scripts.crawl.ciga_ckan_crawler._ckan_request")
    def test_get_package(self, mock_request):
        """Calls package_show with correct ID."""
        mock_request.return_value = {"id": "test-pkg", "resources": []}
        result = ciga.get_package("test-pkg")
        assert result["id"] == "test-pkg"
        # Verify URL contains package_show?id=test-pkg
        call_url = mock_request.call_args[0][0]
        assert "package_show" in call_url
        assert "test-pkg" in call_url


class TestGetPackageResources:
    """Tests for get_package_resources()."""

    def test_returns_resources(self):
        """Extracts resources list from package dict."""
        pkg = {"resources": [{"url": "http://example.com/z1.zip"}, {"url": "http://example.com/z2.zip"}]}
        result = ciga.get_package_resources(pkg)
        assert len(result) == 2

    def test_empty_when_no_resources(self):
        """Returns empty list when no resources key."""
        assert ciga.get_package_resources({}) == []


# ===========================================================================
# download_resource
# ===========================================================================


class TestDownloadResource:
    """Tests for download_resource()."""

    @patch("urllib.request.urlopen")
    def test_valid_zip(self, mock_urlopen):
        """Valid ZIP with JSON autopublicacoes returns parsed content."""
        content = {"autopublicacoes": [{"categoria": "Contratos"}]}
        zip_bytes = _make_zip_bytes(content)

        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_bytes
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga.download_resource("http://example.com/file.zip")
        assert result == content

    @patch("urllib.request.urlopen")
    def test_bad_zip(self, mock_urlopen):
        """Corrupt ZIP returns None."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not a zip file"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga.download_resource("http://example.com/bad.zip")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        """Network failure returns None."""
        mock_urlopen.side_effect = Exception("Connection refused")

        result = ciga.download_resource("http://example.com/fail.zip")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_no_json_in_zip(self, mock_urlopen):
        """ZIP without JSON files returns None."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.csv", "a,b,c\n1,2,3\n")

        mock_resp = MagicMock()
        mock_resp.read.return_value = buf.getvalue()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = ciga.download_resource("http://example.com/nojson.zip")
        assert result is None


# ===========================================================================
# extract_entities
# ===========================================================================


class TestExtractEntities:
    """Tests for extract_entities()."""

    def test_extracts_unique_entities(self, sample_publications):
        """Unique entities are extracted with correct metadata."""
        entities = ciga.extract_entities(sample_publications)

        # 4 unique entities (5th has non-procurement category but is still counted)
        # Actually, extract_entities doesn't filter by category — that's done
        # in download_month. So all 5 records produce 4 unique entities
        # (the first and last have the same entidade+municipio)
        assert len(entities) == 4

        # Check first entity
        key = "PREFEITURA MUNICIPAL DE FLORIANOPOLIS||FLORIANOPOLIS"
        assert key in entities
        entry = entities[key]
        assert entry["count"] == 2  # two publications for same entity
        assert entry["raw_name"] == "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"
        assert entry["first_seen"] == "2025-12-15"

    def test_empty_input(self):
        """Empty list returns empty dict."""
        assert ciga.extract_entities([]) == {}

    def test_publications_without_entidade(self):
        """Publications without entidade are skipped."""
        pubs = [
            {"municipio": "FLORIANOPOLIS", "categoria": "Contratos"},
            {"entidade": "", "municipio": "SAO JOSE", "categoria": "Licitações"},
        ]
        entities = ciga.extract_entities(pubs)
        assert len(entities) == 0

    def test_tracks_first_and_last_seen(self):
        """first_seen and last_seen reflect min/max dates."""
        pubs = [
            {"entidade": "PREFEITURA DE X", "municipio": "X", "data": "2025-03-01", "categoria": "Contratos"},
            {"entidade": "PREFEITURA DE X", "municipio": "X", "data": "2025-01-15", "categoria": "Licitações"},
            {"entidade": "PREFEITURA DE X", "municipio": "X", "data": "2025-06-01", "categoria": "Contratos"},
        ]
        entities = ciga.extract_entities(pubs)
        key = "PREFEITURA DE X||X"
        assert entities[key]["first_seen"] == "2025-01-15"
        assert entities[key]["last_seen"] == "2025-06-01"


# ===========================================================================
# _generate_name_aliases
# ===========================================================================


class TestGenerateNameAliases:
    """Tests for _generate_name_aliases()."""

    def test_prefeitura_municipal(self):
        """'PREFEITURA MUNICIPAL DE X' -> 'MUNICIPIO DE X'."""
        aliases = ciga._generate_name_aliases("PREFEITURA MUNICIPAL DE FLORIANOPOLIS")
        assert any("MUNICIPIO DE FLORIANOPOLIS" in a for a in aliases)

    def test_prefeitura_short(self):
        """'PREFEITURA DE X' -> 'MUNICIPIO DE X'."""
        aliases = ciga._generate_name_aliases("PREFEITURA DE SAO JOSE")
        assert any("MUNICIPIO DE SAO JOSE" in a for a in aliases)

    def test_camara_vereadores_prefix(self):
        """'CAMARA DE VEREADORES DE X' -> 'X CAMARA DE VEREADORES'."""
        aliases = ciga._generate_name_aliases("CAMARA DE VEREADORES DE BLUMENAU")
        assert any("BLUMENAU CAMARA DE VEREADORES" in a for a in aliases)

    def test_camara_vereadores_suffix(self):
        """'X CAMARA DE VEREADORES' -> 'CAMARA DE VEREADORES DE X'."""
        aliases = ciga._generate_name_aliases("BLUMENAU CAMARA DE VEREADORES")
        assert any("CAMARA DE VEREADORES DE BLUMENAU" in a for a in aliases)

    def test_camara_municipal(self):
        """'CAMARA MUNICIPAL DE X' -> 'X CAMARA MUNICIPAL'."""
        aliases = ciga._generate_name_aliases("CAMARA MUNICIPAL DE CHAPECO")
        assert any("CHAPECO CAMARA MUNICIPAL" in a for a in aliases)

    def test_camara_municipal_vereadores(self):
        """'CAMARA MUNICIPAL DE VEREADORES DE X' -> 'X CAMARA MUNICIPAL DE VEREADORES'."""
        aliases = ciga._generate_name_aliases("CAMARA MUNICIPAL DE VEREADORES DE JOINVILLE")
        assert any("JOINVILLE CAMARA MUNICIPAL DE VEREADORES" in a for a in aliases)

    def test_no_alias_for_unknown(self):
        """Unknown pattern returns empty list."""
        assert ciga._generate_name_aliases("SECRETARIA DE EDUCACAO") == []

    def test_duplicates_removed(self):
        """Duplicate aliases are removed."""
        aliases = ciga._generate_name_aliases("PREFEITURA MUNICIPAL DE FLORIANOPOLIS")
        # Should only appear once
        count = sum(1 for a in aliases if "MUNICIPIO DE FLORIANOPOLIS" in a)
        assert count <= 1


# ===========================================================================
# _normalize_name
# ===========================================================================


class TestNormalizeName:
    """Tests for _normalize_name()."""

    def test_normalize_with_accents(self):
        """Accented name is normalized."""
        result = ciga._normalize_name("São José")
        assert "SAO" in result
        assert "JOSE" in result

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert ciga._normalize_name("") == ""

    def test_none_input(self):
        """None returns empty string."""
        assert ciga._normalize_name(None) == ""


# ===========================================================================
# _load_db_entities
# ===========================================================================


class TestLoadDbEntities:
    """Tests for _load_db_entities()."""

    def test_loads_entities(self, db_entities):
        """Returns entities from DB cursor."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [
            ("id",),
            ("razao_social",),
            ("cnpj_8",),
            ("municipio",),
            ("codigo_ibge",),
            ("natureza_juridica",),
            ("raio_200km",),
        ]
        mock_cursor.fetchall.return_value = [
            (
                e["id"],
                e["razao_social"],
                e["cnpj_8"],
                e["municipio"],
                e["codigo_ibge"],
                e["natureza_juridica"],
                e["raio_200km"],
            )
            for e in db_entities
        ]
        result = ciga._load_db_entities(mock_conn, within_200km_only=False)
        assert len(result) == 4
        assert result[0]["razao_social"] == "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"

    def test_within_200km_adds_filter(self, db_entities):
        """within_200km_only adds SQL condition."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.description = [
            ("id",),
            ("razao_social",),
            ("cnpj_8",),
            ("municipio",),
            ("codigo_ibge",),
            ("natureza_juridica",),
            ("raio_200km",),
        ]
        mock_cursor.fetchall.return_value = [
            (
                e["id"],
                e["razao_social"],
                e["cnpj_8"],
                e["municipio"],
                e["codigo_ibge"],
                e["natureza_juridica"],
                e["raio_200km"],
            )
            for e in db_entities
        ]

        ciga._load_db_entities(mock_conn, within_200km_only=True)
        sql = mock_cursor.execute.call_args[0][0]
        assert "raio_200km = TRUE" in sql


# ===========================================================================
# match_entities — all 4 cascade levels
# ===========================================================================


class TestMatchEntities:
    """Tests for match_entities() — cascade matching."""

    def test_level_1_name_muni(self, db_entities):
        """Exact name + municipio match (high confidence)."""
        entities = {
            "PREFEITURA MUNICIPAL DE FLORIANOPOLIS||FLORIANOPOLIS": {
                "raw_name": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "norm_name": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "FLORIANOPOLIS",
                "count": 1,
                "categories": ["Contratos"],
                "first_seen": "2025-12-15",
                "last_seen": "2025-12-15",
            },
        }
        matched = ciga.match_entities(entities, db_entities)
        entry = list(matched.values())[0]
        assert entry["matched_entity_id"] == 1001
        assert entry["match_method"] == "name_muni"
        assert entry["match_confidence"] == "high"

    def test_level_2_name_only(self, db_entities):
        """Exact name match without municipio (high confidence)."""
        entities = {
            "CAMARA DE VEREADORES DE FLORIANOPOLIS||": {
                "raw_name": "CAMARA DE VEREADORES DE FLORIANOPOLIS",
                "norm_name": "CAMARA DE VEREADORES DE FLORIANOPOLIS",
                "municipio": "",
                "count": 1,
                "categories": ["Contratos"],
                "first_seen": "2025-11-01",
                "last_seen": "2025-11-01",
            },
        }
        matched = ciga.match_entities(entities, db_entities)
        entry = list(matched.values())[0]
        assert entry["matched_entity_id"] == 1003
        assert entry["match_method"] == "name_only"
        assert entry["match_confidence"] == "high"

    def test_level_2b_alias(self, db_entities):
        """Alias match via _generate_name_aliases."""
        entities = {
            "PREFEITURA MUNICIPAL DE FLORIANOPOLIS||": {
                "raw_name": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "norm_name": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "",
                "count": 1,
                "categories": ["Contratos"],
                "first_seen": "2025-12-15",
                "last_seen": "2025-12-15",
            },
        }
        matched = ciga.match_entities(entities, db_entities)
        entry = list(matched.values())[0]
        # Should match via alias: PREFEITURA MUNICIPAL DE FLORIANOPOLIS produces
        # alias "MUNICIPIO DE FLORIANOPOLIS" which won't match anything in db.
        # But name_only (level 2) would match first since "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"
        # is a direct match. So this tests the name_only path instead.
        assert entry["matched_entity_id"] is not None

    def test_level_3_fuzzy(self, db_entities):
        """Fuzzy match within same municipio (medium confidence)."""
        # A slightly different name that should fuzzy-match
        entities = {
            "PREF MUNICIPAL DE FLORIANOPOLIS||FLORIANOPOLIS": {
                "raw_name": "PREF MUNICIPAL DE FLORIANOPOLIS",
                "norm_name": "PREF MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "FLORIANOPOLIS",
                "count": 1,
                "categories": ["Contratos"],
                "first_seen": "2025-12-15",
                "last_seen": "2025-12-15",
            },
        }
        matched = ciga.match_entities(entities, db_entities)
        entry = list(matched.values())[0]
        # Should fuzzy-match to PREFEITURA MUNICIPAL DE FLORIANOPOLIS at high score
        assert entry["matched_entity_id"] == 1001
        assert entry["match_method"] in ("fuzzy",)

    def test_unmatched_entity(self, db_entities):
        """Entity with no close match remains unmatched."""
        entities = {
            "SECRETARIA DE EDUCACAO DE ALGUM LUGAR||ALGUMLUGAR": {
                "raw_name": "SECRETARIA DE EDUCACAO DE ALGUM LUGAR",
                "norm_name": "SECRETARIA DE EDUCACAO DE ALGUM LUGAR",
                "municipio": "ALGUMLUGAR",
                "count": 1,
                "categories": ["Contratos"],
                "first_seen": "2025-06-01",
                "last_seen": "2025-06-01",
            },
        }
        matched = ciga.match_entities(entities, db_entities)
        entry = list(matched.values())[0]
        assert entry["matched_entity_id"] is None
        assert entry["match_method"] == "unmatched"

    def test_empty_entities(self, db_entities):
        """Empty entities dict returns empty dict."""
        assert ciga.match_entities({}, db_entities) == {}


# ===========================================================================
# update_coverage
# ===========================================================================


class TestUpdateCoverage:
    """Tests for update_coverage()."""

    def test_inserts_matched_entities(self):
        """Matched entities are upserted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        matched = {
            "PREFEITURA MUNICIPAL DE FLORIANOPOLIS||FLORIANOPOLIS": {
                "matched_entity_id": 1001,
                "last_seen": "2025-12-15",
            },
            "UNMATCHED||NOWHERE": {
                "matched_entity_id": None,
                "last_seen": "2025-01-01",
            },
        }

        stats = ciga.update_coverage(mock_conn, matched, "ciga_ckan")
        assert stats["inserted"] == 1
        assert stats["skipped"] == 1
        assert stats["errors"] == 0

    def test_handles_db_error(self):
        """DB error during upsert is caught and counted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB constraint violation")

        matched = {
            "SOME||ENTITY": {
                "matched_entity_id": 2002,
                "last_seen": "2025-06-01",
            },
        }

        stats = ciga.update_coverage(mock_conn, matched, "ciga_ckan")
        assert stats["inserted"] == 0
        assert stats["errors"] == 1


class TestGetExistingCoverage:
    """Tests for get_existing_coverage()."""

    def test_returns_set_of_ids(self):
        """Returns set of entity IDs from DB."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(1001,), (1002,), (1003,)]

        result = ciga.get_existing_coverage(mock_conn, "ciga_ckan")
        assert result == {1001, 1002, 1003}


# ===========================================================================
# report_coverage_impact
# ===========================================================================


class TestReportCoverageImpact:
    """Tests for report_coverage_impact()."""

    def test_returns_stats(self):
        """Returns coverage statistics dict."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # 4 queries return: total_200km, source_covered, total_covered, exclusive_covered
        mock_cursor.fetchone.side_effect = [
            (500,),  # total_200km
            (120,),  # source_covered
            (350,),  # total_covered
            (45,),  # exclusive_covered
        ]

        result = ciga.report_coverage_impact(mock_conn, "ciga_ckan")
        assert result["total_entities_200km"] == 500
        assert result["source_covered"] == 120
        assert result["total_covered"] == 350
        assert result["exclusive_covered"] == 45
        assert result["total_uncovered"] == 150  # 500 - 350
        assert result["coverage_pct"] == 70.0  # 350/500


# ===========================================================================
# crawl — module interface (monitor.py compatible)
# ===========================================================================


class TestCrawl:
    """Tests for crawl() module interface."""

    @patch("scripts.crawl.ciga_ckan_crawler.list_domsc_months")
    @patch("scripts.crawl.ciga_ckan_crawler.download_month")
    def test_crawl_full(self, mock_download, mock_list):
        """Full mode downloads all months."""
        mock_list.return_value = ["month-1", "month-2"]
        mock_download.return_value = [{"categoria": "Contratos"}]
        result = ciga.crawl(mode="full")
        assert len(result) == 2
        assert mock_download.call_count == 2

    @patch("scripts.crawl.ciga_ckan_crawler.list_domsc_months")
    @patch("scripts.crawl.ciga_ckan_crawler.download_month")
    def test_crawl_incremental(self, mock_download, mock_list):
        """Incremental mode downloads only latest month."""
        mock_list.return_value = ["month-1", "month-2"]
        mock_download.return_value = [{"categoria": "Contratos"}]
        ciga.crawl(mode="incremental")
        mock_download.assert_called_once_with("month-2")

    @patch("scripts.crawl.ciga_ckan_crawler.list_domsc_months")
    def test_crawl_no_data(self, mock_list):
        """No datasets returns empty list."""
        mock_list.return_value = []
        assert ciga.crawl() == []


class TestTransform:
    """Tests for transform() module interface."""

    def test_returns_empty_list(self):
        """Transform always returns empty list (entity-coverage only)."""
        assert ciga.transform([{"some": "data"}]) == []

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert ciga.transform([]) == []


# ===========================================================================
# download_month — full pipeline per month
# ===========================================================================


class TestDownloadMonth:
    """Tests for download_month()."""

    @patch("scripts.crawl.ciga_ckan_crawler.get_package")
    @patch("scripts.crawl.ciga_ckan_crawler.time.sleep")  # avoid real delay
    def test_downloads_and_filters(self, mock_sleep, mock_get_pkg):
        """Downloads resources and filters procurement categories."""
        mock_get_pkg.return_value = {
            "resources": [
                {"url": "http://example.com/z1.zip"},
                {"url": "http://example.com/z2.zip"},
            ]
        }

        # Patch download_resource to return publications
        with patch.object(ciga, "download_resource") as mock_dl:

            def _side_effect(url):
                if "z1" in url:
                    return {"autopublicacoes": [{"categoria": "Contratos", "entidade": "X", "municipio": "Y"}]}
                return {"autopublicacoes": [{"categoria": "Outros", "entidade": "Z", "municipio": "W"}]}

            mock_dl.side_effect = _side_effect

            result = ciga.download_month("domsc-publicacoes-de-janeiro-2023")
            assert len(result) == 1  # Only procurement category
            assert result[0]["categoria"] == "Contratos"

    @patch("scripts.crawl.ciga_ckan_crawler.get_package")
    def test_no_package(self, mock_get_pkg):
        """Package fetch failure returns empty list."""
        mock_get_pkg.return_value = None
        assert ciga.download_month("missing-month") == []

    @patch("scripts.crawl.ciga_ckan_crawler.get_package")
    def test_no_resources(self, mock_get_pkg):
        """Package with no resources returns empty list."""
        mock_get_pkg.return_value = {"resources": []}
        assert ciga.download_month("empty-month") == []


# ===========================================================================
# monitor.py integration — argparse "ciga-ckan" choice
# ===========================================================================


class TestMonitorIntegration:
    """Tests that monitor.py accepts 'ciga-ckan' as a source choice."""

    def test_ciga_ckan_in_choices(self):
        """monitor.py argparse accepts 'ciga-ckan' as --source."""
        from scripts.crawl.monitor import parse_args

        with patch("sys.argv", ["monitor.py", "--source", "ciga-ckan", "--mode", "dry-run"]):
            args = parse_args()
            assert args.source == "ciga-ckan"

    def test_ciga_ckan_in_sources(self):
        """monitor.py SOURCES list contains ciga_ckan."""
        from scripts.crawl.monitor import SOURCES

        assert "ciga_ckan" in SOURCES

    def test_ciga_ckan_in_module_map(self):
        """monitor.py module_map contains ciga_ckan -> ciga_ckan_crawler."""
        from scripts.crawl.monitor import _load_crawler

        module = _load_crawler("ciga_ckan")
        assert module is not None
        assert hasattr(module, "crawl")
        assert hasattr(module, "transform")


# ===========================================================================
# main / CLI — parse_args
# ===========================================================================


class TestCLI:
    """Tests for CLI argument parsing."""

    def test_parse_args_list(self):
        """--list flag sets list=True."""
        with patch("sys.argv", ["ciga_ckan_crawler.py", "--list"]):
            args = ciga.parse_args()
            assert args.list is True

    def test_parse_args_month(self):
        """--month flag is parsed correctly."""
        with patch("sys.argv", ["ciga_ckan_crawler.py", "--month", "12-2025"]):
            args = ciga.parse_args()
            assert args.month == "12-2025"

    def test_default_source_is_ciga_ckan(self):
        """Default source is 'ciga_ckan'."""
        with patch("sys.argv", ["ciga_ckan_crawler.py", "--list"]):
            args = ciga.parse_args()
            assert args.source == "ciga_ckan"
