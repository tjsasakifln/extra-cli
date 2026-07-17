"""Unit tests for scripts/crawl/sc_compras_crawler.py.

Covers all public and private functions:
- _normalize_modalidade
- _map_modalidade
- _infer_esfera
- _parse_br_date
- _parse_br_number
- _digits_only
- _content_hash
- _normalize_item
- crawl
- transform
"""

from unittest.mock import patch

import pytest

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
    """_extract_table_rows() removed in API refactoring (JSON API replaces HTML scraping)."""

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_extracts_rows_from_table(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_extracts_numero_processo(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_extracts_modalidade(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_extracts_objeto(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_extracts_url_detalhe(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_returns_empty_for_no_table(self):
        pass

    @pytest.mark.skip(reason="_extract_table_rows() removed in API refactoring")
    def test_handles_empty_tbody(self):
        pass


# ---------------------------------------------------------------------------
# _extract_detail_fields()
# ---------------------------------------------------------------------------


class TestExtractDetailFields:
    """_extract_detail_fields() removed in API refactoring (JSON API replaces HTML scraping)."""

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_dl_fields(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_date_fields(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_valor(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_municipio(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_returns_empty_for_no_data(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_handles_empty_html(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_label_span_patterns(self):
        pass

    @pytest.mark.skip(reason="_extract_detail_fields() removed in API refactoring")
    def test_extracts_strong_span_patterns(self):
        pass


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
        raw = [
            {
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
            }
        ]
        result = sc.transform(raw)
        assert len(result) == 1
        record = result[0]

        assert record["pncp_id"] == "sc-2025/00001"
        assert record["objeto_compra"] == "Contratacao de servico de limpeza"
        assert record["valor_total_estimado"] == 150000.0
        assert record["modalidade_id"] == 5
        assert record["modalidade_nome"] == "Pregao Eletronico"
        assert record["esfera_id"] == "2"  # PNCP: Estadual
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
        raw = [
            {
                "numero_processo": "2025/00001",
                "modalidade": "Pregao Eletronico",
                "objeto": "Servico",
                "orgao": "Secretaria de Estado",
                "orgao_cnpj": "12.345.678/0001-99",
                "data_publicacao": "15/06/2025",
            }
        ]
        result = sc.transform(raw)
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
            "status",
            "documentos",
            "api_id",
        }
        assert set(result[0].keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(result[0].keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(result[0].keys())}"
        )

    def test_transform_skips_empty_numero_processo(self):
        """Record without numero_processo is skipped."""
        raw = [
            {
                "numero_processo": "",
                "modalidade": "Pregao",
                "objeto": "Servico",
                "orgao": "Orgao",
            }
        ]
        result = sc.transform(raw)
        assert len(result) == 0

    def test_transform_truncates_long_objeto(self):
        """Objeto longer than 1000 chars is truncated."""
        raw = [
            {
                "numero_processo": "2025/00001",
                "objeto": "X" * 2000,
                "orgao": "Orgao",
            }
        ]
        result = sc.transform(raw)
        assert len(result[0]["objeto_compra"]) == 1000  # 997 + "..."

    def test_transform_estadual_esfera(self):
        """State entities get esfera_id='2' (PNCP Estadual)."""
        raw = [
            {
                "numero_processo": "2025/00001",
                "objeto": "Servico",
                "orgao": "Secretaria de Estado da Educacao",
            }
        ]
        result = sc.transform(raw)
        assert result[0]["esfera_id"] == "2"

    def test_transform_municipal_esfera(self):
        """Municipal entities get esfera_id='3' (PNCP Municipal)."""
        raw = [
            {
                "numero_processo": "2025/00001",
                "objeto": "Servico",
                "orgao": "Prefeitura Municipal de Florianopolis",
            }
        ]
        result = sc.transform(raw)
        assert result[0]["esfera_id"] == "3"


# ---------------------------------------------------------------------------
# crawl() — mocked
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl() with mocked API."""

    @patch("scripts.crawl.sc_compras_crawler._fetch_api_detail", return_value=None)
    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_api_list_meta",
        return_value=([], {"ok": False, "total_elementos": 0}),
    )
    def test_crawl_returns_list(self, mock_list, mock_detail):
        """crawl() returns a list even when API returns no data."""
        result = sc.crawl(mode="full")
        assert isinstance(result, list)

    @patch("scripts.crawl.sc_compras_crawler._fetch_api_detail", return_value=None)
    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_api_list_meta",
        return_value=([], {"ok": False, "total_elementos": 0}),
    )
    def test_crawl_full_default_days(self, mock_list, mock_detail):
        """crawl('full') uses SC_COMPRAS_FULL_DAYS."""
        result = sc.crawl(mode="full")
        assert isinstance(result, list)

    @patch("scripts.crawl.sc_compras_crawler._fetch_api_detail", return_value=None)
    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_api_list_meta",
        return_value=([], {"ok": False, "total_elementos": 0}),
    )
    def test_crawl_incremental(self, mock_list, mock_detail):
        """crawl('incremental') returns a list."""
        result = sc.crawl(mode="incremental")
        assert isinstance(result, list)

    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_api_detail",
        return_value={"id": 1, "modalidade": "Pregao Eletronico"},
    )
    @patch(
        "scripts.crawl.sc_compras_crawler._fetch_api_list_meta",
        return_value=([{"id": 1, "processo": "2025/00001"}], {"ok": True, "total_elementos": 1}),
    )
    def test_crawl_with_items(self, mock_list, mock_detail):
        """crawl() returns items when data is available."""
        result = sc.crawl(mode="full")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Pagination / selection / dedupe helpers
# ---------------------------------------------------------------------------


def _sample_item(i: int, **extra) -> dict:
    base = {
        "id": i,
        "processo": f"{i:04d}/2026",
        "tipo": "Pregão Eletrônico",
        "orgaoSigla": "SED",
        "orgaoNome": "Secretaria de Estado da Educação",
        "objeto": f"Objeto {i}",
        "entregaProposta": None,
        "abertura": None,
        "situacao": "Aberto",
    }
    base.update(extra)
    return base


class TestVirtualPagination:
    def test_virtual_pages_split(self):
        items = [_sample_item(i) for i in range(25)]
        pages = sc._virtual_pages(items, page_size=10)
        assert len(pages) == 3
        assert len(pages[0]) == 10
        assert len(pages[2]) == 5

    def test_page_slice_empty_out_of_range(self):
        items = [_sample_item(1)]
        assert sc._page_slice(items, page=5, page_size=10) == []

    def test_empty_bulk_yields_no_pages(self):
        assert sc._virtual_pages([]) == []


class TestSelectItemsForMode:
    def test_smoke_first_pages(self):
        items = [_sample_item(i) for i in range(1, 51)]
        selected, meta = sc.select_items_for_mode(items, "smoke", max_pages=2, page_size=10)
        assert len(selected) == 20
        assert meta["strategy"] == "first_n_pages"

    def test_incremental_since_checkpoint(self):
        items = [_sample_item(i) for i in range(1, 31)]
        cp = sc.ScComprasCheckpoint(mode="incremental", last_max_id=25)
        selected, meta = sc.select_items_for_mode(
            items, "incremental", checkpoint=cp, max_pages=5, page_size=10
        )
        ids = [it["id"] for it in selected]
        assert ids == [26, 27, 28, 29, 30]
        assert meta["strategy"] == "since_last_max_id"

    def test_incremental_no_checkpoint_takes_newest(self):
        items = [_sample_item(i) for i in range(1, 41)]
        selected, meta = sc.select_items_for_mode(
            items, "incremental", checkpoint=None, max_pages=2, page_size=10
        )
        assert len(selected) == 20
        assert meta["strategy"] == "newest_pages_no_checkpoint"
        assert selected[0]["id"] == 21


class TestDedupe:
    def test_duplicate_detection(self):
        items = [_sample_item(1), _sample_item(1), _sample_item(2)]
        unique, dups = sc.dedupe_by_api_id(items)
        assert len(unique) == 2
        assert dups == 1


class TestMetricsIncomplete:
    def test_empty_fields_and_incomplete(self):
        normalized = [
            {
                "pncp_id": "sc-1",
                "objeto_compra": None,
                "orgao_razao_social": "Orgao",
                "data_publicacao": "2026-01-01",
                "data_abertura": None,
                "data_encerramento": None,
                "valor_total_estimado": None,
                "modalidade_nome": None,
                "municipio": None,
                "orgao_cnpj": None,
                "link_pncp": None,
                "status": None,
                "documentos": [],
                "uf": "SC",
            }
        ]
        from datetime import UTC, datetime

        m = sc.compute_metrics(
            normalized,
            raw_count=1,
            api_total_elementos=100,
            duplicate_count=0,
            started_at=datetime.now(UTC),
            live_fetch=False,
        )
        assert m["incomplete_records"] == 1
        assert m["empty_fields"]["objeto_compra"] == 1
        assert m["empty_fields"]["valor_total_estimado"] == 1
        assert m["api_total_elementos_reported"] == 100
        assert m["non_sc_records"] == 0
        assert m["temporal_range"]["min"] == "2026-01-01"


# ---------------------------------------------------------------------------
# HTTP retry (429 / 500)
# ---------------------------------------------------------------------------


class TestApiRequestRetry:
    def test_retries_on_429_then_success(self):
        import io
        import urllib.error

        ok_body = b'{"conteudo":[]}'
        calls = {"n": 0}

        class FakeResp:
            status = 200

            def read(self):
                return ok_body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(
                    url="https://compras.sc.gov.br/api/editais",
                    code=429,
                    msg="Too Many",
                    hdrs={"Retry-After": "0"},
                    fp=io.BytesIO(b""),
                )
            return FakeResp()

        with (
            patch.object(sc.urllib.request, "urlopen", side_effect=fake_urlopen),
            patch.object(sc.time, "sleep"),
            patch.object(sc, "MAX_RETRIES", 3),
        ):
            data = sc._api_request("https://compras.sc.gov.br/api/editais?ano=2026")
        assert data == {"conteudo": []}
        assert calls["n"] == 2

    def test_retries_on_500_then_fails(self):
        import io
        import urllib.error

        def always_500(req, timeout=None):
            raise urllib.error.HTTPError(
                url="https://compras.sc.gov.br/api/editais",
                code=500,
                msg="Err",
                hdrs=None,
                fp=io.BytesIO(b""),
            )

        with (
            patch.object(sc.urllib.request, "urlopen", side_effect=always_500),
            patch.object(sc.time, "sleep"),
            patch.object(sc, "MAX_RETRIES", 2),
        ):
            data = sc._api_request("https://compras.sc.gov.br/api/editais?ano=2026")
        assert data is None


# ---------------------------------------------------------------------------
# Checkpoint resume + run() pipeline
# ---------------------------------------------------------------------------


class TestCheckpointAndRun:
    def test_checkpoint_save_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path)
        cp = sc.ScComprasCheckpoint(mode="incremental", last_max_id=99, total_fetched=5)
        path = sc.save_checkpoint(cp)
        assert path.is_file()
        loaded = sc.load_checkpoint("incremental")
        assert loaded.last_max_id == 99
        assert loaded.total_fetched == 5

    def test_run_empty_page(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(sc, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(sc, "OUTPUT_DIR", tmp_path / "out")
        art = sc.run(
            mode="smoke",
            ano=2026,
            max_pages=1,
            fetch_detail=False,
            persist=True,
            live_fetch=False,
            preloaded_items=[],
            preloaded_meta={"ok": True, "total_elementos": 0, "ano": 2026},
            run_id="test-empty",
        )
        assert art["run_id"] == "test-empty"
        assert art["records_normalized"] == 0
        assert art["live_fetch"] is False
        assert art["metrics"]["records_raw"] == 0

    def test_run_pagination_two_pages(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(sc, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(sc, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(sc, "PAGE_SIZE", 5)
        items = [_sample_item(i) for i in range(1, 13)]
        art = sc.run(
            mode="smoke",
            ano=2026,
            max_pages=2,
            fetch_detail=False,
            persist=True,
            live_fetch=False,
            preloaded_items=items,
            preloaded_meta={"ok": True, "total_elementos": 100, "ano": 2026},
            run_id="test-pages",
        )
        assert art["records_normalized"] == 10  # 2 pages * 5
        assert art["metrics"]["pages_processed"] == 2
        assert art["metrics"]["api_total_elementos_reported"] == 100
        assert (tmp_path / "raw" / "test-pages" / "page_0000.json").is_file()
        assert (tmp_path / "out" / "test-pages" / "licitacoes.jsonl").is_file()
        assert art["evidence"]["run_id"] == "test-pages"

    def test_checkpoint_resume_skips_seen(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(sc, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(sc, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(sc, "PAGE_SIZE", 10)
        # Seed checkpoint
        sc.save_checkpoint(
            sc.ScComprasCheckpoint(mode="incremental", last_max_id=5, total_fetched=5)
        )
        items = [_sample_item(i) for i in range(1, 11)]
        art = sc.run(
            mode="incremental",
            ano=2026,
            max_pages=2,
            fetch_detail=False,
            persist=True,
            live_fetch=False,
            preloaded_items=items,
            preloaded_meta={"ok": True, "total_elementos": 10, "ano": 2026},
            run_id="test-resume",
        )
        # only ids 6..10
        assert art["records_normalized"] == 5
        assert art["checkpoint"]["last_max_id"] == 10
        assert art["metrics"]["selection"]["strategy"] == "since_last_max_id"

    def test_run_duplicate_metrics(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(sc, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(sc, "OUTPUT_DIR", tmp_path / "out")
        items = [_sample_item(1), _sample_item(1), _sample_item(2)]
        art = sc.run(
            mode="full",
            ano=2026,
            max_pages=1,
            fetch_detail=False,
            persist=True,
            live_fetch=False,
            preloaded_items=items,
            preloaded_meta={"ok": True, "total_elementos": 3, "ano": 2026},
            run_id="test-dups",
        )
        assert art["records_normalized"] == 2
        assert art["metrics"]["duplicates"] >= 1

    def test_run_with_detail_loader(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(sc, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(sc, "OUTPUT_DIR", tmp_path / "out")

        def detail_loader(iid: int) -> dict:
            return {
                "id": iid,
                "modalidade": "Pregão Eletrônico",
                "edital": f"{iid:04d}/2026",
                "dataPublicacao": "2026-03-01",
                "dataAbertura": "2026-03-15T10:00:00",
                "dataEncerramento": None,
                "situacao": "Em Recebimento de Proposta",
                "linkArquivosFTP": f"ftp://example/{iid}",
                "natureza": "Serviços",
            }

        art = sc.run(
            mode="incremental",
            ano=2026,
            max_pages=1,
            fetch_detail=True,
            persist=True,
            live_fetch=False,
            preloaded_items=[_sample_item(7)],
            preloaded_meta={"ok": True, "total_elementos": 1},
            detail_loader=detail_loader,
            run_id="test-detail",
        )
        assert art["records_normalized"] == 1
        # read normalized line
        lines = (tmp_path / "out" / "test-detail" / "licitacoes.jsonl").read_text().strip().splitlines()
        rec = __import__("json").loads(lines[0])
        assert rec["data_publicacao"] == "2026-03-01"
        assert rec["status"] == "Em Recebimento de Proposta"
        assert rec["documentos"]
        assert rec["modalidade_id"] == 5


# ---------------------------------------------------------------------------
# Obsolete test classes (functions removed in API refactoring)
# ---------------------------------------------------------------------------


class TestDiagnostic:
    """Diagnostic removed in API refactoring (no longer an HTML-scraping crawler)."""

    @pytest.mark.skip(reason="sc_compras_crawler.diagnostic() removed in API refactoring")
    def test_diagnostic_returns_expected_structure(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler.diagnostic() removed in API refactoring")
    def test_diagnostic_reachable_summary(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler.diagnostic() removed in API refactoring")
    def test_diagnostic_cloudflare_summary(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler.diagnostic() removed in API refactoring")
    def test_diagnostic_unreachable_summary(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler.diagnostic() removed in API refactoring")
    def test_diagnostic_e_lic_fallback(self):
        pass


class TestCheckUrl:
    """_check_url() removed in API refactoring (no longer needs URL checks)."""

    @pytest.mark.skip(reason="sc_compras_crawler._check_url() removed in API refactoring")
    def test_check_url_success(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler._check_url() removed in API refactoring")
    def test_check_url_cloudflare_detected(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler._check_url() removed in API refactoring")
    def test_check_url_captcha_detected(self):
        pass

    @pytest.mark.skip(reason="sc_compras_crawler._check_url() removed in API refactoring")
    def test_check_url_timeout(self):
        pass
