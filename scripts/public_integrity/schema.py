"""Validate a produced payload against the shipped contract (no jsonschema dep)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_integrity.models import (
    CONTRACTED_SOURCES,
    FORBIDDEN_PAYLOAD_FIELDS,
    INTEGRITY_STATES,
    PAYLOAD_FIELDS,
    PRODUCER_VERSION,
    RECORD_FIELDS,
    SCHEMA_VERSION,
    SOURCE_FIELDS,
)

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts"
CONTRACT_JSON = CONTRACT_DIR / "public-read-integrity-v1.json"
CONTRACT_SCHEMA = CONTRACT_DIR / "public-read-integrity-v1.schema.json"


def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))


def load_schema() -> dict[str, Any]:
    return json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema = load_schema()
    required = schema.get("required") or list(PAYLOAD_FIELDS)
    for field in required:
        if field not in payload:
            errors.append(f"missing:{field}")
    if payload.get("schema") != SCHEMA_VERSION:
        errors.append("schema")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if payload.get("producer_version") != PRODUCER_VERSION:
        errors.append("producer_version")
    if payload.get("not_legal_conclusion") is not True:
        errors.append("not_legal_conclusion")
    if payload.get("aggregate_state") not in INTEGRITY_STATES:
        errors.append("aggregate_state")
    if list(payload.get("contracted_sources") or []) != list(CONTRACTED_SOURCES):
        errors.append("contracted_sources")
    freshness = payload.get("freshness") or {}
    if freshness.get("policy") != "public-read-integrity-ttl/1.0":
        errors.append("freshness.policy")
    if freshness.get("status") not in {"current", "stale", "expired"}:
        errors.append("freshness.status")
    if not isinstance(freshness.get("is_current"), bool):
        errors.append("freshness.is_current")
    sources = payload.get("sources") or {}
    for source_id in CONTRACTED_SOURCES:
        source = sources.get(source_id) or {}
        for field in SOURCE_FIELDS:
            if field not in source:
                errors.append(f"sources.{source_id}.{field}")
        if source.get("status") not in INTEGRITY_STATES:
            errors.append(f"sources.{source_id}.status")
    for index, record in enumerate(payload.get("records") or []):
        for field in RECORD_FIELDS:
            if field not in record:
                errors.append(f"records[{index}].{field}")
    for key in payload:
        if key in FORBIDDEN_PAYLOAD_FIELDS:
            errors.append(f"forbidden_field:{key}")
    if payload.get("aggregate_state") == "NO_MATCH_CONFIRMED":
        sources = payload.get("sources") or {}
        if not all((sources.get(item) or {}).get("coverage_complete") for item in CONTRACTED_SOURCES):
            errors.append("no_match_without_coverage")
        if payload.get("records"):
            errors.append("no_match_with_records")
    return errors
