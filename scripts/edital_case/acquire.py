"""Source acquisition: local files, directories, ZIPs, public URLs.

Safe unpacking with path traversal / zip-bomb protection.
No VPS, no database.
"""

from __future__ import annotations

import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.edital_case.isolation import IsolationError, assert_no_foreign_paths
from scripts.edital_case.models import (
    EXECUTABLE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    ZIP_MAX_FILES,
    ZIP_MAX_RATIO,
    ZIP_MAX_SINGLE_FILE,
    ZIP_MAX_UNCOMPRESSED_BYTES,
)
from scripts.edital_case.store import put_object, sha256_bytes, utc_now, write_json


class AcquisitionError(RuntimeError):
    pass


def _guess_content_type(path: Path, data: bytes | None = None) -> str:
    if data and data[:4] == b"%PDF":
        return "application/pdf"
    if data and data[:2] == b"PK":
        return "application/zip"
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype or "application/octet-stream"


def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def fetch_url(url: str, *, timeout: int = 60) -> tuple[bytes, dict[str, Any]]:
    if not url.lower().startswith(("http://", "https://")):
        raise AcquisitionError(f"only public http(s) URLs allowed: {url}")
    # hard deny private/prod hosts
    low = url.lower()
    for bad in ("ec-prod", "localhost", "127.0.0.1", "0.0.0.0", "/opt/extra"):  # noqa: S104
        if bad in low:
            raise AcquisitionError(f"forbidden URL target: {url}")
    req = Request(  # noqa: S310
        url,
        headers={
            "User-Agent": "extra-cli-edital-triage/1.0 (+local campaign; public docs only)",
            "Accept": "*/*",
        },
        method="GET",
    )
    meta: dict[str, Any] = {
        "url": url,
        "method": "HTTP_GET",
        "acquired_at": utc_now(),
    }
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public docs only; guard above
            data = resp.read()
            meta["http_status"] = getattr(resp, "status", None) or resp.getcode()
            meta["content_type"] = resp.headers.get("Content-Type")
            meta["etag"] = resp.headers.get("ETag")
            meta["last_modified"] = resp.headers.get("Last-Modified")
            meta["content_length_header"] = resp.headers.get("Content-Length")
    except HTTPError as exc:
        meta["http_status"] = exc.code
        meta["error"] = str(exc)
        raise AcquisitionError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        meta["error"] = str(exc)
        raise AcquisitionError(f"URL error for {url}: {exc}") from exc
    meta["size"] = len(data)
    meta["sha256"] = sha256_bytes(data)
    return data, meta


def _safe_zip_member_name(name: str) -> str | None:
    # reject absolute, traversal, symlink-like
    if not name or name.endswith("/"):
        return None
    norm = name.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    if any(p.startswith(".") and p not in (".",) for p in parts if p == ".."):
        pass
    return "/".join(parts)


