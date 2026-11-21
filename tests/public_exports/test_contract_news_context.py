from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.public_exports import contract_news_context as context
from scripts.public_exports import pdf_extract

NOW = dt.datetime(2026, 11, 20, 16, 0, tzinfo=dt.UTC)
CONTRACT = "19493732000199-2-000329/2026"
PURCHASE = "19493732000199-1-000101/2026"


def response(url, body):
    return context.EvidenceResponse(url, 200, json.dumps(body, ensure_ascii=False).encode())


def purchase(**changes):
    value = {
        "numeroControlePNCP": PURCHASE,
        "orgaoEntidade": {"cnpj": "19493732000199"},
        "numeroCompra": "36", "processo": "102", "modalidadeNome": "Credenciamento",
        "modoDisputaNome": "Não se aplica", "tipoInstrumentoConvocatorioNome": "Edital de Chamamento Público",
        "amparoLegal": {"nome": "Lei 14.133/2021, Art. 79, I", "descricao": "Contratação paralela e não excludente."},
        "objetoCompra": "Credenciamento de empresas para revitalização de praças e passeios públicos.",
        "valorTotalEstimado": "139800261.37", "valorTotalHomologado": None,
        "dataPublicacaoPncp": "2026-09-25T16:27:58", "dataAberturaProposta": "2026-09-25T08:30:00",
        "dataEncerramentoProposta": None,
    }
    return {**value, **changes}


def documents(identity=CONTRACT, count=2):
    return [{"sequencialDocumento": i, "titulo": f"Contrato de execução {i}",
             "url": context.document_urls(identity, i)} for i in range(1, count + 1)]


def record(identity=CONTRACT, value="139800261.37"):
    return {"id": identity, "value": {"amount": value}, "object": "Obras de revitalização de praças e passeios públicos."}


def contract_payload(purchase_id=PURCHASE):
    return {"numeroControlePncpCompra": purchase_id, "numeroContratoEmpenho": "698/2026-10-22",
            "tipoContrato": {"nome": "Contrato (termo inicial)"}, "categoriaProcesso": {"nome": "Serviços de Engenharia"}}


def pdf_bytes(pages=1, empty_pages=()):
    """Small valid PDF builder, parsed by the real vendored library in tests."""
    content = (b"BT /F1 12 Tf 30 700 Td (Contrato para iluminacao de praca publica. "
               b"A medicao depende dos servicos executados e dos documentos de suporte. "
               b"Esta e uma fixture documental sintetica.) Tj ET")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               (f"<< /Type /Pages /Count {pages} /Kids [" + " ".join(f"{4 + i * 2} 0 R" for i in range(pages))
                + "] >>").encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i in range(pages):
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + i * 2} 0 R >>").encode())
        page_content = b"" if i + 1 in empty_pages else content
        objects.append(f"<< /Length {len(page_content)} >>\nstream\n".encode() + page_content + b"\nendstream")
    raw = b"%PDF-1.4\n"
    offsets = []
    for number, value in enumerate(objects, 1):
        offsets.append(len(raw))
        raw += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(raw)
    raw += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    raw += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return raw + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def test_purchase_context_is_identity_bound_and_preserves_estimate_semantics():
    url = context.purchase_urls(PURCHASE)[1]
    source = response(url, purchase())
    result = context.normalize_purchase(source, PURCHASE, NOW)
    assert result["source_api_url"] == "https://pncp.gov.br/api/consulta/v1/orgaos/19493732000199/compras/2026/101"
    assert result["source_url"] == "https://pncp.gov.br/app/editais/19493732000199/2026/101"
    assert result["estimated_value"] == {"amount": "139800261.37", "currency": "BRL"}
    assert result["awarded_value"] is None
    assert result["modality"] == "Credenciamento"
    assert result["published_at"] == "2026-09-25T19:27:58Z"
    assert result["source_sha256"] == hashlib.sha256(source.body).hexdigest()


@pytest.mark.parametrize("changes", [
    {"numeroControlePNCP": "19493732000199-1-000102/2026"},
    {"orgaoEntidade": {"cnpj": "11222333000181"}},
    {"orgaoEntidade": None},
    {"valorTotalEstimado": "NaN"},
    {"valorTotalEstimado": True},
    {"valorTotalHomologado": "-1"},
    {"valorTotalHomologado": "1.12345"},
    {"dataPublicacaoPncp": "not-a-date"},
])
def test_inconsistent_procurement_is_not_an_evidence_source(changes):
    with pytest.raises(context.ContextError):
        context.normalize_purchase(response(context.purchase_urls(PURCHASE)[1], purchase(**changes)), PURCHASE, NOW)


