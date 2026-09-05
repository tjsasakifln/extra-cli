"""Unit tests for scripts/crawl/contracts_crawler.py."""

from unittest.mock import patch

from scripts.crawl import contracts_crawler as cc
from scripts.crawl.pncp_structural_fields import STRUCTURAL_FIELD_KEYS

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_CONTRACT = {
    "numeroControlePNCP": "12345678901234567890",
    "orgaoEntidade": {
        "cnpj": "12345678000199",
        "razaoSocial": "Prefeitura Municipal de Florianopolis",
    },
    "unidadeOrgao": {
        "cnpj": "12345678000199",
        "nomeUnidade": "Secretaria Municipal de Administracao",
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
    },
    "niFornecedor": "11222333000181",
    "tipoPessoa": "PJ",
    "codigoPaisFornecedor": "BR",
    "nomeRazaoSocialFornecedor": "Empresa Exemplo Ltda",
    "valorGlobal": 150000.00,
    "dataAssinatura": "2025-06-15T10:00:00Z",
    "dataVigenciaInicio": "2025-07-01T00:00:00Z",
    "dataVigenciaFim": "2026-06-30T23:59:59Z",
    "objetoContrato": "Prestacao de servicos de limpeza predial",
}

MOCK_CONTRACT_NO_UNIDADE = {
    "numeroControlePNCP": "22345678901234567890",
    "orgaoEntidade": {
        "cnpj": "82888888000120",
        "razaoSocial": "Secretaria de Estado da Saude de SC",
    },
    "unidadeOrgao": {},
    "niFornecedor": "11222333000181",
    "tipoPessoa": "PJ",
    "nomeRazaoSocialFornecedor": "Empresa Exemplo Ltda",
    "valorGlobal": 50000.00,
    "dataAssinatura": "2025-06-15T10:00:00Z",
    "dataVigenciaInicio": "2025-07-01T00:00:00Z",
    "dataVigenciaFim": "2026-06-30T23:59:59Z",
    "objetoContrato": "Servicos de manutencao hospitalar",
}

MOCK_CONTRACT_ZERO_VALUE = {
    "numeroControlePNCP": "32345678901234567890",
    "orgaoEntidade": {
        "cnpj": "12345678000199",
        "razaoSocial": "Prefeitura Municipal de Florianopolis",
    },
    "unidadeOrgao": {
        "cnpj": "12345678000199",
        "nomeUnidade": "Secretaria Municipal de Administracao",
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
    },
    "niFornecedor": "11222333000181",
    "tipoPessoa": "PJ",
    "nomeRazaoSocialFornecedor": "Empresa Exemplo Ltda",
    "valorGlobal": 0,
    "dataAssinatura": "2025-06-20T10:00:00Z",
    "objetoContrato": "Aditivo de prazo sem custo",
}


# ---------------------------------------------------------------------------
# _safe_float()
# ---------------------------------------------------------------------------


class TestSafeFloat:
    """Tests for _safe_float()."""

    def test_safe_float_zero_value(self):
        """_safe_float(0) should NOT return None for zero values."""
        result = cc._safe_float(0)
        assert result is not None, "_safe_float(0) should not return None"
        assert result == 0.0, "_safe_float(0) should return 0.0"

    def test_safe_float_negative(self):
        """_safe_float(-1) should log a warning and return None."""
        with patch.object(cc.logger, "warning") as mock_warn:
            result = cc._safe_float(-1)
            assert result is None
            mock_warn.assert_called_once()
            assert "negative" in mock_warn.call_args[0][0].lower()

    def test_safe_float_positive(self):
        """_safe_float(100.5) should return the value."""
        result = cc._safe_float(100.5)
        assert result == 100.5

    def test_safe_float_string(self):
        """_safe_float('50') should convert from string."""
        result = cc._safe_float("50")
        assert result == 50.0

    def test_safe_float_none(self):
        """_safe_float(None) should return None."""
        result = cc._safe_float(None)
        assert result is None

    def test_safe_float_invalid(self):
        """_safe_float('abc') should return None for invalid input."""
        result = cc._safe_float("abc")
        assert result is None


