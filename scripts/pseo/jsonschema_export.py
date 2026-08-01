"""Generate real JSON Schema (draft 2020-12) for public pSEO artifacts."""

from __future__ import annotations

from typing import Any

from scripts.pseo.models import (
    Agency,
    Archetype,
    BudgetSignal,
    ClaimEvidence,
    ClassifierMetadata,
    Competition,
    DocumentSignal,
    Freshness,
    ICPMethodology,
    InternalSignatureAggregates,
    Market,
    MethodologyMetadata,
    Modality,
    OfficialReference,
    Opportunity,
    Price,
    PrivacyMetadata,
    ProblemService,
    StatusBreakdown,
    ValueBand,
)


def build_json_schema() -> dict[str, Any]:
    """Composite schema with $defs for each artifact type + nested models."""
    defs: dict[str, Any] = {
        "Archetype": Archetype.model_json_schema(),
        "Market": Market.model_json_schema(),
        "Agency": Agency.model_json_schema(),
        "Price": Price.model_json_schema(),
        "Competition": Competition.model_json_schema(),
        "Opportunity": Opportunity.model_json_schema(),
        "ProblemService": ProblemService.model_json_schema(),
        "ICPMethodology": ICPMethodology.model_json_schema(),
        # Nested public models (B2)
        "ValueBand": ValueBand.model_json_schema(),
        "PrivacyMetadata": PrivacyMetadata.model_json_schema(),
        "Modality": Modality.model_json_schema(),
        "StatusBreakdown": StatusBreakdown.model_json_schema(),
        "Freshness": Freshness.model_json_schema(),
        "OfficialReference": OfficialReference.model_json_schema(),
        "ClaimEvidence": ClaimEvidence.model_json_schema(),
        "DocumentSignal": DocumentSignal.model_json_schema(),
        "BudgetSignal": BudgetSignal.model_json_schema(),
        "ClassifierMetadata": ClassifierMetadata.model_json_schema(),
        "InternalSignatureAggregates": InternalSignatureAggregates.model_json_schema(),
        "MethodologyMetadata": MethodologyMetadata.model_json_schema(),
    }
    for name, sch in list(defs.items()):
        _forbid_additional(sch)
        _reject_empty_and_free_objects(sch, path=name)
        defs[name] = sch

    root: dict[str, Any] = {
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
            # Manifest remains a descriptor object; closed to free form keys at this layer.
            "manifest": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string"},
                    "dataset_hash": {"type": "string"},
                    "export_entrypoint": {"type": "string"},
                    "snapshot_status": {"type": "string"},
                    "publish_status": {"type": "string"},
                    "indexable": {"type": "boolean"},
                },
            },
        },
        "$defs": defs,
    }
    _forbid_additional(root)
    return root


def _forbid_additional(node: Any) -> None:
    """Force additionalProperties:false on every object schema node."""
    if not isinstance(node, dict):
        return
    is_object = node.get("type") == "object" or "properties" in node
    # Typed maps (additionalProperties: {type: ...}) are rewritten to closed objects
    # when they have properties; pure free maps without properties are left as
    # closed empty objects (callers must use nested models / lists instead).
    if is_object:
        ap = node.get("additionalProperties", None)
        if ap is True or ap is None:
            node["additionalProperties"] = False
        elif isinstance(ap, dict) and not node.get("properties"):
            # Free-form map → reject as free object; force closed
            node["additionalProperties"] = False
        elif isinstance(ap, dict):
            # Has properties AND typed additionalProperties — still force closed
            node["additionalProperties"] = False
            _forbid_additional(ap)
    for key, v in list(node.items()):
        if key in {"$defs", "definitions"} and isinstance(v, dict):
            for sub in v.values():
                _forbid_additional(sub)
            continue
        if isinstance(v, dict):
            _forbid_additional(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _forbid_additional(item)


def _reject_empty_and_free_objects(node: Any, *, path: str = "") -> None:
    """Raise if schema still contains empty {} or free object types.

    Used at build time as a defensive check; tests walk the result as well.
    """
    if not isinstance(node, dict):
        return
    # Empty schema {}
    if node == {}:
        raise ValueError(f"empty schema node at {path}")
    if node.get("type") == "object":
        if "additionalProperties" not in node and "$ref" not in node:
            raise ValueError(f"object without additionalProperties at {path}")
        if node.get("additionalProperties") is True:
            raise ValueError(f"free object (additionalProperties:true) at {path}")
        props = node.get("properties")
        if props is None and node.get("additionalProperties") is not False and "$ref" not in node:
            # pure free object
            if not node.get("$ref"):
                raise ValueError(f"free object type at {path}")
    for k, v in node.items():
        child = f"{path}.{k}" if path else k
        if isinstance(v, dict):
            _reject_empty_and_free_objects(v, path=child)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    _reject_empty_and_free_objects(item, path=f"{child}[{i}]")
