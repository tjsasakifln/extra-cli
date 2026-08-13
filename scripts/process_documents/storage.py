"""Content-addressed storage for process documents (raw outside Git — ADR-020)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default operational root (gitignored via output/ and data/)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_ROOT = Path(
    os.environ.get(
        "PROCESS_DOCUMENTS_RAW_ROOT",
        str(_PROJECT_ROOT / "data" / "raw" / "process_documents"),
    )
)
DEFAULT_META_ROOT = Path(
    os.environ.get(
        "PROCESS_DOCUMENTS_META_ROOT",
        str(_PROJECT_ROOT / "output" / "process_documents"),
    )
)

MAX_DOCUMENT_BYTES = int(os.environ.get("PROCESS_DOCUMENTS_MAX_BYTES", str(80 * 1024 * 1024)))
MAX_ZIP_MEMBERS = int(os.environ.get("PROCESS_DOCUMENTS_MAX_ZIP_MEMBERS", "500"))
MAX_ZIP_UNCOMPRESSED = int(os.environ.get("PROCESS_DOCUMENTS_MAX_ZIP_UNCOMPRESSED", str(200 * 1024 * 1024)))
MAX_PDF_BYTES = int(os.environ.get("PROCESS_DOCUMENTS_MAX_PDF_BYTES", str(80 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.environ.get("PROCESS_DOCUMENTS_MAX_PDF_PAGES", "2000"))

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    size_bytes: int
    raw_uri: str
    path: Path
    unchanged: bool


def ensure_roots(raw_root: Path | None = None, meta_root: Path | None = None) -> tuple[Path, Path]:
    # Re-read env on each call so tests/ops can override PROCESS_DOCUMENTS_* at runtime.
    raw = Path(raw_root or os.environ.get("PROCESS_DOCUMENTS_RAW_ROOT") or DEFAULT_RAW_ROOT)
    meta = Path(meta_root or os.environ.get("PROCESS_DOCUMENTS_META_ROOT") or DEFAULT_META_ROOT)
    raw.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    return raw, meta


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cas_path(raw_root: Path, sha256: str, extension: str | None = None) -> Path:
    """Two-level CAS path: ab/cd/<sha256>[.ext]."""
    if len(sha256) < 4:
        raise ValueError("invalid sha256")
    ext = ""
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        ext = _SAFE_NAME.sub("", ext)[:16]
    return raw_root / "cas" / sha256[:2] / sha256[2:4] / f"{sha256}{ext}"


def store_blob(
    data: bytes,
    *,
    raw_root: Path | None = None,
    extension: str | None = None,
    declared_filename: str | None = None,
) -> StoredBlob:
    """Idempotent content-addressed write. Never stores outside raw_root."""
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"document exceeds MAX_DOCUMENT_BYTES ({MAX_DOCUMENT_BYTES})")
    if not data:
        raise ValueError("refusing to store empty blob")
    if data.startswith(b"%PDF"):
        validate_pdf_limits(data)
    raw, _ = ensure_roots(raw_root=raw_root)
    digest = sha256_bytes(data)
    ext = extension
    if not ext and declared_filename and "." in declared_filename:
        ext = declared_filename.rsplit(".", 1)[-1].lower()
    path = cas_path(raw, digest, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    unchanged = path.is_file() and path.stat().st_size == len(data)
    if not unchanged:
        tmp = path.with_suffix(path.suffix + ".partial")
        tmp.write_bytes(data)
        tmp.replace(path)
    return StoredBlob(
        sha256=digest,
        size_bytes=len(data),
        raw_uri=f"cas://process_documents/{digest}",
        path=path,
        unchanged=unchanged,
    )


def validate_pdf_limits(data: bytes) -> None:
    """Fail closed on oversized or implausibly page-dense PDF payloads."""
    if len(data) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds MAX_PDF_BYTES ({MAX_PDF_BYTES})")
    page_markers = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    if page_markers > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds MAX_PDF_PAGES ({MAX_PDF_PAGES})")


def detect_mime(data: bytes, declared: str | None = None) -> str:
    """Lightweight magic-byte MIME detection (no external deps)."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data.lstrip()[:5].lower() in (b"<!doc", b"<html", b"<head", b"<body"):
        return "text/html"
    if declared:
        return declared
    return "application/octet-stream"


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    """Extract ZIP with path-traversal and bomb protections."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValueError(f"ZIP has too many members ({len(infos)} > {MAX_ZIP_MEMBERS})")
        total_uncompressed = sum(i.file_size for i in infos)
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED:
            raise ValueError("ZIP uncompressed size exceeds limit (zip bomb protection)")
        dest_resolved = dest_dir.resolve()
        for info in infos:
            if info.is_dir():
                continue
            # Strip absolute / parent traversal
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"ZIP path traversal blocked: {info.filename}")
            target = (dest_dir / name).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ValueError(f"ZIP path escapes dest: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                written = 0
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_DOCUMENT_BYTES:
                        raise ValueError("ZIP member exceeds MAX_DOCUMENT_BYTES")
                    out.write(chunk)
            extracted.append(target)
    return extracted


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows
