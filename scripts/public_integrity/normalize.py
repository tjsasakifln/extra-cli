"""Normalize CEIS/CNEP records without dropping originals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from scripts.public_integrity.models import ObservedRecord


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _nested_text(raw: dict[str, Any], *path: str) -> str:
    node: Any = raw
    for key in path:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    if node is None:
        return ""
    return str(node).strip()


def official_id_from(raw: dict[str, Any]) -> str | None:
    for key in ("id", "idSancao", "codigoSancao"):
        value = raw.get(key)
        if value is None or value == "":
            continue
        return str(value)
    return None


def normalize_record(
    raw: Any,
    *,
    source_id: str,
    source_url: str,
    captured_at: str,
    type_path: tuple[str, ...],
) -> ObservedRecord | None:
    if not isinstance(raw, dict):
        return None
    official_id = official_id_from(raw)
    if not official_id:
        return None
    record_type = _nested_text(raw, *type_path)
    authority = _nested_text(raw, "orgaoSancionador", "nome")
    start_date = parse_date(raw.get("dataInicioSancao"))
    end_date = parse_date(raw.get("dataFinalSancao"))
    observed_status = record_type or "present_in_source"
    return ObservedRecord(
        source_id=source_id,
        official_id=official_id,
        record_type=record_type,
        authority=authority,
        start_date=start_date,
        end_date=end_date,
        observed_status=observed_status,
        source_url=source_url,
        captured_at=captured_at,
        original=dict(raw),
    )
