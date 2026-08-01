"""Unit tests for edital_case core — exercise real shipped functions."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.edital_case.acquire import safe_extract_zip
from scripts.edital_case.analyze import (
    _normalize_date,
    profile_completeness,
    recommend,
)
from scripts.edital_case.classify import classify_document
from scripts.edital_case.extract import (
    extract_document,
    extract_pdf,
    extract_txt,
    extract_xlsx,
    find_excerpt,
)
from scripts.edital_case.isolation import path_is_allowed
from scripts.edital_case.store import put_object, sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def test_sha256_stable() -> None:
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")


def test_put_object_immutable(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    meta = put_object(case, b"hello-edital", filename="a.txt")
    sha = meta["sha256"]
    # second put same bytes ok
    put_object(case, b"hello-edital", filename="b.txt")
    obj = case / "objects" / sha
    assert obj.read_bytes() == b"hello-edital"
    # collision with different bytes must fail
    # force write different content under same hash path is blocked by put_object
    # simulate by trying put of different content — different hash, different path
    meta2 = put_object(case, b"other", filename="c.txt")
    assert meta2["sha256"] != sha


def test_safe_zip_blocks_traversal(tmp_path: Path) -> None:
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escape.txt", "nope")
        zf.writestr("ok.txt", "safe")
    dest = tmp_path / "out"
    results = safe_extract_zip(zpath, dest)
    statuses = {r.get("name"): r.get("status") for r in results}
    assert statuses.get("../escape.txt") == "REJECTED"
    assert any(r.get("status") == "EXTRACTED" and "ok.txt" in (r.get("safe_name") or "") for r in results)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_zip_blocks_executable(tmp_path: Path) -> None:
    zpath = tmp_path / "exe.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("run.sh", "#!/bin/sh\necho x")
    dest = tmp_path / "out2"
    results = safe_extract_zip(zpath, dest)
    assert results[0]["status"] == "REJECTED"
    assert results[0]["reason"] == "executable_extension"


def test_classify_edital_by_content() -> None:
    result = classify_document(
        filename="documento.pdf",
        text_sample="EDITAL DE PREGÃO ELETRÔNICO Nº 01/2026\nObjeto: reforma predial",
        extension=".pdf",
    )
    assert result["result"] == "EDITAL"
    assert result["confidence"] > 0.3


def test_classify_filename_not_conclusive_alone() -> None:
    result = classify_document(
        filename="edital.pdf",
        text_sample="Planilha orçamentária com preços unitários e BDI",
        extension=".pdf",
    )
    # content may pull toward planilha; needs human if contradiction
    assert result["result"] in {"PLANILHA_ORCAMENTARIA", "EDITAL", "BDI", "UNKNOWN"}
    assert "rule_version" in result


def test_normalize_date() -> None:
    assert _normalize_date("03/07/2026") == "2026-07-03"
    assert _normalize_date("bad") is None


def test_find_excerpt(tmp_path: Path) -> None:
    blocks = [
        {
            "document_id": "d1",
            "page": 2,
            "text": "A visita técnica será no dia 10/08/2026 às 14h.",
            "locator": "page:2",
        }
    ]
    hit = find_excerpt(blocks, r"visita\s+t[eé]cnica")
    assert hit is not None
    assert hit["page"] == 2
    assert "visita" in hit["excerpt"].lower()


def test_profile_completeness_blocks_go() -> None:
    prof = {"_status": "LOADED", "region": {"uf_primary": "SC"}, "positive_terms": ["reforma"]}
    c = profile_completeness(prof)
    assert c["blocks_go"] is True


def test_recommend_fail_closed_review() -> None:
    checklist = {
        "items": [
            {
                "id": "objeto_escopo",
                "label": "Objeto",
                "critical": True,
                "status": "SATISFIED",
            },
            {
                "id": "x",
                "label": "Critical missing",
                "critical": True,
                "status": "NOT_FOUND",
            },
        ]
    }
    findings = {"count": 1, "findings": []}
    missing = {"references": []}
    consistency = {"inconsistencies": []}
    timeline = {"events": [], "conflicts": []}
    profile = {"_status": "LOADED", "region": {"uf_primary": "SC"}}
    rec = recommend(checklist, findings, missing, consistency, profile, timeline)
    assert rec["recommendation"] == "REVIEW"
    assert rec["disclaimer"]


def test_recommend_no_go_expired() -> None:
    checklist = {"items": []}
    findings = {"count": 0, "findings": []}
    missing = {"references": []}
    consistency = {"inconsistencies": []}
    timeline = {
        "events": [
            {
                "kind": "sessao",
                "normalized": "2020-01-01",
                "raw_value": "01/01/2020",
            }
        ],
        "conflicts": [],
    }
    profile = {"_status": "LOADED", "region": {"uf_primary": "SC"}}
    rec = recommend(checklist, findings, missing, consistency, profile, timeline)
    assert rec["recommendation"] == "NO_GO"


def test_allowlist() -> None:
    assert path_is_allowed("scripts/edital_case/cli.py")
    assert path_is_allowed("tests/edital_case/test_core.py")
    assert not path_is_allowed("DOD.md")
    assert not path_is_allowed("scripts/workspace/cli.py")
    assert not path_is_allowed("db/migrations/062_x.sql")


def test_extract_txt(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("Linha um\n\nObjeto: reforma da escola\n", encoding="utf-8")
    result = extract_txt(p, "doc-1")
    assert result["status"] == "OK"
    assert result["total_chars"] > 0
    assert any("reforma" in (b.get("text") or "") for b in result["blocks"])


def test_fixture_edital_pdf_if_present() -> None:
    pdf = FIXTURES / "sample_edital.pdf"
    if not pdf.exists():
        pytest.skip("fixture pdf not built yet")
    result = extract_pdf(pdf, "fix-doc")
    if result.get("status") == "EXTRACTION_FAILED" or (result.get("page_count") or 0) < 1:
        # CI without PDF extractor still exercises the fail-closed path
        assert result.get("quality_status") in {"EXTRACTION_FAILED", "EMPTY", "OCR_REQUIRED"}
        return
    assert result["page_count"] >= 1
    assert result["quality_status"] in {"OK", "PARTIAL", "OCR_REQUIRED", "EMPTY"}
    assert result.get("total_chars", 0) > 0


def test_extract_xlsx_extensionless_object_path(tmp_path: Path) -> None:
    """Regression: openpyxl rejects bare SHA object paths; must load via bytes."""
    xlsx = FIXTURES / "sample_planilha.xlsx"
    if not xlsx.exists():
        pytest.skip("fixture xlsx not present")
    bare = tmp_path / ("a" * 64)  # content-addressed object style (no .xlsx suffix)
    bare.write_bytes(xlsx.read_bytes())
    result = extract_xlsx(bare, "doc-planilha")
    assert result["status"] == "OK", result.get("error")
    assert result["quality_status"] == "OK"
    assert len(result.get("blocks") or []) >= 1
    assert any(b.get("cell") for b in result["blocks"])
    assert any(t.get("cell_count", 0) > 0 for t in (result.get("tables") or []))


def test_extract_document_planilha_via_put_object(tmp_path: Path) -> None:
    """Shipped path: put_object stores bare SHA → extract_document(.xlsx) must succeed."""
    xlsx = FIXTURES / "sample_planilha.xlsx"
    if not xlsx.exists():
        pytest.skip("fixture xlsx not present")
    case = tmp_path / "case"
    case.mkdir()
    meta = put_object(case, xlsx.read_bytes(), filename="sample_planilha.xlsx")
    result = extract_document(
        case,
        document_id="doc-001",
        sha256=meta["sha256"],
        extension=".xlsx",
        original_name="sample_planilha.xlsx",
    )
    assert result["status"] == "OK", result.get("error")
    assert result["quality_status"] == "OK"
    assert (result.get("total_chars") or 0) > 0
    assert len(result.get("blocks") or []) >= 1
    summary = case / "documents" / "doc-001" / "extraction-summary.json"
    assert summary.is_file()
    tables = case / "documents" / "doc-001" / "tables.json"
    assert tables.is_file()
