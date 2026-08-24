"""REJECT-before-parse using shipped bid_readiness ingest and budget_audit zip_safety."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.bid_readiness.ingest import (
    ALLOWED_EXTENSIONS,
    BLOCKED_EXTENSIONS,
    BLOCKED_MACROS,
    MAX_COMPRESSION_RATIO,
    MAX_FILE_BYTES,
    IngestError,
    _check_extension,
    _looks_csv_injection,
    _safe_member_path,
)
from scripts.bid_readiness_public.models import REJECT_REASON_CODES
from scripts.budget_audit.zip_safety import ZipSafetyError, inspect_zip


class RejectedInputError(RuntimeError):
    """Unsafe input refused before any engine parser."""

    def __init__(self, reason_code: str, message: str) -> None:
        if reason_code not in REJECT_REASON_CODES:
            raise ValueError(f"unknown reject reason: {reason_code}")
        self.reason_code = reason_code
        super().__init__(message)


def _ext(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def _classify_ingest_error(message: str) -> str:
    low = message.lower()
    if "traversal" in low or "escape" in low:
        return "path_traversal"
    if "zip bomb" in low or "uncompressed" in low or "compression ratio" in low:
        return "zip_bomb"
    if "too large" in low or "file too large" in low:
        return "oversized"
    if "blocked extension" in low or "suspicious extension" in low:
        if _ext(message.split(":")[-1].strip() if ":" in message else "") in BLOCKED_EXTENSIONS | BLOCKED_MACROS:
            return "malware_like" if _ext(message.split(":")[-1].strip()) in BLOCKED_EXTENSIONS else "disallowed_type"
        return "disallowed_type"
    if "symlink" in low:
        return "symlink_blocked"
    if "injection" in low:
        return "csv_injection"
    if "corrupt" in low:
        return "malware_like"
    return "disallowed_type"


def _preflight_zip(path: Path) -> None:
    try:
        inspect_zip(path)
    except ZipSafetyError as exc:
        msg = str(exc).lower()
        code = "path_traversal" if "traversal" in msg or "absolute" in msg else "zip_bomb"
        raise RejectedInputError(code, str(exc)) from exc
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            try:
                _safe_member_path(info.filename)
            except IngestError as exc:
                raise RejectedInputError("path_traversal", str(exc)) from exc
            try:
                _check_extension(info.filename)
            except IngestError as exc:
                raise RejectedInputError(_classify_ingest_error(str(exc)), str(exc)) from exc
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise RejectedInputError("symlink_blocked", f"symlink in zip blocked: {info.filename}")
            if info.file_size and info.compress_size:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO and info.file_size > 1_000_000:
                    raise RejectedInputError("zip_bomb", f"zip bomb ratio blocked: {info.filename}")


def preflight_path(path: Path) -> None:
    """Refuse unsafe files before PDF/XLSX parsers run.

    Reuses shipped extension, size, zip-bomb, traversal, and injection guards.
    """
    target = Path(path)
    if target.is_symlink():
        raise RejectedInputError("symlink_blocked", f"symlink blocked: {target}")
    if not target.exists():
        return
    name = target.name
    try:
        _check_extension(name)
    except IngestError as exc:
        ext = _ext(name)
        if ext in BLOCKED_EXTENSIONS:
            raise RejectedInputError("malware_like", str(exc)) from exc
        if ext in BLOCKED_MACROS:
            raise RejectedInputError("disallowed_type", str(exc)) from exc
        raise RejectedInputError("disallowed_type", str(exc)) from exc

    if target.is_file():
        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            raise RejectedInputError("oversized", f"file too large: {target.name}")
        suffix = target.suffix.lower()
        if suffix == ".zip":
            _preflight_zip(target)
        elif suffix == ".csv":
            sample = target.read_bytes()[:4096]
            if _looks_csv_injection(sample):
                raise RejectedInputError("csv_injection", f"csv injection pattern blocked: {target.name}")
        if _ext(name) and _ext(name) not in ALLOWED_EXTENSIONS and _ext(name) not in {"meta"}:
            if _ext(name) in {"bin", "dat"}:
                raise RejectedInputError("malware_like", f"suspicious extension blocked: {name}")
    elif target.is_dir():
        for child in sorted(target.rglob("*")):
            if child.is_file():
                preflight_path(child)