def safe_extract_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    max_files: int = ZIP_MAX_FILES,
    max_uncompressed: int = ZIP_MAX_UNCOMPRESSED_BYTES,
    max_ratio: int = ZIP_MAX_RATIO,
    max_single: int = ZIP_MAX_SINGLE_FILE,
) -> list[dict[str, Any]]:
    """Extract ZIP safely; return list of extracted file metadata."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    if not zipfile.is_zipfile(zip_path):
        raise AcquisitionError(f"not a zip file: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise AcquisitionError(
                f"ZIP has too many entries: {len(infos)} > {max_files}"
            )
        total_uncomp = sum(i.file_size for i in infos)
        total_comp = sum(i.compress_size for i in infos) or 1
        if total_uncomp > max_uncompressed:
            raise AcquisitionError(
                f"ZIP uncompressed size {total_uncomp} exceeds limit {max_uncompressed}"
            )
        if total_uncomp / total_comp > max_ratio and total_uncomp > 10 * 1024 * 1024:
            raise AcquisitionError(
                f"ZIP compression ratio too high ({total_uncomp / total_comp:.1f})"
            )

        for info in infos:
            if info.is_dir():
                continue
            # symlink / absolute checks
            if info.external_attr and (info.external_attr >> 16) & 0o170000 == 0o120000:
                results.append(
                    {
                        "name": info.filename,
                        "status": "REJECTED",
                        "reason": "symlink",
                    }
                )
                continue
            safe_name = _safe_zip_member_name(info.filename)
            if not safe_name:
                results.append(
                    {
                        "name": info.filename,
                        "status": "REJECTED",
                        "reason": "unsafe_path",
                    }
                )
                continue
            if info.file_size > max_single:
                results.append(
                    {
                        "name": info.filename,
                        "status": "REJECTED",
                        "reason": "file_too_large",
                        "size": info.file_size,
                    }
                )
                continue
            ext = Path(safe_name).suffix.lower()
            if ext in EXECUTABLE_EXTENSIONS:
                results.append(
                    {
                        "name": info.filename,
                        "status": "REJECTED",
                        "reason": "executable_extension",
                        "extension": ext,
                    }
                )
                continue

            target = dest_dir / safe_name
            target.parent.mkdir(parents=True, exist_ok=True)
            # ensure still under dest_dir
            try:
                target.resolve().relative_to(dest_dir.resolve())
            except ValueError:
                results.append(
                    {
                        "name": info.filename,
                        "status": "REJECTED",
                        "reason": "path_escape",
                    }
                )
                continue
            with zf.open(info, "r") as src, target.open("wb") as out:
                written = 0
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_single:
                        raise AcquisitionError(
                            f"ZIP member exceeded max size during extract: {info.filename}"
                        )
                    out.write(chunk)
            results.append(
                {
                    "name": info.filename,
                    "safe_name": safe_name,
                    "path": str(target),
                    "size": written,
                    "status": "EXTRACTED",
                    "compress_size": info.compress_size,
                }
            )
    return results


def acquire_source(
    source: str,
    case_dir: Path,
    *,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Acquire source into case store objects; return acquisition manifest."""
    assert_no_foreign_paths(case_dir)
    work_dir = work_dir or (case_dir / "sources" / "staging")
    work_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    errors: list[str] = []

    def _ingest_file(
        path: Path,
        *,
        origin: str,
        method: str,
        parent_zip: str | None = None,
        http_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert_no_foreign_paths(path)
        data = path.read_bytes()
        obj = put_object(case_dir, data, filename=path.name)
        rec: dict[str, Any] = {
            "original_name": path.name,
            "original_path": str(path),
            "origin": origin,
            "method": method,
            "extension": path.suffix.lower(),
            "content_type": _guess_content_type(path, data),
            "size": obj["size"],
            "sha256": obj["sha256"],
            "parent_zip_sha256": parent_zip,
            "acquired_at": utc_now(),
            "supported": path.suffix.lower() in SUPPORTED_EXTENSIONS
            or path.suffix.lower() == "",
            "error": None,
        }
        if http_meta:
            rec.update(
                {
                    "http_status": http_meta.get("http_status"),
                    "etag": http_meta.get("etag"),
                    "last_modified": http_meta.get("last_modified"),
                    "url": http_meta.get("url"),
                }
            )
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS and path.suffix.lower() not in {
            ".zip",
            "",
        }:
            rec["status"] = "UNSUPPORTED"
        else:
            rec["status"] = "ACQUIRED"
        return rec

    if _is_url(source):
        try:
            data, http_meta = fetch_url(source)
            fname = source.rstrip("/").split("/")[-1] or "download.bin"
            fname = re.sub(r"[^a-zA-Z0-9._-]+", "_", fname)[:120]
            local = work_dir / fname
            local.write_bytes(data)
            rec = _ingest_file(
                local, origin=source, method="HTTP_GET", http_meta=http_meta
            )
            records.append(rec)
            if local.suffix.lower() == ".zip" or data[:2] == b"PK":
                zdest = work_dir / f"unzip-{rec['sha256'][:12]}"
                try:
                    extracted = safe_extract_zip(local, zdest)
                    for ex in extracted:
                        if ex.get("status") != "EXTRACTED":
                            records.append(
                                {
                                    "original_name": ex.get("name"),
                                    "status": ex.get("status"),
                                    "reason": ex.get("reason"),
                                    "method": "ZIP_MEMBER",
                                    "parent_zip_sha256": rec["sha256"],
                                    "origin": source,
                                    "acquired_at": utc_now(),
                                }
                            )
                            continue
                        er = _ingest_file(
                            Path(ex["path"]),
                            origin=source,
                            method="ZIP_MEMBER",
                            parent_zip=rec["sha256"],
                        )
                        records.append(er)
                except AcquisitionError as exc:
                    errors.append(str(exc))
        except (AcquisitionError, IsolationError) as exc:
            errors.append(str(exc))
            records.append(
                {
                    "origin": source,
                    "method": "HTTP_GET",
                    "status": "ERROR",
                    "error": str(exc),
                    "acquired_at": utc_now(),
                }
            )
    else:
        path = Path(source).expanduser().resolve()
        assert_no_foreign_paths(path)
        if not path.exists():
            raise AcquisitionError(f"source not found: {path}")
        if path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file())
            for f in files:
                if f.suffix.lower() == ".zip":
                    rec = _ingest_file(f, origin=str(f), method="LOCAL_FILE")
                    records.append(rec)
                    zdest = work_dir / f"unzip-{rec['sha256'][:12]}"
                    try:
                        extracted = safe_extract_zip(f, zdest)
                        for ex in extracted:
                            if ex.get("status") != "EXTRACTED":
                                records.append(
                                    {
                                        "original_name": ex.get("name"),
                                        "status": ex.get("status"),
                                        "reason": ex.get("reason"),
                                        "method": "ZIP_MEMBER",
                                        "parent_zip_sha256": rec["sha256"],
                                        "origin": str(f),
                                        "acquired_at": utc_now(),
                                    }
                                )
                                continue
                            records.append(
                                _ingest_file(
                                    Path(ex["path"]),
                                    origin=str(f),
                                    method="ZIP_MEMBER",
                                    parent_zip=rec["sha256"],
                                )
                            )
                    except AcquisitionError as exc:
                        errors.append(str(exc))
                else:
                    records.append(
                        _ingest_file(f, origin=str(f), method="LOCAL_FILE")
                    )
        else:
            rec = _ingest_file(path, origin=str(path), method="LOCAL_FILE")
            records.append(rec)
            if path.suffix.lower() == ".zip":
                zdest = work_dir / f"unzip-{rec['sha256'][:12]}"
                try:
                    extracted = safe_extract_zip(path, zdest)
                    for ex in extracted:
                        if ex.get("status") != "EXTRACTED":
                            records.append(
                                {
                                    "original_name": ex.get("name"),
                                    "status": ex.get("status"),
                                    "reason": ex.get("reason"),
                                    "method": "ZIP_MEMBER",
                                    "parent_zip_sha256": rec["sha256"],
                                    "origin": str(path),
                                    "acquired_at": utc_now(),
                                }
                            )
                            continue
                        records.append(
                            _ingest_file(
                                Path(ex["path"]),
                                origin=str(path),
                                method="ZIP_MEMBER",
                                parent_zip=rec["sha256"],
                            )
                        )
                except AcquisitionError as exc:
                    errors.append(str(exc))

    # dedupe by sha256 keeping first name
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for rec in records:
        sha = rec.get("sha256")
        if not sha:
            unique.append(rec)
            continue
        if sha in seen:
            duplicates.append(rec)
            rec = {**rec, "status": "DUPLICATE_CONTENT", "duplicate_of": sha}
            unique.append(rec)
        else:
            seen.add(sha)
            unique.append(rec)

    acquisition = {
        "source": source,
        "acquired_at": utc_now(),
        "records": unique,
        "duplicates": [
            {"sha256": d.get("sha256"), "original_name": d.get("original_name")}
            for d in duplicates
        ],
        "errors": errors,
        "production_touched": False,
        "soak_touched": False,
        "vps_accessed": False,
        "database_used": False,
    }
    write_json(case_dir / "sources" / "acquisition.json", acquisition)
    return acquisition
