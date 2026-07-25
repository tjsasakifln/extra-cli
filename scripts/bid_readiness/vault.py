"""Content-addressed local vault — originals immutable by SHA-256."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class VaultObject:
    document_id: str
    original_name: str
    sha256: str
    size: int
    content_type: str
    extension: str
    source_path: str
    ingested_at: str
    classification: str
    sensitivity: str
    retention_policy: str
    vault_relpath: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def store_bytes(
    vault_root: Path,
    data: bytes,
    *,
    original_name: str,
    source_path: str,
    document_id: str | None = None,
    classification: str = "UNKNOWN",
    sensitivity: str = "CONFIDENTIAL",
    retention_policy: str = "case-local-not-git",
) -> VaultObject:
    digest = sha256_bytes(data)
    objects = vault_root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    dest = objects / digest
    if dest.exists():
        existing = dest.read_bytes()
        if existing != data:
            raise RuntimeError(f"hash collision with different bytes: {digest}")
        # immutability: never overwrite
    else:
        dest.write_bytes(data)

    ext = Path(original_name).suffix.lower().lstrip(".")
    ctype = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    doc_id = document_id or f"doc-{digest[:12]}"
    return VaultObject(
        document_id=doc_id,
        original_name=original_name,
        sha256=digest,
        size=len(data),
        content_type=ctype,
        extension=ext or "bin",
        source_path=source_path,
        ingested_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        classification=classification,
        sensitivity=sensitivity,
        retention_policy=retention_policy,
        vault_relpath=f"vault/objects/{digest}",
    )


def store_file(vault_root: Path, path: Path, **kwargs: Any) -> VaultObject:
    data = path.read_bytes()
    return store_bytes(
        vault_root,
        data,
        original_name=kwargs.pop("original_name", path.name),
        source_path=kwargs.pop("source_path", str(path)),
        **kwargs,
    )


def verify_object(vault_root: Path, sha256: str) -> bool:
    path = vault_root / "objects" / sha256
    if not path.is_file():
        return False
    return sha256_file(path) == sha256


def read_object(vault_root: Path, sha256: str) -> bytes:
    path = vault_root / "objects" / sha256
    data = path.read_bytes()
    if sha256_bytes(data) != sha256:
        raise RuntimeError(f"vault object corrupted: {sha256}")
    return data


def vault_object_to_dict(obj: VaultObject) -> dict[str, Any]:
    return asdict(obj)


def write_inventory(path: Path, objects: list[VaultObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(objects),
        "documents": [vault_object_to_dict(o) for o in objects],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_original_immutable(src: Path, dest: Path) -> str:
    """Copy bytes without transformation; return sha256."""
    data = src.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.read_bytes() != data:
        raise RuntimeError(f"refusing to alter existing file: {dest}")
    if not dest.exists():
        shutil.copyfile(src, dest)
    return sha256_bytes(data)
