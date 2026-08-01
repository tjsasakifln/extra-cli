"""Quarantine + multi-source consultation report tests."""

from __future__ import annotations

from pathlib import Path

from scripts.process_documents.process_card import (
    merge_documents_into_card,
    source_consultation_report,
)
from scripts.process_documents.quarantine import assess_blob, quarantine_blob


def test_quarantine_empty_and_html_as_pdf(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    v = assess_blob(b"", declared_mime="application/pdf")
    assert v.quarantined is True
    assert "empty_file" in v.reasons

    html = b"<!DOCTYPE html><html><body>not a pdf</body></html>"
    v2 = assess_blob(html, declared_mime="application/pdf", detected_mime="text/html")
    assert v2.quarantined is True
    assert any("html" in r or "mime" in r or "pdf" in r for r in v2.reasons)

    out = quarantine_blob(html, verdict=v2, meta={"title": "fake"}, meta_root=tmp_path / "meta", raw_root=tmp_path / "raw")
    assert out["quarantined"] is True
    assert Path(out["record"]["path"]).is_file()


def test_ocr_recommended_when_native_text_unusable() -> None:
    pdf = b"%PDF-1.4 " + b"\x00" * 100
    v = assess_blob(pdf, declared_mime="application/pdf", detected_mime="application/pdf", native_text="   ")
    assert v.native_text_usable is False
    assert v.ocr_recommended is True
    assert v.extraction_quality in {"none", "low"}


def test_good_pdf_not_quarantined() -> None:
    pdf = b"%PDF-1.4 real content " + b"x" * 50
    v = assess_blob(
        pdf,
        declared_mime="application/pdf",
        detected_mime="application/pdf",
        native_text="Edital de licitacao com texto nativo suficiente para leitura.",
    )
    assert v.quarantined is False
    assert v.ocr_recommended is False
    assert v.text_origin == "native"


def test_source_consultation_report_states() -> None:
    report = source_consultation_report(
        applicable_sources=["pncp", "ciga_ckan", "sc_compras", "doe_sc"],
        source_results={
            "pncp": {
                "status": "success_nonzero",
                "documents": [
                    {"source_id": "pncp", "sha256": "abc", "raw_uri": "cas://abc"},
                ],
            },
            "ciga_ckan": {"status": "connection_failed", "error": "timeout"},
            "sc_compras": {
                "status": "success_zero",
                "documents": [
                    {"source_id": "sc_compras", "cited_missing": True, "original_title": "Ata"},
                ],
            },
            # doe_sc not consulted
        },
    )
    by = {r["source_id"]: r["state"] for r in report["sources"]}
    assert by["pncp"] == "document_located"
    assert by["ciga_ckan"] == "query_failed"
    assert by["sc_compras"] in {"document_not_published", "not_consulted", "query_failed"}
    assert by["doe_sc"] == "not_consulted"


def test_process_card_version_not_overwrite() -> None:
    docs1 = [
        {
            "procurement_id": "P1",
            "sha256": "v1",
            "source_id": "pncp",
            "original_title": "Edital",
            "download_url": "https://x/e.pdf",
        }
    ]
    c1 = merge_documents_into_card("P1", docs1)
    docs2 = [
        {
            "procurement_id": "P1",
            "sha256": "v2",
            "source_id": "pncp",
            "original_title": "Edital",
            "download_url": "https://x/e.pdf",
        }
    ]
    c2 = merge_documents_into_card("P1", docs2, previous=c1.to_dict())
    assert any(ch["change"] == "changed" for ch in c2.changes)
    # history keeps prior version entries
    key = next(iter(c2.versions))
    shas = [v.get("sha256") for v in c2.versions[key]]
    assert "v2" in shas
