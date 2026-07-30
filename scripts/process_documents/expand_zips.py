"""Expand already-collected ZIP packs into per-member documents (multi-source completeness).

Uses CAS blobs referenced by run results. Does not shrink denominators — members
are attached to the parent process_id so completeness can see edital/TR/ata packs
hidden inside FASE_INTERNA / editais / envelope ZIPs.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.models import DocumentRecord
from scripts.process_documents.storage import (
    DEFAULT_META_ROOT,
    DEFAULT_RAW_ROOT,
    cas_path,
    detect_mime,
    ensure_roots,
    safe_extract_zip,
    store_blob,
    write_json,
)


def _resolve_cas(raw_root: Path, doc: dict[str, Any]) -> Path | None:
    sha = (doc.get("sha256") or "").strip()
    if not sha:
        raw_uri = str(doc.get("raw_uri") or "")
        if raw_uri.startswith("cas://"):
            # cas://process_documents/<sha>
            sha = raw_uri.rstrip("/").split("/")[-1]
    if not sha or len(sha) < 16:
        return None
    for ext in (doc.get("extension"), "zip", "pdf", None):
        p = cas_path(raw_root, sha, extension=ext if ext else None)
        if p.is_file():
            return p
        # try without extension
        bare = cas_path(raw_root, sha, extension=None)
        if bare.is_file():
            return bare
        # glob
        parent = bare.parent
        if parent.is_dir():
            matches = list(parent.glob(f"{sha}*"))
            if matches:
                return matches[0]
    return None


def _is_zip_doc(doc: dict[str, Any]) -> bool:
    title = str(doc.get("original_title") or doc.get("original_filename") or "").lower()
    mime = str(doc.get("detected_mime") or doc.get("declared_mime") or "").lower()
    ext = str(doc.get("extension") or "").lower()
    return ext == "zip" or title.endswith(".zip") or "zip" in mime or mime.endswith("zip")


def expand_zip_documents(
    *,
    meta_root: Path | None = None,
    raw_root: Path | None = None,
    max_zips: int = 200,
    max_members_per_zip: int = 40,
) -> dict[str, Any]:
    """Extract ZIP members from existing runs into new synthetic run result."""
    raw, meta = ensure_roots(raw_root=raw_root or DEFAULT_RAW_ROOT, meta_root=meta_root or DEFAULT_META_ROOT)
    runs_dir = meta / "runs"
    expanded_docs: list[dict[str, Any]] = []
    zips_seen = 0
    zips_ok = 0
    zips_fail = 0
    errors: list[str] = []
    # Dedup only within (process_id, member_sha) so CAS hits still link to process.
    seen_proc_sha: set[tuple[str, str]] = set()

    if not runs_dir.is_dir():
        return {"status": "no_runs", "expanded_documents": 0}

    import re

    _PNCP_PID = re.compile(r"^\d{14}-\d+-\d+/\d{4}$")

    def _zip_priority(doc: dict[str, Any], data: dict[str, Any]) -> int:
        """Higher first: real PNCP process packs over CIGA publication dumps."""
        pid = str(doc.get("procurement_id") or doc.get("notice_id") or "")
        title = str(doc.get("original_title") or doc.get("original_filename") or "").lower()
        source = str(doc.get("source_id") or data.get("source_id") or "").lower()
        score = 0
        if _PNCP_PID.match(pid):
            score += 100
        if any(k in title for k in ("edital", "anexo", "fase", "tr", "etp", "dfd", "habilit", "proposta")):
            score += 50
        if "publicac" in title or pid.startswith("ciga:domsc-publicacoes"):
            score -= 100
        if source == "pncp":
            score += 20
        if source == "ciga_ckan":
            score -= 10
        return score

    # Collect candidates first so noise dumps don't consume max_zips budget.
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for result_path in runs_dir.glob("*/result.json"):
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for doc in data.get("documents") or []:
            if _is_zip_doc(doc):
                candidates.append((_zip_priority(doc, data), doc, data))
    candidates.sort(key=lambda t: t[0], reverse=True)

    for _prio, doc, data in candidates:
        if zips_seen >= max_zips:
            break
        zips_seen += 1
        path = _resolve_cas(raw, doc)
        if path is None or not path.is_file():
            zips_fail += 1
            errors.append(f"missing cas for zip sha={doc.get('sha256')}")
            continue
        # verify zip magic
        try:
            head = path.read_bytes()[:4]
        except OSError as exc:
            zips_fail += 1
            errors.append(str(exc))
            continue
        if head != b"PK\x03\x04":
            zips_fail += 1
            continue
        tmp = Path(tempfile.mkdtemp(prefix="pd-zip-"))
        try:
            members = safe_extract_zip(path, tmp)
        except ValueError as exc:
            zips_fail += 1
            errors.append(f"zip extract fail: {exc}")
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        zips_ok += 1
        parent_pid = str(
            doc.get("procurement_id") or doc.get("notice_id") or data.get("run_id") or "unknown"
        )
        entity = doc.get("canonical_entity_id") or data.get("canonical_entity_id")
        source = doc.get("source_id") or data.get("source_id") or "zip_expand"
        family = doc.get("portal_family") or data.get("portal_family") or "multi_source"
        for member in members[:max_members_per_zip]:
            if not member.is_file():
                continue
            try:
                blob = member.read_bytes()
            except OSError:
                continue
            if not blob or len(blob) < 32:
                continue
            try:
                stored = store_blob(
                    blob,
                    raw_root=raw,
                    extension=member.suffix.lstrip(".") or None,
                    declared_filename=member.name,
                )
            except ValueError as exc:
                errors.append(f"store fail {member.name}: {exc}")
                continue
            key = (parent_pid, stored.sha256)
            if key in seen_proc_sha:
                continue
            seen_proc_sha.add(key)
            cat = classify_document_title(member.name)
            mime = detect_mime(blob)
            rec = DocumentRecord(
                internal_id=stored.sha256[:20],
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                download_url=str(doc.get("download_url") or "") + f"#member={member.name}",
                source_id=f"{source}+zip_member",
                canonical_entity_id=str(entity or "unknown"),
                portal_family=str(family),
                document_category=cat,
                original_title=member.name,
                original_filename=member.name,
                procurement_id=parent_pid,
                notice_id=doc.get("notice_id"),
                declared_mime=mime,
                detected_mime=mime,
                extension=member.suffix.lstrip(".") or None,
                run_id=None,
                raw_uri=stored.raw_uri,
                unchanged=stored.unchanged,
            )
            expanded_docs.append(rec.to_dict())
        shutil.rmtree(tmp, ignore_errors=True)

    started = datetime.now(UTC)
    run_id = f"pd-zip-expand-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = meta / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "run_id": run_id,
        "canonical_entity_id": "multi:zip_expand",
        "source_id": "zip_expand",
        "portal_family": "multi_source",
        "capabilities_requested": [
            "notice_documents",
            "planning_documents",
            "session_and_judgment_documents",
            "bidder_submission_documents",
        ],
        "capabilities_proven": ["notice_documents"] if expanded_docs else [],
        "status": "SUCCESS_NONZERO" if expanded_docs else "SUCCESS_ZERO",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "query_parameters": {
            "max_zips": max_zips,
            "max_members_per_zip": max_members_per_zip,
            "mode": "expand_existing_cas_zips",
        },
        "pages_attempted": zips_seen,
        "pages_completed": zips_ok,
        "records_seen": zips_seen,
        "processes_seen": len({d.get("procurement_id") for d in expanded_docs if d.get("procurement_id")}),
        "documents_discovered": len(expanded_docs),
        "documents_downloaded": len(expanded_docs),
        "documents_unchanged": 0,
        "documents_failed": zips_fail,
        "errors": errors[:50],
        "blockers": [],
        "documents": expanded_docs,
    }
    write_json(run_dir / "result.json", result)
    # append run-index
    index = meta / "run-index.jsonl"
    with index.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "canonical_entity_id": "multi:zip_expand",
                    "source_id": "zip_expand",
                    "status": result["status"],
                    "documents_downloaded": len(expanded_docs),
                    "process_id": None,
                    "finished_at": result["finished_at"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    summary = {
        "run_id": run_id,
        "zips_seen": zips_seen,
        "zips_ok": zips_ok,
        "zips_fail": zips_fail,
        "expanded_documents": len(expanded_docs),
        "unique_processes": result["processes_seen"],
        "errors_sample": errors[:10],
    }
    write_json(meta / "zip-expand-summary.json", summary)
    return summary
