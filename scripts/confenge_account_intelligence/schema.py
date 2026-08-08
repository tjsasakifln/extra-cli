"""Lightweight validation against confenge-account-intelligence-v1 required fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.models import SCHEMA_ID

_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "confenge-account-intelligence-v1.schema.json"

REQUIRED_TOP_LEVEL = (
    "schema_id",
    "schema_version",
    "catalog_version",
    "generated_at",
    "as_of",
    "cnpj_root",
    "source_hash",
    "account_snapshot",
    "portfolio_summary",
    "why_now",
    "confirmed_facts",
    "strong_inferences",
    "weak_inferences",
    "internal_structure_hypothesis",
    "primary_service",
    "secondary_service",
    "service_fit_rationale",
    "fact_to_mention",
    "question_to_ask",
    "cta",
    "objection_expected",
    "claims_to_avoid",
    "message_tone",
    "research_gaps",
    "evidence",
    "dominant_state",
    "cache_key",
)


def load_json_schema() -> dict[str, Any]:
    data: Any = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("schema root must be an object")
    return data


def validate_dossier(dossier: dict[str, Any]) -> list[str]:
    """Return list of validation errors (empty if ok). No network; no jsonschema dep required."""
    errors: list[str] = []
    if dossier.get("schema_id") != SCHEMA_ID:
        errors.append(f"schema_id must be {SCHEMA_ID!r}")
    for key in REQUIRED_TOP_LEVEL:
        if key not in dossier:
            errors.append(f"missing required field: {key}")
    hyp = dossier.get("internal_structure_hypothesis")
    if isinstance(hyp, dict) and hyp.get("assertion_as_fact") is not False:
        errors.append("internal_structure_hypothesis.assertion_as_fact must be false")
    # Epistemic separation: confirmed_facts must not contain inference classes
    for item in dossier.get("confirmed_facts") or []:
        if not isinstance(item, dict):
            errors.append("confirmed_facts items must be objects")
            continue
        if item.get("epistemic_class") != "confirmed":
            errors.append(f"confirmed_facts item {item.get('id')} has class {item.get('epistemic_class')}")
        if "evidence_ids" not in item:
            errors.append(f"confirmed_facts item {item.get('id')} missing evidence_ids")
    for item in (dossier.get("strong_inferences") or []) + (dossier.get("weak_inferences") or []):
        if not isinstance(item, dict):
            continue
        if item.get("epistemic_class") == "confirmed":
            errors.append(f"inference item {item.get('id')} incorrectly labeled confirmed")
    primary = dossier.get("primary_service")
    if isinstance(primary, dict) and not primary.get("service_id"):
        errors.append("primary_service.service_id required")
    return errors
