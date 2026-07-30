"""Unit/contract tests for process_documents — drive shipped functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.coverage import (
    THRESHOLDS,
    compute_completeness,
    compute_financial_coverage,
    compute_operational_coverage,
    compute_process_recall,
    gate_exit_code,
)
from scripts.process_documents.discovery import (
    EXPECTED_UNIVERSE,
    build_discovery_report,
    classify_entity,
    discover_all,
    ordered_id_hash,
)
from scripts.process_documents.models import (
    DocumentRecord,
    DocumentRunResult,
    EntityDocumentDiscovery,
    resolve_financial_value,
)
from scripts.process_documents.sanitize import sanitize_text
from scripts.process_documents.statuses import DocumentCategory, DocumentRunStatus
from scripts.process_documents.storage import safe_extract_zip, sha256_bytes, store_blob
from scripts.source_registry.models import EntitySourceRecord


def test_universe_discovery_1093_zero_unknown(tmp_path: Path) -> None:
    discoveries, report = discover_all(persist=True, output_dir=tmp_path)
    assert len(discoveries) == EXPECTED_UNIVERSE
    assert report["entity_count"] == EXPECTED_UNIVERSE
    assert report["unknown_access_count"] == 0
    assert report["unknown_applicability_count"] == 0
    assert all(d.access_status != "unknown" for d in discoveries)
    assert all(d.applicability != "unknown" for d in discoveries)
    assert report["meets_100_percent"] is True
    assert report["entity_source_discovery_coverage"] == 1.0
    # set equality hash stable
    ids = sorted(d.canonical_id for d in discoveries)
    assert report["canonical_ids_sha256"] == ordered_id_hash(ids)
    assert (tmp_path / "document-source-registry.json").is_file()


def test_classify_entity_never_unknown() -> None:
    rec = EntitySourceRecord(
        canonical_id="12345678:TESTE",
        razao_social="TESTE",
        cnpj="12345678",
        natureza_juridica="municipio",
        municipio="FLORIANOPOLIS",
        access_status="unknown",
        plataformas=["pncp"],
    )
    d = classify_entity(rec)
    assert d.access_status != "unknown"
    assert d.portal_family == "pncp"
    assert d.pncp_source


def test_fail_closed_success_nonzero_requires_docs() -> None:
    run = DocumentRunResult(
        run_id="r1",
        canonical_entity_id="x",
        source_id="pncp",
        portal_family="pncp",
        capabilities_requested=[],
        capabilities_proven=[],
        status=DocumentRunStatus.SUCCESS_NONZERO,
        started_at="t0",
        finished_at="t1",
        documents_downloaded=0,
        documents_unchanged=0,
    )
    with pytest.raises(ValueError):
        run.validate_fail_closed()


def test_fail_closed_success_zero_needs_justification() -> None:
    run = DocumentRunResult(
        run_id="r1",
        canonical_entity_id="x",
        source_id="pncp",
        portal_family="pncp",
        capabilities_requested=[],
        capabilities_proven=[],
        status=DocumentRunStatus.SUCCESS_ZERO,
        started_at="t0",
        finished_at="t1",
    )
    with pytest.raises(ValueError):
        run.validate_fail_closed()


def test_success_zero_valid() -> None:
    run = DocumentRunResult(
        run_id="r1",
        canonical_entity_id="x",
        source_id="pncp",
        portal_family="pncp",
        capabilities_requested=[],
        capabilities_proven=[],
        status=DocumentRunStatus.SUCCESS_ZERO,
        started_at="t0",
        finished_at="t1",
        pages_attempted=2,
        pages_completed=2,
        success_zero_justification="full window empty",
    )
    run.validate_fail_closed()


def test_cas_idempotent(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    blob = b"%PDF-1.4 test content for hash"
    a = store_blob(blob, raw_root=raw, extension="pdf")
    b = store_blob(blob, raw_root=raw, extension="pdf")
    assert a.sha256 == b.sha256 == sha256_bytes(blob)
    assert b.unchanged is True
    assert a.path.is_file()


def test_zip_path_traversal_blocked(tmp_path: Path) -> None:
    import zipfile

    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../evil.txt", "nope")
    with pytest.raises(ValueError, match="traversal"):
        safe_extract_zip(zpath, tmp_path / "out")


def test_classify_document_title() -> None:
    assert classify_document_title("Edital de Pregão Eletrônico") == DocumentCategory.EDITAL.value
    assert classify_document_title("Planilha Orçamentária") == DocumentCategory.PLANILHA_ORCAMENTARIA.value
    assert classify_document_title("Homologação") == DocumentCategory.HOMOLOGACAO.value
    # Underscore / encoding / PNCP filename patterns
    assert classify_document_title("TERMO_DE_REFER_NCIA.pdf") == DocumentCategory.TERMO_REFERENCIA.value
    assert classify_document_title("ESTUDO_T_CNICO_PRELIMINAR.pdf") == DocumentCategory.ESTUDO_TECNICO.value
    assert classify_document_title("DFD ASSINADO") == DocumentCategory.ESTUDO_TECNICO.value
    assert classify_document_title("ETP393026_000013_2025.pdf") == DocumentCategory.ESTUDO_TECNICO.value
    assert classify_document_title("TR_393026_000028_2025__2_.pdf") == DocumentCategory.TERMO_REFERENCIA.value
    assert classify_document_title("Pregao_Eletronico_n_238_2024.pdf") == DocumentCategory.EDITAL.value
    assert classify_document_title("PE 055-2026 - Aquisicao de material saibro.pdf") == DocumentCategory.EDITAL.value
    assert classify_document_title("194334_editais_1784315803.zip") == DocumentCategory.EDITAL.value
    assert classify_document_title("Razao de escolha do contratado ASSINADO") == DocumentCategory.PARECER_JURIDICO.value
    assert classify_document_title("Termo_de_Homologacao.pdf") == DocumentCategory.HOMOLOGACAO.value
    assert classify_document_title("EDITAL202622.pdf") == DocumentCategory.EDITAL.value
    assert (
        classify_document_title("Documentos da Contratacao Direta - PUBLICADO.zip")
        == DocumentCategory.EDITAL.value
    )
    assert classify_document_title("") == DocumentCategory.UNKNOWN.value


def test_sanitize_cpf_email() -> None:
    text, findings = sanitize_text("CPF 123.456.789-09 email a@b.com")
    kinds = {f.kind for f in findings}
    assert "cpf" in kinds
    assert "email" in kinds
    assert "123.456.789-09" not in text
    assert "a@b.com" not in text


def test_financial_hierarchy_not_summed() -> None:
    from scripts.process_documents.models import ProcessRef

    p = ProcessRef(
        process_id="p1",
        canonical_entity_id="e",
        source_id="pncp",
        estimated_value=100.0,
        contracted_value=80.0,
    )
    val, field = resolve_financial_value(p)
    assert val == 80.0
    assert field == "contracted_value"


def test_operational_coverage_does_not_count_pending(tmp_path: Path) -> None:
    discoveries = [
        EntityDocumentDiscovery(
            canonical_id="A:1",
            razao_social="A",
            cnpj="1",
            municipio="X",
            uf="SC",
            applicability="applicable",
            applicability_reason="t",
            institutional_site=None,
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
            collection_strategy="pncp",
            fallback_strategy="html",
            activity_status="active",
        ),
        EntityDocumentDiscovery(
            canonical_id="B:1",
            razao_social="B",
            cnpj="2",
            municipio="Y",
            uf="SC",
            applicability="applicable",
            applicability_reason="t",
            institutional_site=None,
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
            collection_strategy="pncp",
            fallback_strategy="html",
            activity_status="active",
        ),
    ]
    meta = tmp_path / "meta"
    meta.mkdir()
    # only A has SUCCESS_NONZERO
    (meta / "run-index.jsonl").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "canonical_entity_id": "A:1",
                "status": "SUCCESS_NONZERO",
                "finished_at": "2026-07-30T00:00:00+00:00",
                "documents_downloaded": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = compute_operational_coverage(discoveries, meta_root=meta, persist=True)
    assert report["denominator"] == 2
    assert report["numerator"] == 1
    assert report["percent"] == 50.0
    assert report["meets_threshold"] is False
    # timeout-like status would not cover
    assert any(g["canonical_id"] == "B:1" for g in report["not_covered"])


def test_gate_exit_nonzero_when_operational_below(tmp_path: Path) -> None:
    discoveries, discovery_report = discover_all(persist=True, output_dir=tmp_path)
    # force activity active for two entities only via synthetic operational report
    reports = {
        "discovery": discovery_report,
        "operational": {
            "denominator": 10,
            "meets_threshold": False,
            "ratio": 0.1,
        },
        "recall": {"denominator": 0, "meets_threshold": False},
        "financial": {"total_value": 0, "meets_threshold": False},
        "completeness": {"metrics": {}},
    }
    code = gate_exit_code(reports)
    assert code != 0


def test_http_error_status_not_in_operational_success() -> None:
    from scripts.process_documents.statuses import OPERATIONAL_SUCCESS

    for st in (
        DocumentRunStatus.TIMEOUT,
        DocumentRunStatus.HTTP_RATE_LIMIT,
        DocumentRunStatus.HTTP_CLIENT_ERROR,
        DocumentRunStatus.HTTP_SERVER_ERROR,
        DocumentRunStatus.PARTIAL,
        DocumentRunStatus.DOWNLOAD_INCOMPLETE,
    ):
        assert st not in OPERATIONAL_SUCCESS


def test_thresholds_are_independent() -> None:
    # no single average key
    assert "average" not in THRESHOLDS
    assert THRESHOLDS["entity_source_discovery_coverage"] == 1.0
    assert THRESHOLDS["active_entity_document_operational_coverage"] == 0.95
    assert THRESHOLDS["relevant_process_recall"] == 0.98
    assert THRESHOLDS["covered_financial_value_ratio"] == 0.99
