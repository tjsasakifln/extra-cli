"""Deterministic JSON and SHA-256 helpers. Execution timestamps stay out of hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from scripts.official_contract_semantics.constants import EXECUTION_TIMESTAMP_FIELDS


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value


def canonical_dumps(payload: Any) -> str:
    return json.dumps(jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_hash(payload: Any) -> str:
    return sha256_text(canonical_dumps(payload))


def semantic_payload(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if key not in EXECUTION_TIMESTAMP_FIELDS}


def semantic_hash(mapping: dict[str, Any]) -> str:
    return content_hash(semantic_payload(mapping))


def write_json(path: Any, payload: Any) -> str:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_text(text, encoding="utf-8")
    return sha256_text(text)


def write_jsonl(path: Any, rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: str(row.get("observation_id") or row.get("id") or canonical_dumps(row)))
    lines = [canonical_dumps(row) for row in ordered]
    text = ("\n".join(lines) + "\n") if lines else ""
    target.write_text(text, encoding="utf-8")
    return sha256_text(text)


def load_json(path: Any) -> Any:
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Any) -> list[dict[str, Any]]:
    from pathlib import Path

    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
