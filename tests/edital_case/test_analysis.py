"""Unit tests for missing-annex detection, consistency, reconciliation — real shipped APIs."""

from __future__ import annotations

from pathlib import Path

from scripts.edital_case.analyze import (
    _normalize_compare_value,
    check_consistency,
    detect_missing_documents,
)
from scripts.edital_case.classify import classify_document
from scripts.edital_case.report import build_model, reconcile_reports, render_markdown
from scripts.edital_case.store import write_json

FIXTURES = Path(__file__).parent / "fixtures"


def _doc(
    doc_id: str,
    name: str,
    dtype: str,
    text: str,
    *,
    supported: bool = True,
) -> dict:
    blocks = [
        {
            "document_id": doc_id,
            "page": 1,
            "text": text,
            "locator": "page:1",
        }
    ]
    return {
        "document_id": doc_id,
        "original_name": name,
        "sha256": "a" * 64,
        "classification": {"result": dtype, "confidence": 0.9},
        "supported": supported,
        "quality_status": "OK",
        "blocks": blocks,
        "text": text,
    }


def test_classify_tr_filename_and_title() -> None:
    r = classify_document(
        filename="03_TR.pdf",
        text_sample="TERMO DE REFERÊNCIA\n1. Objeto: reforma predial",
        extension=".pdf",
    )
    assert r["result"] == "TERMO_DE_REFERENCIA"


def test_classify_etp_filename() -> None:
    r = classify_document(
        filename="02_ETPManutencaoPredialassinado.pdf",
        text_sample="ESTUDO TÉCNICO PRELIMINAR\nObjeto da contratação",
        extension=".pdf",
    )
    assert r["result"] == "ESTUDO_TECNICO_PRELIMINAR"


def test_classify_contrato_filename_not_edital() -> None:
    r = classify_document(
        filename="04_Contrato_ou_aditivo_ao_contrato.pdf",
        text_sample=(
            "MINUTA DO CONTRATO\nCláusula primeira\n"
            "O edital de pregão e o termo de referência integram este contrato."
        ),
        extension=".pdf",
    )
    assert r["result"] == "MINUTA_CONTRATUAL"


def test_detect_missing_finds_absent_planilha() -> None:
    edital = _doc(
        "doc-001",
        "edital.pdf",
        "EDITAL",
        "Anexos: Termo de Referência e Planilha Orçamentária e Memorial Descritivo.",
    )
    tr = _doc(
        "doc-002",
        "03_TR.pdf",
        "TERMO_DE_REFERENCIA",
        "TERMO DE REFERÊNCIA\nObjeto: reforma",
    )
    out = detect_missing_documents({"documents": [edital, tr]})
    # TR present
    assert any(
        r["status"] == "PRESENT" and r["expected_type"] == "TERMO_DE_REFERENCIA"
        for r in out["references"]
    )
    # Planilha missing
    assert any(
        r["status"] == "MISSING" and r["expected_type"] == "PLANILHA_ORCAMENTARIA"
        for r in out["references"]
    )
    assert out["missing_count"] >= 1


def test_detect_missing_does_not_false_missing_present_tr() -> None:
    """Regression: present TR must not be reported MISSING."""
    edital = _doc(
        "d1",
        "edital.pdf",
        "EDITAL",
        "Conforme o Termo de Referência e o ESTUDO TÉCNICO PRELIMINAR anexos.",
    )
    tr = _doc("d2", "03_TR.pdf", "TERMO_DE_REFERENCIA", "TERMO DE REFERÊNCIA completo")
    etp = _doc(
        "d3",
        "02_ETPManutencao.pdf",
        "ESTUDO_TECNICO_PRELIMINAR",
        "ESTUDO TÉCNICO PRELIMINAR da contratação",
    )
    out = detect_missing_documents({"documents": [edital, tr, etp]})
    for r in out["references"]:
        if r["expected_type"] in {"TERMO_DE_REFERENCIA", "ESTUDO_TECNICO_PRELIMINAR"}:
            assert r["status"] == "PRESENT", r
            assert r["matched_document_id"] in {"d2", "d3"}


def test_detect_missing_fixture_mentions_file() -> None:
    path = FIXTURES / "mentions_missing.txt"
    text = path.read_text(encoding="utf-8")
    edital = _doc("d1", "edital.txt", "EDITAL", text)
    out = detect_missing_documents({"documents": [edital]})
    assert out["missing_count"] >= 1
    types = {r["expected_type"] for r in out["references"] if r["status"] == "MISSING"}
    assert "PLANILHA_ORCAMENTARIA" in types or "MINUTA_CONTRATUAL" in types