def test_moved_endpoint_error_with_http_200_cannot_be_reported_as_procurement():
    moved = {"status": "301", "message": "Moved to port 59035", "error": "301 MOVED_PERMANENTLY"}
    with pytest.raises(context.ContextError, match="identity_mismatch"):
        context.normalize_purchase(response(context.purchase_urls(PURCHASE)[1], moved), PURCHASE, NOW)


@pytest.mark.parametrize("url", [
    "https://pncp.gov.br.evil.test/doc.pdf", "https://127.0.0.1/private",
    "https://pncp.gov.br:59035/api/consulta/v1/orgaos/19493732000199/compras/2026/101",
    "https://pncp.gov.br/pncp-api/v1/orgaos/19493732000199/contratos/2026/328/arquivos/1",
    "https://pncp.gov.br/pncp-api/v1/orgaos/19493732000199/contratos/2026/329/arquivos/1?token=secret",
])
def test_document_lists_cannot_redirect_evidence_to_unrelated_urls(url):
    values = documents(count=1)
    values[0]["url"] = url
    with pytest.raises(context.ContextError, match="unbound_document"):
        context.normalize_document_list(response(context.document_urls(CONTRACT), values), CONTRACT)


def test_more_than_three_documents_is_explicitly_incomplete_and_sorted():
    rows, total = context.normalize_document_list(response(context.document_urls(CONTRACT), documents(count=5)[::-1]), CONTRACT)
    assert [row["id"] for row in rows] == ["1", "2", "3"]
    assert total == 5


def test_procurement_cache_and_documentary_limit_do_not_change_source_values():
    records = [record(f"19493732000199-2-{index:06d}/2026", str(index * 100)) for index in range(1, 21)]
    payloads = {row["id"]: contract_payload() for row in records}
    calls = []

    def fetch(url, limit, timeout):
        calls.append(url)
        assert 0 < timeout <= 15
        if "/compras/" in url:
            return response(url, purchase())
        return response(url, [])

    summary = context.enrich_records(records, payloads, recheck_ids=[records[0]["id"]], clock=lambda: NOW, fetch=fetch)
    assert summary["context_purchase_requests"] == 1
    assert summary["context_document_list_requests"] == 2
    assert summary["context_requests"] == len(calls) == 3
    assert records[0]["editorial_context"]["documents_status"] == "complete"
    assert sum(row["editorial_context"]["documents_status"] == "complete" for row in records[1:]) == 1
    assert records[0]["value"]["amount"] == "100"


def test_distinct_purchase_limit_is_independent_of_contract_identity():
    records = [record(f"19493732000199-2-{index:06d}/2026", str(index * 100)) for index in range(1, 21)]
    payloads = {row["id"]: contract_payload(row["id"].replace("-2-", "-1-")) for row in records}
    calls = []

    def fetch(url, limit, timeout):
        calls.append(url)
        if "/compras/" not in url:
            return response(url, [])
        sequence = int(url.rsplit("/", 1)[1])
        return response(url, purchase(numeroControlePNCP=f"19493732000199-1-{sequence:06d}/2026"))

    summary = context.enrich_records(records, payloads, recheck_ids=[], clock=lambda: NOW, fetch=fetch)
    assert summary["context_purchase_requests"] == 5
    assert summary["context_requests"] == len(calls) == 7
    assert sum(bool(row["editorial_context"]["procurement"]) for row in records) == 5


def test_stable_published_records_cannot_consume_both_documentary_slots(monkeypatch):
    old_first = "19493732000199-2-000301/2026"
    old_second = "19493732000199-2-000302/2026"
    new = "19493732000199-2-000303/2026"
    # The consumer intentionally asks to review the smaller old record first.
    rows = [record(old_second, "99999999"), record(old_first, "500000"), record(new, "100")]
    source = {row["id"]: contract_payload(row["id"].replace("-2-", "-1-")) for row in rows}
    called = []
    monkeypatch.setattr(context.shutil, "which", lambda name: None)

    def fetch(url, limit, timeout):
        called.append(url)
        if "/compras/" in url:
            sequence = int(url.rsplit("/", 1)[1])
            return response(url, purchase(numeroControlePNCP=f"19493732000199-1-{sequence:06d}/2026"))
        if url.endswith("/arquivos"):
            identity = next(row["id"] for row in rows if context.document_urls(row["id"]) == url)
            return response(url, documents(identity=identity, count=1))
        return context.EvidenceResponse(url, 200, pdf_bytes())

    summary = context.enrich_records(rows, source, recheck_ids=[old_first, old_second], clock=lambda: NOW, fetch=fetch)
    observed = {row["id"]: row["editorial_context"]["documents_status"] for row in rows}
    assert observed == {old_first: "complete", old_second: "not_collected", new: "complete"}
    new_context = next(row for row in rows if row["id"] == new)["editorial_context"]
    assert len(new_context["documents"]) == 1
    assert "iluminacao de praca publica" in new_context["documents"][0]["text"]
    assert [url for url in called if url.endswith("/arquivos")] == [
        context.document_urls(old_first), context.document_urls(new),
    ]
    assert [url for url in called if "/compras/" in url][:2] == [
        context.purchase_urls(old_first.replace("-2-", "-1-"))[1],
        context.purchase_urls(new.replace("-2-", "-1-"))[1],
    ]
    assert summary["context_document_list_requests"] == 2


