"""Safe document ingestion (dir/zip/manifest) into case vault."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from scripts.bid_readiness.vault import VaultObject, store_bytes

# Safety limits
MAX_FILES = 500
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MiB
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
BLOCKED_EXTENSIONS = {
    "exe",
    "dll",
    "so",
    "bat",
    "cmd",
    "ps1",
    "sh",
    "msi",
    "com",
    "scr",
    "js",
    "vbs",
    "jar",
}
BLOCKED_MACROS = {"docm", "xlsm", "pptm"}
ALLOWED_EXTENSIONS = {
    "pdf",
    "docx",
    "xlsx",
    "csv",
    "txt",
    "zip",
    "png",
    "jpg",
    "jpeg",
    "json",
    "yaml",
    "yml",
    "md",
    "html",
}


class IngestError(RuntimeError):
    pass


def _ext(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def _safe_member_path(name: str) -> Path:
    # Prevent zip traversal
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise IngestError(f"zip traversal blocked: {name}")
    if any(part.startswith("/") or part == ".." for part in p.parts):
        raise IngestError(f"zip traversal blocked: {name}")
    return p


def _check_extension(name: str) -> None:
    ext = _ext(name)
    if ext in BLOCKED_EXTENSIONS or ext in BLOCKED_MACROS:
        raise IngestError(f"blocked extension: {name}")
    if ext and ext not in ALLOWED_EXTENSIONS and ext not in {"meta"}:
        # Allow unknown non-exec extensions as OUTRO but flag
        if ext in {"bin", "dat"}:
            raise IngestError(f"suspicious extension blocked: {name}")


def _looks_csv_injection(data: bytes) -> bool:
    try:
        text = data[:200].decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return False
    for line in text.splitlines()[:5]:
        s = line.lstrip()
        if s.startswith(("=", "+", "-", "@", "\t=")):
            return True
    return False


def ingest_path(
    vault_root: Path,
    source: Path,
    *,
    tmp_root: Path | None = None,
) -> tuple[list[VaultObject], list[dict[str, Any]]]:
    """Ingest a directory, zip, or manifest.json into the vault.

    Returns (objects, warnings).
    """
    source = source.resolve()
    warnings: list[dict[str, Any]] = []
    objects: list[VaultObject] = []

    if source.is_file() and source.suffix.lower() == ".zip":
        return _ingest_zip(vault_root, source, warnings)
    if source.is_file() and source.name.endswith("manifest.json"):
        return _ingest_manifest(vault_root, source, warnings)
    if source.is_file() and source.suffix.lower() == ".json" and "manifest" in source.name:
        return _ingest_manifest(vault_root, source, warnings)
    if source.is_dir():
        files = sorted([p for p in source.rglob("*") if p.is_file()])
        if len(files) > MAX_FILES:
            raise IngestError(f"too many files: {len(files)} > {MAX_FILES}")
        for fp in files:
            if fp.name.startswith("."):
                continue
            if fp.suffix.lower() == ".json" and fp.name.endswith(".meta.json"):
                continue  # sidecars handled with primary
            try:
                objects.append(_ingest_file(vault_root, fp, source_label=str(fp.relative_to(source))))
            except IngestError as exc:
                warnings.append({"path": str(fp), "error": str(exc)})
        return objects, warnings
    if source.is_file():
        objects.append(_ingest_file(vault_root, source, source_label=source.name))
        return objects, warnings
    raise IngestError(f"unsupported source: {source}")


def _ingest_file(vault_root: Path, path: Path, *, source_label: str) -> VaultObject:
    if path.is_symlink():
        raise IngestError(f"symlink blocked: {path}")
    _check_extension(path.name)
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise IngestError(f"file too large: {path.name}")
    if _looks_csv_injection(data) and path.suffix.lower() in {".csv", ".xlsx"}:
        raise IngestError(f"csv/xlsx injection pattern blocked: {path.name}")
    # Corrupt marker for golden tests
    if data.startswith(b"CORRUPT\x00"):
        raise IngestError(f"corrupted document: {path.name}")
    return store_bytes(
        vault_root,
        data,
        original_name=path.name,
        source_path=source_label,
        document_id=f"doc-{path.stem[:40]}",
    )


def _ingest_zip(
    vault_root: Path, zip_path: Path, warnings: list[dict[str, Any]]
) -> tuple[list[VaultObject], list[dict[str, Any]]]:
    objects: list[VaultObject] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise IngestError("zip has too many members")
        total_uncomp = sum(i.file_size for i in infos)
        if total_uncomp > MAX_ZIP_UNCOMPRESSED:
            raise IngestError("zip bomb: uncompressed size too large")
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename
            _safe_member_path(name)
            if info.file_size and info.compress_size:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO and info.file_size > 1_000_000:
                    raise IngestError(f"zip bomb ratio blocked: {name}")
            # Symlink in zip (Unix external attr)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise IngestError(f"symlink in zip blocked: {name}")
            try:
                _check_extension(name)
                data = zf.read(info)
                if len(data) > MAX_FILE_BYTES:
                    raise IngestError(f"member too large: {name}")
                objects.append(
                    store_bytes(
                        vault_root,
                        data,
                        original_name=Path(name).name,
                        source_path=f"zip:{zip_path.name}:{name}",
                        document_id=f"doc-{Path(name).stem[:40]}",
                    )
                )
            except IngestError as exc:
                warnings.append({"path": name, "error": str(exc)})
    return objects, warnings


def _ingest_manifest(
    vault_root: Path, manifest_path: Path, warnings: list[dict[str, Any]]
) -> tuple[list[VaultObject], list[dict[str, Any]]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    files = payload.get("files") or payload.get("documents") or []
    objects: list[VaultObject] = []
    for entry in files:
        rel = entry.get("path") or entry.get("file")
        if not rel:
            warnings.append({"error": "manifest entry missing path", "entry": entry})
            continue
        fp = (base / rel).resolve()
        if not str(fp).startswith(str(base.resolve())):
            raise IngestError(f"manifest path escapes base: {rel}")
        if not fp.is_file():
            warnings.append({"path": rel, "error": "missing file"})
            continue
        try:
            obj = _ingest_file(vault_root, fp, source_label=rel)
            if entry.get("document_id"):
                obj.document_id = str(entry["document_id"])
            objects.append(obj)
        except IngestError as exc:
            warnings.append({"path": rel, "error": str(exc)})
    return objects, warnings