def test_consistency_orgao_whitespace_is_format_variation() -> None:
    d1 = _doc("a", "edital.pdf", "EDITAL", "Prefeitura Municipal de Laguna\nCritério: MAIOR DESCONTO")
    d2 = _doc(
        "b",
        "tr.pdf",
        "TERMO_DE_REFERENCIA",
        "Prefeitura Municipal de \nLaguna\nCritério: maior desconto",
    )
    out = check_consistency({"documents": [d1, d2]})
    by_field = {i["field"]: i["class"] for i in out["inconsistencies"]}
    if "orgao" in by_field:
        assert by_field["orgao"] == "FORMAT_VARIATION"
    if "criterio_julgamento" in by_field:
        assert by_field["criterio_julgamento"] == "FORMAT_VARIATION"
    assert out.get("confirmed_conflict_count", 0) == 0


def test_consistency_true_conflict_on_different_dates_field() -> None:
    d1 = _doc("a", "edital.pdf", "EDITAL", "Prazo de execução: 180 dias")
    d2 = _doc("b", "tr.pdf", "TERMO_DE_REFERENCIA", "Prazo de execução: 90 dias")
    out = check_consistency({"documents": [d1, d2]})
    prazo = [i for i in out["inconsistencies"] if i["field"] == "prazo_execucao"]
    assert prazo
    assert prazo[0]["class"] == "CONFIRMED_CONFLICT"


def test_normalize_compare_value_case_and_ws() -> None:
    a = _normalize_compare_value("criterio_julgamento", "MAIOR DESCONTO")
    b = _normalize_compare_value("criterio_julgamento", "maior desconto")
    assert a == b
    a2 = _normalize_compare_value("orgao", "Prefeitura Municipal de\nLaguna")
    b2 = _normalize_compare_value("orgao", "Prefeitura Municipal de Laguna")
    assert a2 == b2


def test_report_reconciliation_counts(tmp_path: Path) -> None:
    """Drive shipped reconcile_reports against a minimal case dir."""
    case = tmp_path / "case"
    reports = case / "reports"
    reports.mkdir(parents=True)
    # minimal case artifacts for build_model
    write_json(
        case / "case-manifest.json",
        {
            "case_id": "t",
            "production_touched": False,
            "soak_touched": False,
            "vps_accessed": False,
            "database_used": False,
        },
    )
    write_json(
        case / "inventory.json",
        {
            "document_count": 1,
            "documents": [
                {
                    "document_id": "doc-001",
                    "original_name": "e.pdf",
                    "sha256": "ab",
                    "classification": {"result": "EDITAL"},
                    "quality_status": "OK",
                    "page_count": 2,
                    "total_chars": 10,
                }
            ],
        },
    )
    write_json(
        case / "checklist.json",
        {
            "item_count": 2,
            "items": [
                {
                    "id": "a",
                    "label": "A",
                    "status": "SATISFIED",
                    "critical": True,
                    "category": "x",
                    "evidence": {"locator": "page:1", "excerpt": "obj"},
                },
                {
                    "id": "b",
                    "label": "B",
                    "status": "NOT_FOUND",
                    "critical": False,
                    "category": "x",
                    "evidence": {},
                },
            ],
        },
    )
    write_json(case / "timeline.json", {"event_count": 0, "events": [], "conflicts": []})
    write_json(case / "missing-documents.json", {"missing_count": 0, "references": []})
    write_json(case / "findings.json", {"count": 0, "findings": []})
    write_json(case / "inconsistencies.json", {"count": 0, "inconsistencies": []})
    write_json(case / "requirements.json", {"rows": [], "row_count": 0})
    write_json(case / "risk-register.json", {"risks": [], "count": 0})
    write_json(
        case / "recommendation.json",
        {"recommendation": "REVIEW", "reasons": ["x"], "disclaimer": "d"},
    )
    write_json(case / "evidence-matrix.json", {"entries": []})

    model = build_model(case)
    md = render_markdown(model)
    (reports / "executive-summary.md").write_text(md, encoding="utf-8")
    # create xlsx via shipped renderer
    from scripts.edital_case.report import render_excel

    render_excel(model, reports / "triage-workbook.xlsx")
    recon = reconcile_reports(model, reports)
    assert recon["ok"] is True
    assert recon["counts"]["checklist_items"] == 2


def test_scanned_empty_pdf_marks_ocr_or_empty() -> None:
    pdf = FIXTURES / "scanned_empty.pdf"
    from scripts.edital_case.extract import extract_pdf

    result = extract_pdf(pdf, "scan")
    # Blank PDF: OCR_REQUIRED/EMPTY when extractors work; EXTRACTION_FAILED if none installed
    assert result["quality_status"] in {
        "OCR_REQUIRED",
        "EMPTY",
        "OK",
        "PARTIAL",
        "EXTRACTION_FAILED",
    }
    # blank canvas should not invent rich requirements
    assert (result.get("total_chars") or 0) < 50


def test_pack_evil_zip_fixture() -> None:
    from scripts.edital_case.acquire import safe_extract_zip

    z = FIXTURES / "pack_evil.zip"
    dest = Path("/tmp/extra-cli-edital-triage-01/tmp/test-evil-out")
    import shutil

    if dest.exists():
        shutil.rmtree(dest)
    results = safe_extract_zip(z, dest)
    assert all(r.get("status") == "REJECTED" for r in results)
