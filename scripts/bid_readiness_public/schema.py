"""Validate a produced envelope against the shipped 1.0 contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bid_readiness_public.models import SCHEMA_VERSION
from scripts.bid_readiness_public.validators import validate_envelope

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "public-read-bid-readiness"
CONTRACT_JSON = CONTRACT_DIR / "public-read-bid-readiness-v1.json"
CONTRACT_SCHEMA = CONTRACT_DIR / "public-read-bid-readiness-v1.schema.json"


def _load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"expected object JSON in {path}")
    return data


def load_contract() -> dict[str, Any]:
    return _load_object(CONTRACT_JSON)


def load_schema() -> dict[str, Any]:
    return _load_object(CONTRACT_SCHEMA)


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors = validate_envelope(payload)
    schema = load_schema()
    required = schema.get("required") or []
    for field in required:
        if field not in payload:
            errors.append(f"schema.missing:{field}")
    if (
        payload.get("schema_version") != schema.get("schema_version")
        and payload.get("schema_version") != SCHEMA_VERSION
    ):
        errors.append("schema.schema_version")
    return errors
