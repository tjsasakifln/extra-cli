"""Tests for contract date semantics (transform mapping + validators)."""

from datetime import date

from scripts.crawl.contracts_crawler import _transform_record
from scripts.crawl.date_semantics import validate_contract_dates

# ---------------------------------------------------------------------------
# Minimal PNCP-like fixtures
# ---------------------------------------------------------------------------

RAW_ASSINATURA_ONLY = {
    "numeroControlePNCP": "11111111111111111111",
    "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Orgao X"},
    "unidadeOrgao": {
        "nomeUnidade": "Unidade X",
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
    },
    "niFornecedor": "00999999000199",
    "nomeRazaoSocialFornecedor": "Fornecedor Y",
    "valorGlobal": 1000.0,
    "dataAssinatura": "2020-01-15T10:00:00Z",
    "dataVigenciaInicio": "2020-02-01T00:00:00Z",
    "dataVigenciaFim": "2021-01-31T23:59:59Z",
    "objetoContrato": "Contrato antigo assinado em 2020",
}

RAW_WITH_PUBLICACAO_PNCP = {
    "numeroControlePNCP": "22222222222222222222",
    "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Orgao X"},
    "unidadeOrgao": {
        "nomeUnidade": "Unidade X",
        "ufSigla": "SC",
        "municipioNome": "Florianopolis",
    },
    "niFornecedor": "00999999000199",
    "nomeRazaoSocialFornecedor": "Fornecedor Y",
    "valorGlobal": 2500.0,
    "dataAssinatura": "2026-03-01T10:00:00Z",
    "dataPublicacaoPncp": "2026-03-05T12:00:00Z",
    "dataVigenciaInicio": "2026-03-10T00:00:00Z",
    "dataVigenciaFim": "2027-03-09T23:59:59Z",
    "objetoContrato": "Contrato com publicacao PNCP",
}

RAW_FUTURE_ASSINATURA = {
    "numeroControlePNCP": "33333333333333333333",
    "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Orgao X"},
    "unidadeOrgao": {
        "nomeUnidade": "Unidade X",
        "ufSigla": "PR",
        "municipioNome": "Curitiba",
    },
    "niFornecedor": "00999999000199",
    "nomeRazaoSocialFornecedor": "Fornecedor Y",
    "valorGlobal": 500.0,
    "dataAssinatura": "2099-12-31T00:00:00Z",
    "objetoContrato": "Contrato com data futura",
}

RAW_NO_DATES = {
    "numeroControlePNCP": "44444444444444444444",
    "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Orgao X"},
    "unidadeOrgao": {
        "nomeUnidade": "Unidade X",
        "ufSigla": "SC",
        "municipioNome": "Joinville",
    },
    "niFornecedor": "00999999000199",
    "nomeRazaoSocialFornecedor": "Fornecedor Y",
    "valorGlobal": 10.0,
    "objetoContrato": "Sem datas",
}


# ---------------------------------------------------------------------------
# Transform field mapping
# ---------------------------------------------------------------------------


