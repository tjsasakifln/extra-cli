"""End-to-end pipeline: create → ingest → analyze → report → verify."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scripts.edital_case.acquire import acquire_source
from scripts.edital_case.analyze import run_analysis
from scripts.edital_case.classify import classify_document
from scripts.edital_case.extract import extract_document, full_text
from scripts.edital_case.isolation import enforce_isolation
from scripts.edital_case.report import generate_reports
from scripts.edital_case.store import (
    create_case_dir,
    init_manifest,
    read_json,
    slugify,
    update_manifest,
    utc_now,
    write_json,
)
from scripts.edital_case.verify import verify_case


def default_case_root() -> Path:
    root = os.environ.get("EDITAL_CASE_ROOT") or os.environ.get("EDITAL_CAMPAIGN_ROOT")
    if root:
        p = Path(root)
        if (p / "cases").is_dir() or os.environ.get("EDITAL_CASE_ROOT"):
            return Path(os.environ.get("EDITAL_CASE_ROOT") or (p / "cases"))
        return p / "cases" if p.name != "cases" else p
    return Path("/tmp/extra-cli-edital-triage-01/cases")  # noqa: S108


def cmd_create(case_id: str, source: str, *, case_root: Path | None = None) -> dict[str, Any]:
    enforce_isolation()
    case_root = case_root or default_case_root()
    case_root.mkdir(parents=True, exist_ok=True)
    case_dir = create_case_dir(case_root, case_id)
    manifest = init_manifest(case_dir, case_id=slugify(case_id), source=source)
    write_json(
        case_dir / "sources" / "create.json",
        {"case_id": case_id, "source": source, "created_at": utc_now()},
    )
    return {"case_dir": str(case_dir), "manifest": manifest}


def cmd_ingest(case_dir: Path) -> dict[str, Any]:
    enforce_isolation()
    case_dir = Path(case_dir).resolve()
    manifest = read_json(case_dir / "case-manifest.json")
    source = manifest.get("source")
    if not source:
        raise ValueError("manifest missing source")
    acquisition = acquire_source(source, case_dir)

    documents: list[dict[str, Any]] = []
    doc_index = 0
    skip_names = {
        "selection.json",
        "arquivos.json",
        "acquisition.json",
        "create.json",
    }
    for rec in acquisition.get("records") or []:
        if rec.get("status") not in {"ACQUIRED", "UNSUPPORTED", "DUPLICATE_CONTENT"}:
            continue
        if not rec.get("sha256"):
            continue
        if rec.get("status") == "DUPLICATE_CONTENT":
            continue
        if rec.get("extension") == ".zip":
            # container only
            continue
        oname = (rec.get("original_name") or "").lower()
        if oname in skip_names:
            continue
        doc_index += 1
        doc_id = f"doc-{doc_index:03d}"
        ext = rec.get("extension") or ""
        extraction = extract_document(
            case_dir,
            document_id=doc_id,
            sha256=rec["sha256"],
            extension=ext,
            original_name=rec.get("original_name") or doc_id,
        )
        sample = full_text(extraction.get("blocks") or [])[:20000]
        classification = classify_document(
            filename=rec.get("original_name") or "",
            text_sample=sample,
            extension=ext,
        )
        doc_meta = {
            "document_id": doc_id,
            "original_name": rec.get("original_name"),
            "sha256": rec["sha256"],
            "extension": ext,
            "content_type": rec.get("content_type"),
            "size": rec.get("size"),
            "origin": rec.get("origin"),
            "method": rec.get("method"),
            "parent_zip_sha256": rec.get("parent_zip_sha256"),
            "classification": classification,
            "quality_status": extraction.get("quality_status"),
            "extraction_status": extraction.get("status"),
            "extraction_method": extraction.get("extraction_method"),
            "page_count": extraction.get("page_count"),
            "total_chars": extraction.get("total_chars"),
            "ocr_used": extraction.get("ocr_used", False),
            "supported": rec.get("status") != "UNSUPPORTED"
            and extraction.get("status") != "UNSUPPORTED",
        }
        write_json(case_dir / "documents" / doc_id / "document.json", doc_meta)
        documents.append(doc_meta)

    inventory = {
        "generated_at": utc_now(),
        "document_count": len(documents),
        "documents": documents,
        "acquisition_errors": acquisition.get("errors") or [],
        "duplicates": acquisition.get("duplicates") or [],
    }
    write_json(case_dir / "inventory.json", inventory)
    update_manifest(
        case_dir,
        status="INGESTED",
        document_count=len(documents),
        object_count=len(
            [r for r in (acquisition.get("records") or []) if r.get("sha256")]
        ),
    )
    return {"inventory": inventory, "case_dir": str(case_dir)}


def cmd_analyze(case_dir: Path, profile: Path | None) -> dict[str, Any]:
    enforce_isolation()
    case_dir = Path(case_dir).resolve()
    result = run_analysis(case_dir, profile)
    update_manifest(
        case_dir,
        status="ANALYZED",
        recommendation=(result.get("recommendation") or {}).get("recommendation"),
        profile_path=str(profile) if profile else None,
    )
    return result


def cmd_report(case_dir: Path) -> dict[str, Any]:
    enforce_isolation()
    case_dir = Path(case_dir).resolve()
    result = generate_reports(case_dir)
    update_manifest(case_dir, status="REPORTED")
    return result


def cmd_verify(case_dir: Path) -> dict[str, Any]:
    enforce_isolation()
    case_dir = Path(case_dir).resolve()
    result = verify_case(case_dir)
    write_json(case_dir / "verification.json", result)
    update_manifest(case_dir, status="VERIFIED" if result.get("ok") else "VERIFY_FAILED")
    return result


def cmd_run(
    *,
    case_id: str,
    source: str,
    profile: Path | None,
    output: Path | None = None,
) -> dict[str, Any]:
    enforce_isolation()
    if output:
        output = Path(output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        # if output is the case dir itself
        if output.name == slugify(case_id) or (output / "case-manifest.json").exists():
            case_dir = output
            if not (case_dir / "case-manifest.json").exists():
                init_manifest(case_dir, case_id=slugify(case_id), source=source)
        else:
            created = cmd_create(case_id, source, case_root=output)
            case_dir = Path(created["case_dir"])
    else:
        created = cmd_create(case_id, source)
        case_dir = Path(created["case_dir"])

    # if create was skipped and source differs, still ingest from manifest source
    ingest = cmd_ingest(case_dir)
    analysis = cmd_analyze(case_dir, profile)
    report = cmd_report(case_dir)
    verification = cmd_verify(case_dir)
    return {
        "case_dir": str(case_dir),
        "ingest": {
            "document_count": (ingest.get("inventory") or {}).get("document_count")
        },
        "recommendation": (analysis.get("recommendation") or {}).get("recommendation"),
        "findings": (analysis.get("findings") or {}).get("count"),
        "report_ok": (report.get("reconciliation") or {}).get("ok"),
        "verification": verification,
    }
