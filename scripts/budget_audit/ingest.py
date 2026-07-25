"""Secure acquisition and workbook extraction into case store."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.budget_audit.case_store import (
    ensure_case_layout,
    load_manifest,
    save_manifest,
    store_object,
    utc_now,
    write_json,
    write_jsonl,
)
from scripts.budget_audit.constants import (
    CONVERSION_REQUIRED_EXTENSIONS,
    MAX_SINGLE_FILE_BYTES,
    SUPPORTED_EXTENSIONS,
)
from scripts.budget_audit.hashing import sha256_file
from scripts.budget_audit.workbook_reader import OPENPYXL_VERSION, read_workbook
from scripts.budget_audit.zip_safety import safe_extract


def _document_id(name: str) -> str:
    stem = Path(name).stem
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return (safe or "doc")[:60] + "-" + uuid4().hex[:8]


def _collect_source_files(source: Path) -> list[Path]:
    if source.is_file():
        if source.suffix.lower() == ".zip":
            return [source]
        return [source]
    if source.is_dir():
        files: list[Path] = []
        for p in sorted(source.rglob("*")):
            if p.is_file() and not p.is_symlink():
                files.append(p)
        return files
    raise FileNotFoundError(f"source not found: {source}")


def create_case(case_id: str, source: str | Path, case_dir: Path | None = None) -> Path:
    import os

    if case_dir is None:
        # campaign-exclusive runtime root (override via BUDGET_CASE_ROOT)
        root = Path(
            os.environ.get(
                "BUDGET_CASE_ROOT",
                "/tmp/extra-cli-budget-audit-01/cases",  # noqa: S108
            )
        )
        case_dir = root / case_id
    case_dir = Path(case_dir)
    ensure_case_layout(case_dir)

    source_path = Path(source).expanduser().resolve()
    files = _collect_source_files(source_path)

    # Expand zips into tmp under case
    expanded: list[Path] = []
    acquisition_entries: list[dict[str, Any]] = []
    tmp = case_dir / "sources" / "_expand"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    for f in files:
        if f.suffix.lower() == ".zip":
            dest = tmp / f.stem
            dest.mkdir(parents=True, exist_ok=True)
            result = safe_extract(f, dest)
            acquisition_entries.append(
                {
                    "source": str(f),
                    "type": "zip",
                    "extracted": result.extracted,
                    "skipped": result.skipped,
                    "warnings": result.warnings,
                    "sha256": sha256_file(f),
                }
            )
            for rel in result.extracted:
                expanded.append(dest / rel)
        else:
            expanded.append(f)
            acquisition_entries.append(
                {
                    "source": str(f),
                    "type": "file",
                    "sha256": sha256_file(f),
                }
            )

    documents: list[dict[str, Any]] = []
    for f in expanded:
        if f.is_symlink():
            continue
        if not f.is_file():
            continue
        size = f.stat().st_size
        if size > MAX_SINGLE_FILE_BYTES:
            documents.append(
                {
                    "document_id": _document_id(f.name),
                    "original_name": f.name,
                    "status": "REJECTED_TOO_LARGE",
                    "size_bytes": size,
                }
            )
            continue
        ext = f.suffix.lower()
        obj = store_object(case_dir, f)
        ctype, _ = mimetypes.guess_type(f.name)
        doc = {
            "document_id": _document_id(f.name),
            "original_name": f.name,
            "source": str(f),
            "acquired_at": utc_now(),
            "content_type": ctype,
            "size_bytes": obj["size_bytes"],
            "sha256": obj["sha256"],
            "object_path": obj["object_path"],
            "extension": ext,
            "parser": None,
            "parser_version": None,
            "formula_mode": None,
            "calculation_mode": None,
            "warnings": [],
            "status": "ACQUIRED",
        }
        if ext in CONVERSION_REQUIRED_EXTENSIONS:
            doc["status"] = "CONVERSION_REQUIRED"
            doc["warnings"].append("XLS requires conversion")
        elif ext not in SUPPORTED_EXTENSIONS and ext not in {".json", ".md", ".txt"}:
            doc["status"] = "UNSUPPORTED"
            doc["warnings"].append(f"unsupported extension {ext}")
        documents.append(doc)

    manifest = {
        "case_id": case_id,
        "created_at": utc_now(),
        "source": str(source_path),
        "documents": documents,
        "phase": "created",
        "global_status": None,
    }
    save_manifest(case_dir, manifest)
    write_json(
        case_dir / "sources" / "acquisition.json",
        {
            "case_id": case_id,
            "acquired_at": utc_now(),
            "source": str(source_path),
            "entries": acquisition_entries,
            "document_count": len(documents),
        },
    )
    return case_dir


def ingest_case(case_dir: Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    manifest = load_manifest(case_dir)
    ensure_case_layout(case_dir)

    results = []
    for doc in manifest.get("documents") or []:
        if doc.get("status") not in {"ACQUIRED", "INGESTED", "CONVERSION_REQUIRED"}:
            continue
        if doc.get("status") == "CONVERSION_REQUIRED":
            results.append({"document_id": doc["document_id"], "status": "CONVERSION_REQUIRED"})
            continue
        ext = doc.get("extension") or ""
        if ext not in {".xlsx", ".xlsm", ".csv"}:
            results.append(
                {
                    "document_id": doc["document_id"],
                    "status": doc.get("status") or "SKIPPED",
                    "reason": f"no parser for {ext}",
                }
            )
            continue

        obj_path = case_dir / doc["object_path"]
        model = read_workbook(
            obj_path,
            document_id=doc["document_id"],
            extension=ext,
        )
        wb_dir = case_dir / "workbooks" / doc["document_id"]
        wb_dir.mkdir(parents=True, exist_ok=True)
        write_json(wb_dir / "workbook.json", model["workbook"])
        write_json(wb_dir / "sheets.json", model["sheets"])
        write_jsonl(wb_dir / "cells.jsonl", model["cells"])
        write_jsonl(wb_dir / "formulas.jsonl", model["formulas"])
        write_json(wb_dir / "merged-ranges.json", model["merged_ranges"])
        write_json(wb_dir / "names.json", model["names"])
        write_json(wb_dir / "hidden-content.json", model["hidden_content"])
        write_json(wb_dir / "extraction-quality.json", model["extraction_quality"])

        doc["parser"] = model["extraction_quality"].get("parser")
        doc["parser_version"] = model["extraction_quality"].get("parser_version") or OPENPYXL_VERSION
        doc["formula_mode"] = model["extraction_quality"].get("formula_mode")
        doc["calculation_mode"] = model["extraction_quality"].get("calculation_mode")
        doc["warnings"] = list(doc.get("warnings") or []) + list(model.get("warnings") or [])
        doc["status"] = "INGESTED"
        doc["cell_count"] = model["extraction_quality"].get("cell_count")
        doc["formula_count"] = model["extraction_quality"].get("formula_count")
        doc["sheet_count"] = model["extraction_quality"].get("sheet_count")
        results.append(
            {
                "document_id": doc["document_id"],
                "status": "INGESTED",
                "cell_count": doc["cell_count"],
                "formula_count": doc["formula_count"],
            }
        )

    manifest["documents"] = manifest.get("documents") or []
    manifest["phase"] = "ingested"
    manifest["updated_at"] = utc_now()
    save_manifest(case_dir, manifest)
    return {"case_id": manifest["case_id"], "results": results}