class TestTransformDateSemantics:
    def test_assinatura_only_not_confused_as_true_publication(self):
        """dataAssinatura must not be the only meaning of data_publicacao_fonte."""
        row = _transform_record(RAW_ASSINATURA_ONLY)
        assert row is not None
        assert row["data_assinatura"] == "2020-01-15"
        assert row["data_publicacao_fonte"] is None
        assert row["source_event_date"] == "2020-01-15"
        # Legacy column still populated for backward compat (fallback to assinatura)
        assert row["data_publicacao"] == "2020-01-15"
        assert row["source_date_semantics"] == "dataAssinatura_as_event"

    def test_publicacao_pncp_preferred_over_assinatura(self):
        row = _transform_record(RAW_WITH_PUBLICACAO_PNCP)
        assert row is not None
        assert row["data_assinatura"] == "2026-03-01"
        assert row["data_publicacao_fonte"] == "2026-03-05"
        assert row["data_publicacao"] == "2026-03-05"  # true pub preferred for legacy
        assert row["source_event_date"] == "2026-03-01"  # assinatura is act date
        assert row["source_date_semantics"] == "dataPublicacaoPncp"

    def test_generic_data_publicacao_fallback(self):
        raw = {
            **RAW_ASSINATURA_ONLY,
            "numeroControlePNCP": "55555555555555555555",
            "dataAssinatura": "2025-01-01T00:00:00Z",
            "dataPublicacao": "2025-01-10T00:00:00Z",
        }
        row = _transform_record(raw)
        assert row is not None
        assert row["data_publicacao_fonte"] == "2025-01-10"
        assert row["source_date_semantics"] == "dataPublicacao"
        assert row["data_publicacao"] == "2025-01-10"

    def test_no_dates_semantics_unknown(self):
        row = _transform_record(RAW_NO_DATES)
        assert row is not None
        assert row["data_assinatura"] is None
        assert row["data_publicacao_fonte"] is None
        assert row["data_publicacao"] is None
        assert row["source_event_date"] is None
        assert row["source_date_semantics"] == "unknown"

    def test_query_window_passthrough(self):
        raw = {
            **RAW_ASSINATURA_ONLY,
            "numeroControlePNCP": "66666666666666666666",
            "_query_window_start": "2026-01-01",
            "_query_window_end": "2026-01-30",
        }
        row = _transform_record(raw)
        assert row is not None
        assert row["query_window_start"] == "2026-01-01"
        assert row["query_window_end"] == "2026-01-30"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestValidateContractDates:
    def test_missing_all_dates(self):
        warnings = validate_contract_dates({})
        assert "missing_all_dates" in warnings

    def test_future_date(self):
        warnings = validate_contract_dates(
            {"data_assinatura": "2099-12-31", "source_event_date": "2099-12-31"},
            today=date(2026, 7, 16),
        )
        assert any(w.startswith("future_date") for w in warnings)

    def test_future_grace_one_day_ok(self):
        """today+1 is allowed; only > today+1 flags."""
        warnings = validate_contract_dates(
            {"data_assinatura": "2026-07-17", "source_event_date": "2026-07-17"},
            today=date(2026, 7, 16),
        )
        assert not any(w.startswith("future_date") for w in warnings)

    def test_assinatura_ne_publicacao(self):
        warnings = validate_contract_dates(
            {
                "data_assinatura": "2026-03-01",
                "data_publicacao_fonte": "2026-03-05",
                "source_event_date": "2026-03-01",
            },
            today=date(2026, 7, 16),
        )
        assert "assinatura_ne_publicacao" in warnings

    def test_outside_query_window(self):
        warnings = validate_contract_dates(
            {
                "data_assinatura": "2020-01-15",
                "source_event_date": "2020-01-15",
                "source_date_semantics": "dataAssinatura_as_event",
            },
            query_start=date(2026, 4, 1),
            query_end=date(2026, 6, 30),
            today=date(2026, 7, 16),
        )
        assert "outside_query_window" in warnings

    def test_inside_query_window_clean(self):
        warnings = validate_contract_dates(
            {
                "data_assinatura": "2026-05-10",
                "source_event_date": "2026-05-10",
                "source_date_semantics": "dataAssinatura_as_event",
            },
            query_start="2026-04-01",
            query_end="2026-06-30",
            today=date(2026, 7, 16),
        )
        assert warnings == []

    def test_unknown_semantics_skips_window_check(self):
        warnings = validate_contract_dates(
            {
                "data_assinatura": "2020-01-15",
                "source_event_date": "2020-01-15",
                "source_date_semantics": "unknown",
            },
            query_start=date(2026, 4, 1),
            query_end=date(2026, 6, 30),
            today=date(2026, 7, 16),
        )
        assert "outside_query_window" not in warnings

    def test_validate_on_transformed_row(self):
        row = _transform_record(RAW_FUTURE_ASSINATURA)
        assert row is not None
        warnings = validate_contract_dates(row, today=date(2026, 7, 16))
        assert any(w.startswith("future_date") for w in warnings)