def test_next_four_hour_window_moves_past_an_unreadable_new_candidate():
    old = "19493732000199-2-000301/2026"
    new_ids = [f"19493732000199-2-{number:06d}/2026" for number in range(302, 310)]
    new_by_url = {context.document_urls(identity): identity for identity in new_ids}

    def run(at):
        rows = [record(old, "99999999"), *[record(identity, str(1000 - i)) for i, identity in enumerate(new_ids)]]
        source = {row["id"]: contract_payload(None) for row in rows}
        called = []

        def fetch(url, limit, timeout):
            called.append(url)
            if url == context.document_urls(old):
                return response(url, [])
            raise context.ContextError("evidence_transport_unavailable")

        summary = context.enrich_records(rows, source, recheck_ids=[old], clock=lambda: at, fetch=fetch)
        assert summary["context_requests"] == 1 + context.MAX_NEW_DOCUMENT_PROBES
        assert context.document_urls(old) in called
        return next(new_by_url[url] for url in called if url in new_by_url)

    first = run(NOW)
    assert run(NOW + dt.timedelta(minutes=30)) == first
    second = run(NOW + dt.timedelta(hours=4))
    assert second == new_ids[(new_ids.index(first) + 1) % len(new_ids)]
    # Every position is reached, including positions after the sixth daily run.
    assert {run(NOW + dt.timedelta(hours=4 * offset)) for offset in range(len(new_ids))} == set(new_ids)


def test_failed_new_dossier_falls_back_in_same_batch_with_a_recheck():
    old = "19493732000199-2-000301/2026"
    blocked = "19493732000199-2-000302/2026"
    ready = "19493732000199-2-000303/2026"
    rows = [record(old, "900"), record(blocked, "200"), record(ready, "100")]
    now = dt.datetime.fromtimestamp(2 * context.DOCUMENT_ROTATION_SECONDS, dt.UTC)

    def fetch(url, limit, timeout):
        if url.endswith("/arquivos"):
            identity = next(row["id"] for row in rows if context.document_urls(row["id"]) == url)
            return response(url, documents(identity=identity, count=1))
        if url == context.document_urls(blocked, 1):
            raise context.ContextError("evidence_response_unavailable")
        return context.EvidenceResponse(url, 200, b"%PDF-1.7 fixture")

    summary = context.enrich_records(
        rows, {row["id"]: contract_payload(None) for row in rows}, recheck_ids=[old], clock=lambda: now,
        fetch=fetch, extract_pdf=lambda raw, timeout: {"text": "Confirmed clause.", "pages": 1},
    )
    statuses = {row["id"]: row["editorial_context"]["documents_status"] for row in rows}
    assert statuses == {old: "complete", blocked: "unavailable", ready: "complete"}
    assert summary["context_document_list_requests"] == summary["context_document_requests"] == 3


def test_rechecks_without_new_candidates_retain_both_slots_and_consumer_order():
    ids = ["19493732000199-2-000301/2026", "19493732000199-2-000302/2026", "19493732000199-2-000303/2026"]
    rows = [record(identity, str(i * 1000)) for i, identity in enumerate(ids, 1)]
    called = []

    def fetch(url, limit, timeout):
        called.append(url)
        return response(url, [])

    context.enrich_records(rows, {row["id"]: contract_payload(None) for row in rows},
                           recheck_ids=ids, clock=lambda: NOW, fetch=fetch)
    assert called == [context.document_urls(ids[0]), context.document_urls(ids[1])]


def test_failed_document_is_partial_not_fabricated_complete_evidence():
    row = record()
    seen = []

    def fetch(url, limit, timeout):
        seen.append(url)
        if url.endswith("/arquivos"):
            return response(url, documents(count=2))
        if url.endswith("/arquivos/1"):
            return context.EvidenceResponse(url, 200, b"%PDF-1.7 fixture")
        raise context.ContextError("evidence_transport_unavailable")

    summary = context.enrich_records([row], {CONTRACT: contract_payload(None)}, recheck_ids=[], clock=lambda: NOW,
                                    fetch=fetch, extract_pdf=lambda raw, timeout: {"text": "Confirmed clause.", "pages": 1})
    result = row["editorial_context"]
    assert result["documents_status"] == "partial"
    assert result["documents_total"] == 2
    assert [doc["id"] for doc in result["documents"]] == ["1"]
    assert result["documents"][0]["sha256"] == hashlib.sha256(b"%PDF-1.7 fixture").hexdigest()
    assert summary["context_errors"] == {"evidence_transport_unavailable": 1}
    assert summary["context_requests"] == len(seen) == 3


