"""Immutable case store layout helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.budget_audit.hashing import sha256_file


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_case_dir(case: str | Path) -> Path:
    p = Path(case).expanduser().resolve()
    if not p.exists():
        # try under BUDGET_CASE_ROOT
        root = os.environ.get("BUDGET_CASE_ROOT")
        if root:
            alt = Path(root) / case
            if alt.exists():
                return alt.resolve()
        raise FileNotFoundError(f"case directory not found: {case}")
    return p


def case_subdirs(case_dir: Path) -> dict[str, Path]:
    return {
        "sources": case_dir / "sources",
        "objects": case_dir / "objects",
        "workbooks": case_dir / "workbooks",
        "mapping": case_dir / "mapping",
        "normalized": case_dir / "normalized",
        "audits": case_dir / "audits",
        "reports": case_dir / "reports",
    }


def ensure_case_layout(case_dir: Path) -> dict[str, Path]:
    case_dir.mkdir(parents=True, exist_ok=True)
    subs = case_subdirs(case_dir)
    for p in subs.values():
        p.mkdir(parents=True, exist_ok=True)
    return subs


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def store_object(case_dir: Path, source_path: Path) -> dict[str, Any]:
    """Copy source into objects/<sha256><ext> content-addressed store. Never overwrite different content.

    Extension is preserved so parsers can detect format from the object path.
    """
    digest = sha256_file(source_path)
    objects = case_dir / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    ext = source_path.suffix.lower()
    dest = objects / f"{digest}{ext}"
    # also accept legacy extensionless object
    legacy = objects / digest
    if dest.exists():
        existing = sha256_file(dest)
        if existing != digest:
            raise RuntimeError(f"object collision with different content: {digest}")
    elif legacy.exists():
        existing = sha256_file(legacy)
        if existing != digest:
            raise RuntimeError(f"object collision with different content: {digest}")
        dest = legacy
    else:
        dest.write_bytes(source_path.read_bytes())
        try:
            dest.chmod(0o444)
        except OSError:
            pass
    return {
        "sha256": digest,
        "object_path": str(dest.relative_to(case_dir)),
        "size_bytes": dest.stat().st_size,
        "original_name": source_path.name,
        "extension": ext,
    }


def load_manifest(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "case-manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"case-manifest.json missing in {case_dir}")
    return read_json(path)


def save_manifest(case_dir: Path, manifest: dict[str, Any]) -> None:
    write_json(case_dir / "case-manifest.json", manifest)
