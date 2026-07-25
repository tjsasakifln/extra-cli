"""Immutable content-addressed case store (file/hash based, no database)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.edital_case.models import SAFETY_FLAGS


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(text: str, max_len: int = 80) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text or "case")[:max_len]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def case_paths(case_dir: Path) -> dict[str, Path]:
    return {
        "root": case_dir,
        "manifest": case_dir / "case-manifest.json",
        "sources": case_dir / "sources",
        "acquisition": case_dir / "sources" / "acquisition.json",
        "objects": case_dir / "objects",
        "documents": case_dir / "documents",
        "inventory": case_dir / "inventory.json",
        "missing": case_dir / "missing-documents.json",
        "checklist": case_dir / "checklist.json",
        "timeline": case_dir / "timeline.json",
        "requirements": case_dir / "requirements.json",
        "findings": case_dir / "findings.json",
        "inconsistencies": case_dir / "inconsistencies.json",
        "evidence_matrix": case_dir / "evidence-matrix.json",
        "risk_register": case_dir / "risk-register.json",
        "recommendation": case_dir / "recommendation.json",
        "verification": case_dir / "verification.json",
        "reports": case_dir / "reports",
    }


def create_case_dir(case_root: Path, case_id: str) -> Path:
    case_dir = case_root / slugify(case_id)
    if case_dir.exists():
        raise FileExistsError(f"case already exists: {case_dir}")
    for sub in ("sources", "objects", "documents", "reports"):
        (case_dir / sub).mkdir(parents=True, exist_ok=True)
    return case_dir


def put_object(case_dir: Path, data: bytes, *, filename: str | None = None) -> dict[str, Any]:
    """Store bytes by SHA-256. Idempotent; never mutates existing object bytes."""
    digest = sha256_bytes(data)
    objects = case_dir / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    dest = objects / digest
    if dest.exists():
        existing = dest.read_bytes()
        if existing != data:
            raise RuntimeError(f"SHA-256 collision with different bytes: {digest}")
        # immutable — leave as-is
    else:
        # write via temp then rename
        tmp = objects / f".tmp-{digest}"
        tmp.write_bytes(data)
        tmp.replace(dest)
    return {
        "sha256": digest,
        "size": len(data),
        "object_path": str(dest),
        "filename": filename,
        "stored_at": utc_now(),
    }


def get_object_path(case_dir: Path, sha256: str) -> Path:
    path = case_dir / "objects" / sha256
    if not path.is_file():
        raise FileNotFoundError(f"object not found: {sha256}")
    return path


def verify_object_immutable(case_dir: Path, sha256: str) -> bool:
    path = get_object_path(case_dir, sha256)
    return sha256_file(path) == sha256


def init_manifest(
    case_dir: Path,
    *,
    case_id: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "case_id": case_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source": source,
        "status": "CREATED",
        "schema_version": "edital-case-v1",
        "campaign_id": "EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01",
        **SAFETY_FLAGS,
        "document_count": 0,
        "object_count": 0,
        "recommendation": None,
        "profile_path": None,
    }
    if extra:
        manifest.update(extra)
    write_json(case_dir / "case-manifest.json", manifest)
    return manifest


def update_manifest(case_dir: Path, **fields: Any) -> dict[str, Any]:
    path = case_dir / "case-manifest.json"
    manifest = read_json(path) if path.exists() else {}
    # safety flags cannot become true silently
    for k in SAFETY_FLAGS:
        if k in fields and fields[k] is not False:
            raise ValueError(f"refusing to set {k}={fields[k]!r}")
        fields.setdefault(k, False)
        if manifest.get(k) is True:
            raise ValueError(f"manifest already has {k}=true")
    manifest.update(fields)
    manifest["updated_at"] = utc_now()
    write_json(path, manifest)
    return manifest


def copy_tree_safe(src: Path, dst: Path) -> None:
    if dst.exists():
        raise FileExistsError(dst)
    shutil.copytree(src, dst)