def test_time_budget_stops_network_without_losing_confirmed_contract_facts():
    row = record()
    fetch = Mock()
    # First call establishes deadline, all subsequent attempts are expired.
    ticks = iter([0, 122, 122, 122])
    summary = context.enrich_records([row], {CONTRACT: contract_payload()}, recheck_ids=[], clock=lambda: NOW,
                                    fetch=fetch, monotonic=lambda: next(ticks))
    fetch.assert_not_called()
    assert summary["context_requests"] == 0
    assert row["value"]["amount"] == "139800261.37"
    assert row["editorial_context"]["documents_status"] == "unavailable"
    assert summary["context_errors"]["context_time_budget_exhausted"] == 2


def test_pdf_fallback_works_without_poppler_or_site_packages(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: None)
    result = context.extract_pdf_text(pdf_bytes(), timeout=5)
    assert result["pages"] == 1
    assert "iluminacao de praca publica" in result["text"]
    assert result["text_pages"] == 1
    assert result["pages_without_text"] == []


def test_pdf_fallback_discloses_pages_without_text_without_claiming_visual_read(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: None)
    result = context.extract_pdf_text(pdf_bytes(pages=2, empty_pages=(2,)), timeout=5)
    assert result["pages"] == 2
    assert result["text_pages"] == 1
    assert result["pages_without_text"] == [2]
    assert "não foram interpretadas" in result["extraction_note"]


def test_pdf_dependency_tampering_is_rejected(tmp_path):
    original = pdf_extract.verified_wheel()
    modified = tmp_path / pdf_extract.PYPDF_WHEEL
    modified.parent.mkdir(parents=True)
    modified.write_bytes(original.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="pdf_dependency_digest_mismatch"):
        pdf_extract.verified_wheel(tmp_path)


def test_fallback_rejects_more_than_twenty_pages(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: None)
    with pytest.raises(context.ContextError, match="page_limit"):
        context.extract_pdf_text(pdf_bytes(pages=21), timeout=5)


@pytest.mark.parametrize("raw", [b"not a PDF", b"%PDF-1.7" + b"x" * context.MAX_PDF_BYTES])
def test_non_pdf_and_oversize_documents_fail_before_tools(raw, monkeypatch):
    run = Mock()
    monkeypatch.setattr(context.subprocess, "run", run)
    with pytest.raises(context.ContextError, match="document_not_bounded_pdf"):
        context.extract_pdf_text(raw)
    run.assert_not_called()


def test_pdf_extraction_enforces_pages_and_sanitizes_contact_evidence(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs["timeout"] == 3
        assert kwargs["preexec_fn"] == context._pdf_limits
        if argv[0].endswith("pdfinfo"):
            return SimpleNamespace(returncode=0, stdout="Pages: 2\nEncrypted: no\n")
        Path(argv[-1]).write_text("Contrato de execução com objeto de iluminação e medição por serviço realizado. " * 2
                                 + " CPF 123.456.789-00, contato ana@example.com e telefone (48) 99999-0000.")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(context.subprocess, "run", run)
    extracted = context.extract_pdf_text(b"%PDF-1.7 fixture", 3)
    assert extracted["pages"] == 2
    assert "iluminação" in extracted["text"]
    for private in ["123.456.789-00", "ana@example.com", "99999-0000"]:
        assert private not in extracted["text"]
    assert len(calls) == 2


def test_excessive_pages_prevents_text_extraction(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: "/usr/bin/" + name)
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="Pages: 21\nEncrypted: no\n"))
    monkeypatch.setattr(context.subprocess, "run", run)
    with pytest.raises(context.ContextError, match="page_limit"):
        context.extract_pdf_text(b"%PDF-1.7 fixture")
    assert run.call_count == 1


def test_pdf_subprocess_timeout_is_stable_and_keeps_raw_details_private(monkeypatch):
    monkeypatch.setattr(context.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(context.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("secret document name", 2)))
    with pytest.raises(context.ContextError, match="^document_extraction_unavailable$"):
        context.extract_pdf_text(b"%PDF-1.7 fixture")


def test_context_decimal_zero_stays_zero_not_missing():
    result = context.normalize_purchase(response(context.purchase_urls(PURCHASE)[1], purchase(valorTotalHomologado=0)), PURCHASE, NOW)
    assert result["awarded_value"] == {"amount": "0", "currency": "BRL"}
    assert Decimal(result["estimated_value"]["amount"]) > 0
