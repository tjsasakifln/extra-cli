"""JSONL I/O helpers — fail-closed on missing/unreadable paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """Required input path missing, unreadable, or malformed."""


def require_readable_file(path: Path | str, *, label: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise InputError(f"required input missing: {label} path={p}")
    if not p.is_file():
        raise InputError(f"required input not a file: {label} path={p}")
    try:
        # probe readability
        with p.open("rb") as fh:
            fh.read(1)
            fh.seek(0)
    except OSError as exc:
        raise InputError(f"required input unreadable: {label} path={p} error={exc}") from exc
    return p


def read_jsonl(path: Path | str, *, label: str) -> list[dict[str, Any]]:
    p = require_readable_file(path, label=label)
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputError(f"invalid JSONL in {label} line={lineno}: {exc}") from exc
            if not isinstance(obj, dict):
                raise InputError(f"JSONL row must be object in {label} line={lineno}")
            rows.append(obj)
    return rows


def write_json(path: Path, data: Any, *, sort_keys: bool = True) -> str:
    """Write canonical JSON; return content hash (sha256 hex of bytes written)."""
    import hashlib

    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys, default=str) + "\n"
    raw = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def content_hash_bytes(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def content_hash_obj(data: Any, *, sort_keys: bool = True) -> str:
    import hashlib

    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=sort_keys, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
