"""Shared deliverables manifest for PDF + Excel from one execution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _iso() -> str:
    return datetime.now(UTC).isoformat()


def _git_sha(cwd: Path | None = None) -> str | None:
    try:
        git = shutil.which("git")
        if not git:
            return None
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_artifact_file(path: Path, *, min_bytes: int = 32) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "ok": False, "error": "missing"}
    size = p.stat().st_size
    if size < min_bytes:
        return {"path": str(p), "ok": False, "error": "empty_or_too_small", "size": size}
    # basic magic
    head = p.read_bytes()[:8]
    kind = "unknown"
    if head.startswith(b"%PDF"):
        kind = "pdf"
    elif head.startswith(b"PK"):
        kind = "zip_or_xlsx"
    digest = sha256_file(p)
    return {"path": str(p), "ok": True, "size": size, "kind": kind, "sha256": digest}


def build_deliverables_manifest(
    *,
    execution_id: str,
    conclusions: dict[str, Any],
    sources_consulted: list[str],
    sources_failed: list[str],
    documents_used: list[dict[str, Any]],
    documents_missing: list[dict[str, Any]],
    human_review: dict[str, Any],
    pdf_path: Path | str | None = None,
    excel_path: Path | str | None = None,
    template_version: str = "1.0",
    code_sha: str | None = None,
    ressalvas: list[str] | None = None,
) -> dict[str, Any]:
    pdf_info = validate_artifact_file(Path(pdf_path)) if pdf_path else None
    xlsx_info = validate_artifact_file(Path(excel_path)) if excel_path else None

    pdf_ok = bool(pdf_info and pdf_info.get("ok"))
    xlsx_ok = bool(xlsx_info and xlsx_info.get("ok"))

    # agreement on counts if both present conclusions
    counts = conclusions.get("counts") if isinstance(conclusions, dict) else None
    agreement = True
    if isinstance(counts, dict) and "pdf" in counts and "excel" in counts:
        agreement = counts["pdf"] == counts["excel"]

    human = dict(human_review or {})
    package_released = bool(human.get("accepted_by_tiago")) and pdf_ok and xlsx_ok and agreement
    if not human.get("accepted_by_tiago"):
        package_released = False

    blocked_reasons: list[str] = []
    if pdf_path and not pdf_ok:
        blocked_reasons.append("pdf_invalid")
    if excel_path and not xlsx_ok:
        blocked_reasons.append("excel_invalid")
    if not agreement:
        blocked_reasons.append("pdf_excel_count_mismatch")
    if not human.get("accepted_by_tiago"):
        blocked_reasons.append("awaiting_human_accept")

    return {
        "execution_id": execution_id,
        "code_sha": code_sha or _git_sha() or os.environ.get("GITHUB_SHA"),
        "generated_at": _iso(),
        "template_version": template_version,
        "sources_consulted": list(sources_consulted),
        "sources_failed": list(sources_failed),
        "documents_used": list(documents_used),
        "documents_missing": list(documents_missing),
        "conclusions": conclusions,
        "ressalvas": list(ressalvas or []),
        "human_review": human,
        "artifacts": {"pdf": pdf_info, "excel": xlsx_info},
        "pdf_excel_agreement": agreement,
        "delivery_blocked": bool(blocked_reasons),
        "blocked_reasons": blocked_reasons,
        "package_released_to_client": package_released,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
