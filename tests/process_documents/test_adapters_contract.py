"""Adapter contract tests with mocked HTTP — shipped adapter code paths."""

from __future__ import annotations

from unittest.mock import patch

from scripts.process_documents.adapters.base import classify_http_status, get_adapter
from scripts.process_documents.adapters.pncp import PncpDocumentAdapter
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus


def _entity() -> EntityDocumentDiscovery:
    return EntityDocumentDiscovery(
        canonical_id="82892324:MUNICIPIO_TEST",
        razao_social="MUNICIPIO TESTE",
        cnpj="82892324000100",
        municipio="FLORIANOPOLIS",
        uf="SC",
        applicability="applicable",
        applicability_reason="test",
        institutional_site="https://example.invalid",
        transparency_portal=None,
        procurement_portal=None,
        dispute_platform=None,
        admin_process_system=None,
        pncp_source="https://pncp.gov.br",
        portal_family="pncp",
        capabilities=["notice_documents"],
        access_status="mapped",
        last_verified_at="t",
        blocker=None,
        collection_strategy="pncp_compra_arquivos",
        fallback_strategy="html",
        platforms=["pncp"],
    )


def test_classify_http_status() -> None:
    assert classify_http_status(429) == DocumentRunStatus.HTTP_RATE_LIMIT
    assert classify_http_status(403) == DocumentRunStatus.AUTH_REQUIRED
    assert classify_http_status(500) == DocumentRunStatus.HTTP_SERVER_ERROR
    assert classify_http_status(404) == DocumentRunStatus.HTTP_CLIENT_ERROR


def test_get_adapter_pncp() -> None:
    ad = get_adapter("pncp")
    assert isinstance(ad, PncpDocumentAdapter)


def test_pncp_timeout_not_success_zero(tmp_path) -> None:
    adapter = PncpDocumentAdapter(raw_root=tmp_path / "raw", meta_root=tmp_path / "meta", max_retries=1, request_delay=0)
    with patch.object(adapter, "_get", return_value=(None, None, "timeout: read")):
        result = adapter.collect(_entity(), max_processes=1, download=False)
    assert result.status == DocumentRunStatus.CONNECTION_FAILED
    assert result.status != DocumentRunStatus.SUCCESS_ZERO


def test_pncp_success_zero_with_empty_window(tmp_path) -> None:
    adapter = PncpDocumentAdapter(raw_root=tmp_path / "raw", meta_root=tmp_path / "meta", max_retries=1, request_delay=0)

    def fake_get(url, params=None):
        if "publicacao" in url:
            return 200, {"data": [], "totalPaginas": 1, "totalRegistros": 0}, None
        return 200, [], None

    with patch.object(adapter, "_get", side_effect=fake_get):
        result = adapter.collect(_entity(), max_processes=1, download=True, since="2026-01-01", until="2026-01-31")
    assert result.status == DocumentRunStatus.SUCCESS_ZERO
    assert result.success_zero_justification
    result.validate_fail_closed()


def test_pncp_download_and_cas(tmp_path) -> None:
    adapter = PncpDocumentAdapter(raw_root=tmp_path / "raw", meta_root=tmp_path / "meta", max_retries=1, request_delay=0)
    proc = {
        "orgaoEntidade": {"cnpj": "82892324000100"},
        "anoCompra": 2026,
        "sequencialCompra": 1,
        "numeroControlePNCP": "82892324000100-1-000001/2026",
        "dataPublicacaoPncp": "2026-01-15",
        "objetoCompra": "Obra de pavimentação",
    }
    arquivo = {"titulo": "Edital.pdf", "url": "https://pncp.gov.br/fake/edital.pdf"}

    def fake_get(url, params=None):
        if "publicacao" in url:
            return 200, {"data": [proc], "totalPaginas": 1}, None
        if "arquivos" in url and not url.endswith(".pdf"):
            return 200, [arquivo], None
        return 200, [], None

    pdf = b"%PDF-1.4 fake edital content for test"
    with patch.object(adapter, "_get", side_effect=fake_get):
        with patch.object(adapter, "_download_bytes", return_value=(None, pdf, "application/pdf", None)):
            result = adapter.collect(_entity(), max_processes=1, download=True, since="2026-01-01", until="2026-01-31")
    assert result.status == DocumentRunStatus.SUCCESS_NONZERO
    assert result.documents_downloaded == 1
    assert result.documents[0].sha256
    assert result.documents[0].document_category == "edital"
    # second run unchanged
    with patch.object(adapter, "_get", side_effect=fake_get):
        with patch.object(adapter, "_download_bytes", return_value=(None, pdf, "application/pdf", None)):
            result2 = adapter.collect(_entity(), max_processes=1, download=True, since="2026-01-01", until="2026-01-31")
    assert result2.documents_unchanged == 1 or result2.documents_downloaded == 1


def test_pncp_partial_download_fail_closed(tmp_path) -> None:
    adapter = PncpDocumentAdapter(raw_root=tmp_path / "raw", meta_root=tmp_path / "meta", max_retries=1, request_delay=0)
    proc = {
        "orgaoEntidade": {"cnpj": "82892324000100"},
        "anoCompra": 2026,
        "sequencialCompra": 1,
        "numeroControlePNCP": "x",
    }
    arquivo = {"titulo": "Anexo.pdf", "url": "https://pncp.gov.br/fake/a.pdf"}

    def fake_get(url, params=None):
        if "publicacao" in url:
            return 200, {"data": [proc], "totalPaginas": 1}, None
        if "arquivos" in url:
            return 200, [arquivo], None
        return 200, [], None

    with patch.object(adapter, "_get", side_effect=fake_get):
        with patch.object(
            adapter,
            "_download_bytes",
            return_value=(DocumentRunStatus.TIMEOUT, None, None, "timeout"),
        ):
            result = adapter.collect(_entity(), max_processes=1, download=True)
    assert result.status == DocumentRunStatus.DOWNLOAD_INCOMPLETE
    assert result.status not in (DocumentRunStatus.SUCCESS_ZERO, DocumentRunStatus.SUCCESS_NONZERO)
