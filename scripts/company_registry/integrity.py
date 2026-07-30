"""File integrity: SHA-256, truncation, HTML-disguised-as-ZIP detection."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def looks_like_html(path: Path | str, *, sample: int = 512) -> bool:
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return False
    with p.open("rb") as f:
        head = f.read(sample).lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or head.startswith(
        b"<head"
    )


def looks_like_zip(path: Path | str) -> bool:
    p = Path(path)
    if not p.is_file() or p.stat().st_size < 4:
        return False
    with p.open("rb") as f:
        magic = f.read(4)
    return magic[:2] == b"PK"


def validate_downloaded_file(
    path: Path | str,
    *,
    expected_length: int | None = None,
    expect_zip: bool = True,
) -> dict[str, Any]:
    """Validate a downloaded artifact. Returns {ok, errors, sha256, size_bytes}."""
    p = Path(path)
    errors: list[str] = []
    if not p.is_file():
        return {"ok": False, "errors": ["file_missing"], "sha256": None, "size_bytes": 0}
    size = p.stat().st_size
    if size == 0:
        errors.append("empty_file")
    if expected_length is not None and size != expected_length:
        errors.append(f"content_length_mismatch:expected={expected_length}:got={size}")
        if size < expected_length:
            errors.append("truncated")
    if looks_like_html(p):
        errors.append("html_instead_of_binary")
    if expect_zip:
        if not looks_like_zip(p):
            errors.append("not_zip_magic")
        elif not errors:
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    bad = zf.testzip()
                    if bad is not None:
                        errors.append(f"zip_corrupt_member:{bad}")
            except zipfile.BadZipFile:
                errors.append("bad_zip_file")
    digest = sha256_file(p)
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "sha256": digest,
        "size_bytes": size,
    }
