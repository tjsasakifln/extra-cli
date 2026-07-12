from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from scripts.crawl import pncp_crawler_adapter as pca
from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult


MOCK_RAW_RECORD = {
    "numeroControlePNCP": "12345678000199-1-000225/2026",
    "objetoCompra": "Contratação de empresa especializada para reforma e instalações elétricas de escola",
    "informacaoComplementar": "Com fornecimento de material e mão de obra",
    "valorTotalEstimado": 500000.00,
    "modalidadeId": 4,
    "modalidadeNome": "Concorrência - Eletrônica",
    "situacaoCompraNome": "Divulgada no PNCP",
    "orgaoEntidade": {
        "cnpj": "12345678000199",
        "razaoSocial": "Prefeitura Municipal de Exemplo",
        "esferaId": "M",
    },
    "unidadeOrgao": {
        "ufSigla": "SC",
        "municipioNome": "Florianópolis",
        "codigoIbge": "4205407",
        "nomeUnidade": "Secretaria de Educação",
    },
    "anoCompra": 2026,
    "sequencialCompra": 225,
    "dataPublicacaoPncp": "2026-07-01T10:00:00",
    "dataAberturaProposta": "2026-08-01T09:00:00",
    "dataEncerramentoProposta": "2026-08-15T18:00:00",
    "linkSistemaOrigem": "https://origem.example/edital/225",
}


class TestFetchPublicationPage:
    def test_http_200_without_records_is_confirmed_empty(self):
        payload = {"data": [], "totalRegistros": 0, "totalPaginas": 0, "numeroPagina": 1, "paginasRestantes": 0, "empty": True}
        body = __import__("json").dumps(payload).encode("utf-8")

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return body

        with patch("urllib.request.urlopen", return_value=Response()):
            result = pca._http_get_json("https://pncp.test")
        assert result.request_completed is True
        assert result.empty_confirmed is True
        assert result.records == []

    def test_invalid_json_is_not_treated_as_empty(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"{invalid"

        with patch("urllib.request.urlopen", return_value=Response()):
            result = pca._http_get_json("https://pncp.test")
        assert result.request_completed is True
        assert result.empty_confirmed is False
        assert result.errors


class TestTransformRecord:
    def test_transform_uses_official_field_names(self):
        result = pca.transform([MOCK_RAW_RECORD])[0]
        assert result["pncp_id"] == "12345678000199-1-000225/2026"
        assert result["numero_controle_pncp"] == "12345678000199-1-000225/2026"
        assert result["uf"] == "SC"
        assert result["municipio"] == "Florianópolis"
        assert result["codigo_municipio_ibge"] == "4205407"
        assert result["data_publicacao"] == "2026-07-01T10:00:00"
        assert result["link_sistema_origem"] == "https://origem.example/edital/225"
        assert result["link_pncp"] == "https://pncp.gov.br/app/editais/12345678000199/2026/225"

    def test_transform_creates_synthetic_id_when_missing_numero_controle(self):
        raw = dict(MOCK_RAW_RECORD)
        raw.pop("numeroControlePNCP")
        result = pca.transform([raw])[0]
        assert result["synthetic_id"] is True
        assert result["synthetic_id_reason"] == "numeroControlePNCP ausente"
        assert result["pncp_id"]


class TestCrawl:
    def test_crawl_returns_fetch_result(self):
        with patch("scripts.crawl.pncp_crawler_adapter._fetch_publication_page") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                records=[],
                request_completed=True,
                http_status=200,
                empty_confirmed=True,
                metadata={"pagination": {"paginasRestantes": 0}},
            )
            result = pca.crawl(CrawlRequest(mode="backfill", date_from=date(2026, 1, 1), date_to=date(2026, 1, 1), limit=1))

        assert isinstance(result, FetchResult)
        assert result.request_completed is True

    def test_crawl_request_limit_stops_total_records(self):
        with patch("scripts.crawl.pncp_crawler_adapter._fetch_publication_page") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                records=[MOCK_RAW_RECORD],
                request_completed=True,
                http_status=200,
                empty_confirmed=False,
                metadata={"pagination": {"paginasRestantes": 0}},
            )
            result = pca.crawl(CrawlRequest(mode="backfill", date_from=date(2026, 1, 1), date_to=date(2026, 1, 1), limit=1))

        assert len(result.records) == 1
        assert mock_fetch.call_count >= 1

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError):
            pca.crawl(CrawlRequest(mode="incremental", target="qualquer_coisa"))
