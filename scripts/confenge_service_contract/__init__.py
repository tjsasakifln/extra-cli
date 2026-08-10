"""confenge.service.v1 — canonical service ontology (extra-cli ↔ Warmbly)."""

from __future__ import annotations

from scripts.confenge_service_contract.mapping import (
    SCHEMA_ID,
    canonical_to_extra_cli,
    export_contract_json,
    load_service_contract,
    map_to_canonical,
    map_to_warmbly,
    resolve_service,
)

__all__ = [
    "SCHEMA_ID",
    "canonical_to_extra_cli",
    "export_contract_json",
    "load_service_contract",
    "map_to_canonical",
    "map_to_warmbly",
    "resolve_service",
]
