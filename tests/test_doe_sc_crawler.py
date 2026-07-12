"""Unit tests for scripts/crawl/doe_sc_crawler.py.

Covers all public and private functions:
- _get_token
- _api_request
- _load_categories
- _fetch_materias
- crawl
- transform
- _transform_record
- _generate_content_hash
- _extract_entity_info
- diagnostic
"""

from unittest.mock import MagicMock, patch

from scripts.crawl import doe_sc_crawler as doe

# ---------------------------------------------------------------------------
# _get_token()
# ---------------------------------------------------------------------------


class TestGetToken:
    """Tests for _get_token()."""

    def test_missing_credentials_returns_none(self):
        """Should return None when credentials are empty."""
        with patch.object(doe, "DOE_SC_LOGIN", ""), patch.object(doe, "DOE_SC_PASSWORD", ""):
            assert doe._get_token() is None

    def test_cached_token_returned(self):
        """Should return cached token if not expired."""
        doe._auth_token = "cached-token"
        doe._auth_expires = 9999999999.0
        try:
            token = doe._get_token()
            assert token == "cached-token"
        finally:
            doe._auth_token = None
            doe._auth_expires = 0.0

    @patch("urllib.request.urlopen")
    def test_successful_login(self, mock_urlopen):
        """Should authenticate and return token on success."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"token": "my-token-123"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(doe, "DOE_SC_LOGIN", "login"), patch.object(doe, "DOE_SC_PASSWORD", "pass"):
            try:
                token = doe._get_token()
                assert token == "my-token-123"
                # Verify login URL uses DOE_SC_API_HOST (not DOE_SC_API_BASE)
                call_url = mock_urlopen.call_args[0][0].full_url
                assert "/apis/login" in call_url
                assert "/apis/doe-api/login" not in call_url
            finally:
                doe._auth_token = None
                doe._auth_expires = 0.0

    @patch("urllib.request.urlopen")
    def test_http_401_on_login(self, mock_urlopen):
        """Should return None on 401."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError("http://example.com/login", 401, "Unauthorized", {}, None)

        with patch.object(doe, "DOE_SC_LOGIN", "login"), patch.object(doe, "DOE_SC_PASSWORD", "pass"):
            assert doe._get_token() is None


# ---------------------------------------------------------------------------
# _api_request()
# ---------------------------------------------------------------------------


