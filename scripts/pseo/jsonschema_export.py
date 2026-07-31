"""Generate real JSON Schema (draft 2020-12) for public pSEO artifacts."""

from __future__ import annotations

from typing import Any

from scripts.pseo.models import (
    Agency,
    Archetype,
    Competition,
    ICPMethodology,
    Market,
    Opportunity,
    Price,
    ProblemService,
)


def build_json_schema() -> dict[str, Any]:
    """Composite schema with $defs for each artifact type."""
    defs: dict[str, Any] = {
        "Archetype": Archetype.model_json_schema(),
        "Market": Market.model_json_schema(),
        "Agency": Agency.model_json_schema(),
        "Price": Price.model_json_schema(),
        "Competition": Competition.model_json_schema(),
        "Opportunity": Opportunity.model_json_schema(),
        "ProblemService": ProblemService.model_json_schema(),
        "ICPMethodology": ICPMethodology.model_json_schema(),
    }
    # Force additionalProperties false on object schemas
    for name, sch in list(defs.items()):
        _forbid_additional(sch)
        defs[name] = sch

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://extra-cli.local/schemas/pseo-public-export.json",
        "title": "CONFENGE public pSEO export",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "archetypes",
            "markets",
            "agencies",
            "prices",
            "competition",
            "opportunities",
            "problem_service",
            "icp_methodology",
            "manifest",
        ],
        "properties": {
            "archetypes": {"type": "array", "items": {"$ref": "#/$defs/Archetype"}},
            "markets": {"type": "array", "items": {"$ref": "#/$defs/Market"}},
            "agencies": {"type": "array", "items": {"$ref": "#/$defs/Agency"}},
            "prices": {"type": "array", "items": {"$ref": "#/$defs/Price"}},
            "competition": {"type": "array", "items": {"$ref": "#/$defs/Competition"}},
            "opportunities": {"type": "array", "items": {"$ref": "#/$defs/Opportunity"}},
            "problem_service": {"type": "array", "items": {"$ref": "#/$defs/ProblemService"}},
            "icp_methodology": {"$ref": "#/$defs/ICPMethodology"},
            "manifest": {"type": "object"},
        },
        "$defs": defs,
    }


def _forbid_additional(node: Any) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        node.setdefault("additionalProperties", False)
    for v in node.values():
        if isinstance(v, dict):
            _forbid_additional(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _forbid_additional(item)
