"""Safe ZIP extraction — blocks traversal, bombs, symlinks, absolute paths."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from scripts.budget_audit.constants import (
    MAX_SINGLE_FILE_BYTES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_BYTES,
)


class ZipSafetyError(ValueError):
    """Unsafe ZIP content rejected."""


@dataclass
class SafeExtractResult:
    extracted: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_safe_member_name(name: str) -> tuple[bool, str]:
    if not name or name.endswith("/"):
        return False, "directory_or_empty"
    # normalize separators
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or name.startswith("/") or name.startswith("\\"):
        return False, "absolute_path"
    if ".." in pure.parts:
        return False, "path_traversal"
    if any(part.startswith("/") for part in pure.parts):
        return False, "absolute_segment"
    return True, "ok"


def inspect_zip(path: Path | str) -> dict:
    """Inspect ZIP without extracting; raise on bomb indicators."""
    zpath = Path(path)
    with zipfile.ZipFile(zpath, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ZipSafetyError(
                f"ZIP has {len(infos)} members > MAX_ZIP_MEMBERS={MAX_ZIP_MEMBERS}"
            )
        total_uncompressed = 0
        members = []
        for info in infos:
            total_uncompressed += int(info.file_size)
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                raise ZipSafetyError(
                    f"member {info.filename!r} size {info.file_size} exceeds limit"
                )
            # zip bomb ratio
            if info.compress_size > 0 and info.file_size / max(info.compress_size, 1) > 1000:
                raise ZipSafetyError(
                    f"suspicious compression ratio for {info.filename!r}"
                )
            safe, reason = _is_safe_member_name(info.filename)
            members.append(
                {
                    "name": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                    "safe": safe,
                    "reason": reason,
                }
            )
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ZipSafetyError(
                f"total uncompressed {total_uncompressed} exceeds limit"
            )
        return {
            "member_count": len(infos),
            "total_uncompressed": total_uncompressed,
            "members": members,
        }


def safe_extract(zip_path: Path | str, dest_dir: Path | str) -> SafeExtractResult:
    """Extract only safe members into dest_dir."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    result = SafeExtractResult()
    inspect_zip(zip_path)  # bomb checks

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                result.skipped.append({"name": info.filename, "reason": "directory"})
                continue
            # Detect symlink via external_attr (Unix)
            is_symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                result.skipped.append({"name": info.filename, "reason": "symlink"})
                result.warnings.append(f"skipped symlink: {info.filename}")
                continue
            safe, reason = _is_safe_member_name(info.filename)
            if not safe:
                result.skipped.append({"name": info.filename, "reason": reason})
                result.warnings.append(f"skipped unsafe member: {info.filename} ({reason})")
                continue
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                result.skipped.append({"name": info.filename, "reason": "escape_dest"})
                result.warnings.append(f"skipped path escape: {info.filename}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                remaining = info.file_size
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            result.extracted.append(str(Path(info.filename)))
    return result