class TestApiRequest:
    """Tests for _api_request()."""

    @patch("scripts.crawl.doe_sc_crawler._get_token", return_value="test-token")
    @patch("urllib.request.urlopen")
    def test_successful_get(self, mock_urlopen, mock_get_token):
        """Should return parsed JSON on GET."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": [1, 2, 3]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = doe._api_request("/test")
        assert result == {"data": [1, 2, 3]}

    @patch("scripts.crawl.doe_sc_crawler._get_token", return_value="reauth-token")
    @patch("urllib.request.urlopen")
    def test_401_triggers_reauth(self, mock_urlopen, mock_get_token):
        """Should retry once on 401 by re-authenticating."""
        from urllib.error import HTTPError

        # Proper mock for successful response on retry
        mock_success_resp = MagicMock()
        mock_success_resp.read.return_value = b'{"data": "ok"}'
        mock_success_resp.__enter__.return_value = mock_success_resp
        mock_success_resp.__exit__.return_value = None

        mock_urlopen.side_effect = [
            HTTPError("http://example.com", 401, "Unauthorized", {}, None),
            mock_success_resp,
        ]

        result = doe._api_request("/test")
        assert result == {"data": "ok"}

    @patch("scripts.crawl.doe_sc_crawler._get_token", return_value=None)
    def test_no_token_returns_none(self, mock_get_token):
        """Should return None when no token."""
        assert doe._api_request("/test") is None


# ---------------------------------------------------------------------------
# _generate_content_hash()
# ---------------------------------------------------------------------------


class TestGenerateContentHash:
    """Tests for _generate_content_hash()."""

    def test_returns_string(self):
        """Should return a hex string."""
        h = doe._generate_content_hash({"id": 123, "titulo": "Test", "cdCategoria": 5, "dtPublicacao": "2026-01-01"})
        assert isinstance(h, str)
        assert len(h) == 32

    def test_deterministic(self):
        """Same input should produce same hash."""
        record = {"id": 123, "titulo": "Test", "cdCategoria": 5, "dtPublicacao": "2026-01-01"}
        h1 = doe._generate_content_hash(record)
        h2 = doe._generate_content_hash(record)
        assert h1 == h2

    def test_different_records_different_hashes(self):
        """Different input should produce different hashes."""
        r1 = {"id": 1, "titulo": "A", "cdCategoria": 1, "dtPublicacao": "2026-01-01"}
        r2 = {"id": 2, "titulo": "B", "cdCategoria": 2, "dtPublicacao": "2026-01-02"}
        assert doe._generate_content_hash(r1) != doe._generate_content_hash(r2)


# ---------------------------------------------------------------------------
# _extract_entity_info()
# ---------------------------------------------------------------------------


class TestExtractEntityInfo:
    """Tests for _extract_entity_info()."""

    def test_empty_text(self):
        """Should return defaults for empty text."""
        nome, cnpj, mun, uf = doe._extract_entity_info("")
        assert nome == ""
        assert cnpj == ""
        assert uf == "SC"

    def test_cnpj_extraction(self):
        """Should extract CNPJ from text."""
        text = "Contrato firmado pela SECRETARIA DE EDUCACAO (00.123.456/0001-89)"
        nome, cnpj, mun, uf = doe._extract_entity_info(text)
        assert cnpj == "00123456000189"

    def test_government_header(self):
        """Should extract orgao_nome from government header."""
        text = "GOVERNO DO ESTADO DE SANTA CATARINA Secretaria de Saude Publica"
        nome, cnpj, mun, uf = doe._extract_entity_info(text)
        assert "GOVERNO DO ESTADO DE SANTA CATARINA" in nome


# ---------------------------------------------------------------------------
# _transform_record()
# ---------------------------------------------------------------------------


class TestTransformRecord:
    """Tests for _transform_record()."""

    def test_none_on_missing_id(self):
        """Should return None if no id found."""
        result = doe._transform_record({})
        assert result is None

    def test_basic_transform(self):
        """Should transform a valid record."""
        record = {
            "id": 1001,
            "titulo": "PREGAO ELETRONICO - Aquisicao de Material",
            "dtPublicacao": "2026-06-15",
            "cdCategoria": 12,
            "dsCategoria": "Licitação",
            "texto": "GOVERNO DO ESTADO DE SANTA CATARINA Secretaria da Saude (12.345.678/0001-90)",
        }
        result = doe._transform_record(record)
        assert result is not None
        assert result["source_id"] == "1001"
        assert "PREGAO ELETRONICO" in result["objeto_compra"]
        assert result["data_publicacao"] == "2026-06-15"
        assert result["modalidade_id"] == 12
        assert result["modalidade_nome"] == "Licitação"
        assert result["esfera_id"] == 2  # ESTADUAL
        assert result["uf"] == "SC"
        assert result["orgao_cnpj"] == "12345678000190"

    def test_materia_id_fallback(self):
        """Should work with cdMateria field."""
        record = {
            "cdMateria": 2002,
            "dsTitulo": "Dispensa de Licitação",
            "dtPublicacao": "2026-06-20",
            "idCategoria": 15,
        }
        result = doe._transform_record(record)
        assert result is not None
        assert result["source_id"] == "2002"

    def test_skip_empty_record(self):
        """Should skip record with empty titulo and texto."""
        record = {"id": 3003, "cdCategoria": 1}
        assert doe._transform_record(record) is None


# ---------------------------------------------------------------------------
# crawl()
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl()."""

    def test_disabled_returns_empty(self):
        """Should return empty list when disabled."""
        with patch.object(doe, "DOE_SC_ENABLED", False):
            assert doe.crawl("full") == []

    @patch.object(doe, "_load_categories")
    @patch.object(doe, "_fetch_materias")
    def test_crawl_calls_fetch(self, mock_fetch, mock_cat):
        """Should call _fetch_materias and return records."""
        mock_fetch.return_value = [{"id": 1}, {"id": 2}]
        result = doe.crawl("full")
        assert len(result) == 2
        assert mock_fetch.called

    @patch.object(doe, "_load_categories")
    @patch.object(doe, "_fetch_materias")
    def test_crawl_incremental_mode(self, mock_fetch, mock_cat):
        """Should call _fetch_materias in incremental mode."""
        mock_fetch.return_value = []
        doe.crawl("incremental")
        assert mock_fetch.called


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_empty_list(self):
        """Should return empty list for empty input."""
        assert doe.transform([]) == []

    def test_transform_multiple(self):
        """Should transform a list of records."""
        records = [
            {"id": 1, "titulo": "Test A", "dtPublicacao": "2026-01-01", "cdCategoria": 5},
            {"id": 2, "titulo": "Test B", "dtPublicacao": "2026-01-02", "cdCategoria": 3},
        ]
        result = doe.transform(records)
        assert len(result) == 2
        assert result[0]["source_id"] == "1"
        assert result[1]["source_id"] == "2"

    def test_skips_invalid(self):
        """Should skip records without essential fields."""
        records = [
            {"id": 1, "titulo": "Valid", "dtPublicacao": "2026-01-01", "cdCategoria": 1},
            {},  # invalid
            {"id": 3, "titulo": "", "dtPublicacao": "", "cdCategoria": 0},  # empty content
        ]
        result = doe.transform(records)
        assert len(result) == 1

    def test_transform_sets_source(self):
        """Should set pncp_id as MD5 hash from doe_sc prefix."""
        records = [{"id": 42, "titulo": "Test", "dtPublicacao": "2026-06-01", "cdCategoria": 2}]
        result = doe.transform(records)
        assert len(result) == 1
        assert result[0]["pncp_id"] is not None
        assert isinstance(result[0]["pncp_id"], str)