# ---------------------------------------------------------------------------
# _uf_from_cnpj()
# ---------------------------------------------------------------------------


class TestUfFromCnpj:
    """Tests for _uf_from_cnpj()."""

    def test_uf_extraction_from_cnpj(self):
        """_uf_from_cnpj() should return DF for known federal prefix."""
        # Known pattern: 000000 is in the mapping
        result = cc._uf_from_cnpj("00000000000123")
        assert result == "DF"

    def test_uf_extraction_unknown_cnpj(self):
        """_uf_from_cnpj() should return None for unknown prefix."""
        result = cc._uf_from_cnpj("99222222000123")
        assert result is None

    def test_uf_extraction_empty_cnpj(self):
        """_uf_from_cnpj('') should return None."""
        result = cc._uf_from_cnpj("")
        assert result is None

    def test_uf_extraction_short_cnpj(self):
        """_uf_from_cnpj() with short string should return None."""
        result = cc._uf_from_cnpj("1234567")
        assert result is None


# ---------------------------------------------------------------------------
# _transform_record()
# ---------------------------------------------------------------------------


class TestTransformRecord:
    """Tests for _transform_record()."""

    def test_transform_mock_contract(self):
        """_transform_record() normalizes a contract with all 12 fields."""
        result = cc._transform_record(MOCK_CONTRACT)
        assert result is not None

        # Verify key fields
        assert result["contrato_id"] == "12345678901234567890"
        assert result["orgao_cnpj"] == "12345678000199"
        assert result["orgao_nome"] == "Secretaria Municipal de Administracao"
        assert result["fornecedor_cnpj"] == "11222333000181"
        assert result["supplier_id_type"] == "CNPJ"
        assert result["supplier_identifier"] == "11222333000181"
        assert result["supplier_country"] == "BR"
        assert result["fornecedor_nome"] == "Empresa Exemplo Ltda"
        assert result["objeto_contrato"] == "Prestacao de servicos de limpeza predial"
        assert result["valor_total"] == 150000.00
        assert result["data_inicio"] == "2025-07-01"
        assert result["data_fim"] == "2026-06-30"
        # LEGACY data_publicacao falls back to assinatura when no true pub date
        assert result["data_publicacao"] == "2025-06-15"
        assert result["data_assinatura"] == "2025-06-15"
        assert result["data_publicacao_fonte"] is None
        assert result["source_event_date"] == "2025-06-15"
        assert result["source_date_semantics"] == "dataAssinatura_as_event"
        assert result["uf"] == "SC"
        assert result["municipio"] == "Florianopolis"
        assert result["source_id"] == "12345678901234567890"

        # Core + date-semantics fields (migration 051)
        expected_fields = {
            "contrato_id",
            "orgao_cnpj",
            "orgao_nome",
            "fornecedor_cnpj",
            "supplier_id_type",
            "supplier_identifier",
            "supplier_country",
            "supplier_identifier_hash",
            "supplier_identifier_export",
            "supplier_identity_reason",
            "fornecedor_nome",
            "objeto_contrato",
            "valor_total",
            "data_inicio",
            "data_fim",
            "data_publicacao",
            "data_assinatura",
            "data_publicacao_fonte",
            "data_atualizacao_fonte",
            "source_event_date",
            "source_date_semantics",
            "query_window_start",
            "query_window_end",
            "uf",
            "municipio",
            "source_id",
            "status_raw",
            "status_normalized",
            "status_rule_version",
            "status_source",
            "quality_state",
            "quality_reasons",
            "quality_rule_version",
            "report_ready",
            "canonical_contract_id",
            "source",
            "source_contract_id",
            "parent_procurement_id",
            *STRUCTURAL_FIELD_KEYS,
        }
        assert set(result.keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(result.keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(result.keys())}"
        )

    def test_transform_contract_zero_value(self):
        """_transform_record() should accept contracts with valor=0."""
        result = cc._transform_record(MOCK_CONTRACT_ZERO_VALUE)
        assert result is not None
        assert result["valor_total"] == 0.0, (
            f"Zero-value contract should have valor_total=0.0, got {result['valor_total']}"
        )

    def test_transform_contract_without_ufsigla(self):
        """_transform_record() should NOT presume UF=SC when ufSigla is missing.

        GOAL CRITERION 2: UF is never defaulted to "SC". If ufSigla is absent
        and CNPJ-root lookup fails, UF stays None.
        """
        result = cc._transform_record(MOCK_CONTRACT_NO_UNIDADE)
        assert result is not None
        # orgao_cnpj "82888888000120" is not in _CNPJ_ROOT_UF
        # UF should be None (no fallback to "SC")
        assert result["uf"] is None, (
            f"UF should be None when ufSigla is missing and CNPJ lookup fails. Got: {result['uf']}"
        )
        assert result["municipio"] is None


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns an empty list."""
        result = cc.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_transform_single_record(self):
        """transform() processes a single contract record."""
        result = cc.transform([MOCK_CONTRACT])
        assert len(result) == 1

        record = result[0]
        assert record["contrato_id"] == "12345678901234567890"
        assert record["fornecedor_cnpj"] == "11222333000181"
        assert record["valor_total"] == 150000.00


class TestCrawlWithEvidenceCompletion:
    """Issue #303: source exhaustion, terminal state and checkpoint honesty."""

    @staticmethod
    def _run_one_window(monkeypatch, pages, *, checkpoint=None, max_pages=10):
        responses = iter(pages)
        monkeypatch.setattr(cc, "CONTRACTS_FULL_DAYS", 1)
        monkeypatch.setattr(cc, "CONTRACTS_WINDOW_DAYS", 1)
        monkeypatch.setattr(cc, "CONTRACTS_MAX_PAGES", max_pages)
        monkeypatch.setattr(cc, "CONTRACTS_REQUEST_DELAY", 0)
        monkeypatch.setattr(cc, "CONTRACTS_JANELA_DELAY", 0)
        monkeypatch.setattr(cc, "load_checkpoint", lambda _mode: checkpoint)
        monkeypatch.setattr(cc, "save_checkpoint", lambda _checkpoint: None)
        monkeypatch.setattr(cc, "_fetch_page", lambda *_args: next(responses))
        return cc.crawl_with_evidence(mode="full")

    def test_real_zero_first_page_is_complete(self, monkeypatch):
        result = self._run_one_window(
            monkeypatch,
            [cc.FetchResult(cc.FetchStatus.SUCCESS_ZERO, total_records=0, total_pages=0)],
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.SUCCESS_ZERO
        assert window.request_completed is True
        assert window.scope_complete is True
        assert result.total_windows_ok == 1

    def test_nonempty_single_page_becomes_success_data(self, monkeypatch):
        result = self._run_one_window(
            monkeypatch,
            [
                cc.FetchResult(
                    cc.FetchStatus.SUCCESS_DATA,
                    items=[MOCK_CONTRACT],
                    total_records=1,
                    total_pages=1,
                    current_page=1,
                )
            ],
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.SUCCESS_DATA
        assert window.scope_complete is True
        assert window.records_fetched == 1
        assert result.total_windows_ok == 1

    def test_multiple_pages_require_declared_exhaustion(self, monkeypatch):
        result = self._run_one_window(
            monkeypatch,
            [
                cc.FetchResult(cc.FetchStatus.SUCCESS_DATA, items=[MOCK_CONTRACT], total_records=2, total_pages=2),
                cc.FetchResult(cc.FetchStatus.SUCCESS_DATA, items=[MOCK_CONTRACT], total_records=2, total_pages=2),
            ],
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.SUCCESS_DATA
        assert window.pages_fetched == 2
        assert window.scope_complete is True

    def test_intermediate_failure_is_partial_and_not_checkpointed(self, monkeypatch):
        checkpoint = cc.CrawlCheckpoint(mode="full")
        monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://unused")
        result = self._run_one_window(
            monkeypatch,
            [
                cc.FetchResult(cc.FetchStatus.SUCCESS_DATA, items=[MOCK_CONTRACT], total_records=2, total_pages=2),
                cc.FetchResult(cc.FetchStatus.HTTP_SERVER_ERROR, error_message="HTTP 500", total_pages=2),
            ],
            checkpoint=checkpoint,
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.HTTP_SERVER_ERROR
        assert window.scope_complete is False
        assert checkpoint.completed_windows == []
        assert result.total_windows_failed == 1

    def test_page_cap_is_partial_and_not_checkpointed(self, monkeypatch):
        checkpoint = cc.CrawlCheckpoint(mode="full")
        result = self._run_one_window(
            monkeypatch,
            [cc.FetchResult(cc.FetchStatus.SUCCESS_DATA, items=[MOCK_CONTRACT], total_records=2, total_pages=2)],
            checkpoint=checkpoint,
            max_pages=1,
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.PARTIAL
        assert "Hit CONTRACTS_MAX_PAGES" in (window.error_message or "")
        assert window.scope_complete is False
        assert checkpoint.completed_windows == []
        assert result.total_windows_failed == 1

    def test_incomplete_persistence_is_not_checkpointed(self, monkeypatch):
        checkpoint = cc.CrawlCheckpoint(mode="full")
        monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://unused")
        monkeypatch.setattr(cc, "_persist_window_if_enabled", lambda _items: 0)
        result = self._run_one_window(
            monkeypatch,
            [
                cc.FetchResult(
                    cc.FetchStatus.SUCCESS_DATA,
                    items=[MOCK_CONTRACT],
                    total_records=1,
                    total_pages=1,
                )
            ],
            checkpoint=checkpoint,
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.PARTIAL
        assert "Persistence incomplete" in (window.error_message or "")
        assert checkpoint.completed_windows == []

    def test_complete_persistence_advances_checkpoint(self, monkeypatch):
        checkpoint = cc.CrawlCheckpoint(mode="full")
        monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://unused")
        monkeypatch.setattr(cc, "_persist_window_if_enabled", lambda _items: 1)
        result = self._run_one_window(
            monkeypatch,
            [
                cc.FetchResult(
                    cc.FetchStatus.SUCCESS_DATA,
                    items=[MOCK_CONTRACT],
                    total_records=1,
                    total_pages=1,
                )
            ],
            checkpoint=checkpoint,
        )
        window = result.windows[0]
        assert window.status is cc.FetchStatus.SUCCESS_DATA
        assert window.scope_complete is True
        assert window.persisted_records == 1
        assert len(checkpoint.completed_windows) == 1


# ---------------------------------------------------------------------------
# _trunc()
# ---------------------------------------------------------------------------


class TestTrunc:
    """Tests for trunc()."""

    def test_truncate_long_texts(self):
        """trunc() truncates texts longer than max_len with ellipsis."""
        long_text = "A" * 500
        result = cc.trunc(long_text, 10)
        assert result is not None
        assert len(result) == 10  # 7 chars + "..."
        assert result.endswith("...")

    def test_truncate_short_text(self):
        """trunc() returns short texts unchanged."""
        result = cc.trunc("Short", 100)
        assert result == "Short"

    def test_truncate_none(self):
        """trunc() returns None for None input."""
        result = cc.trunc(None, 100)
        assert result is None

    def test_truncate_empty(self):
        """trunc() returns None for empty string."""
        result = cc.trunc("", 100)
        assert result is None

    def test_truncate_max_len_text(self):
        """trunc() returns texts at max_len unchanged."""
        text = "Exactly10"
        result = cc.trunc(text, 10)
        assert result == text