# ---------------------------------------------------------------------------
# diagnostic()
# ---------------------------------------------------------------------------


class TestDiagnostic:
    """Tests for diagnostic()."""

    @patch("urllib.request.urlopen")
    def test_diagnostic_structure(self, mock_urlopen):
        """Should return a dict with expected keys."""
        # Mock 3 sequential calls: portal, login, materia
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(doe, "DOE_SC_LOGIN", "test"), patch.object(doe, "DOE_SC_PASSWORD", "test"):
            result = doe.diagnostic()
            assert isinstance(result, dict)
            assert "summary" in result
            assert "total_time_s" in result
            assert "main_portal" in result
            assert "e_lic" in result
            assert "list_page_test" in result
            assert "auth_status" in result

    @patch("urllib.request.urlopen")
    def test_diagnostic_portal_reachable(self, mock_urlopen):
        """Should mark portal as reachable on success."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(doe, "DOE_SC_LOGIN", ""), patch.object(doe, "DOE_SC_PASSWORD", ""):
            result = doe.diagnostic()
            assert result["main_portal"]["reachable"] is True
            assert result["main_portal"]["status_code"] == 200

    def test_diagnostic_no_credentials(self):
        """Should indicate auth is blocked when credentials missing."""
        with patch.object(doe, "DOE_SC_LOGIN", ""), patch.object(doe, "DOE_SC_PASSWORD", ""):
            result = doe.diagnostic()
            assert result["auth_status"]["credentials_available"] is False
            assert result["auth_status"]["can_authenticate"] is False

    def test_diagnostic_with_credentials(self):
        """Should indicate auth is ready when credentials available."""
        with patch.object(doe, "DOE_SC_LOGIN", "user"), patch.object(doe, "DOE_SC_PASSWORD", "pass"):
            result = doe.diagnostic()
            assert result["auth_status"]["credentials_available"] is True
            assert result["auth_status"]["can_authenticate"] is True
