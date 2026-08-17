"""Project validated observations into the #415 corpus shape. Engine is not modified."""

from __future__ import annotations

from collections.abc import Iterable

from scripts.official_contract_semantics.constants import (
    COMPARABLES_CANONICAL_SEMANTIC,
    COMPARABLES_CANONICAL_UNIT,
    EXPORT_COMPARABLES_VERSION,
    EXPORT_SEMANTIC_TO_COMPARABLES,
)
from scripts.official_contract_semantics.models import OfficialContractObservation
from scripts.official_contract_semantics.serialize import content_hash

DEFAULT_AS_OF = "2026-08-01"
DEFAULT_CASE = "official_semantics_export"


def _value_basis(item: OfficialContractObservation) -> str:
    if item.amendment_type in {"valor", "prazo_e_valor"} or item.amendment_value_delta is not None:
        return "atualizado"
    if item.value_amount is not None:
        return "original"
    return "unknown"


def _export_semantic(item: OfficialContractObservation) -> str:
    if not item.value_semantic:
        return "unknown"
    return EXPORT_SEMANTIC_TO_COMPARABLES.get(item.value_semantic, item.value_semantic)


def _export_unit(item: OfficialContractObservation) -> str | None:
    if item.unit is None:
        return None
    folded = item.unit.strip()
    if folded.upper() in {COMPARABLES_CANONICAL_UNIT, "GLOBAL", "VB", "VERBA"}:
        return COMPARABLES_CANONICAL_UNIT
    return folded


def observation_to_contract_record(item: OfficialContractObservation) -> dict[str, object]:
    contract_id = item.contract_identifier or item.observation_id
    unknown_value = item.value_amount is None or item.status in {"conflicted", "unknown"}
    return {
        "contract_id": contract_id,
        "objeto": item.object_text or "",
        "valor": None if unknown_value or item.value_amount is None else format(item.value_amount, "f"),
        "valor_is_unknown": unknown_value,
        "valor_semantic": "unknown" if item.status == "conflicted" else _export_semantic(item),
        "value_basis": "unknown" if item.status == "conflicted" else _value_basis(item),
        "unidade": None if item.status == "conflicted" else _export_unit(item),
        "quantidade": None if item.quantity is None else format(item.quantity, "f"),
        "uf": (item.extra or {}).get("uf"),
        "municipio": (item.extra or {}).get("municipio"),
        "regime": None if item.status == "conflicted" else item.execution_regime,
        "modalidade": None if item.status == "conflicted" else item.procurement_modality,
        "data_referencia": item.effective_at or item.period_start or item.observed_at,
        "revision": 1,
        "evidence_ref": item.source_document_id or item.official_url or item.observation_id,
        "source": item.source_system,
        "orgao_id": item.contracting_entity_identifier,
        "fornecedor_id": item.supplier_identifier,
        "extra_observation_id": item.observation_id,
        "extra_value_semantic_source": item.value_semantic,
        "extra_status": item.status,
        "extra_conflict_group_id": item.conflict_group_id,
        "extra_export_version": EXPORT_COMPARABLES_VERSION,
    }


def eligible_for_comparables_export(item: OfficialContractObservation) -> bool:
    if item.status == "superseded_by_official_evidence":
        return False
    return True


def export_comparables_corpus(
    observations: Iterable[OfficialContractObservation],
    *,
    as_of: str = DEFAULT_AS_OF,
    case_id: str = DEFAULT_CASE,
    focal_id: str | None = None,
    catalog_mode: str = "fixture",
) -> dict[str, object]:
    live = [item for item in observations if eligible_for_comparables_export(item)]
    records = [observation_to_contract_record(item) for item in live]
    records.sort(key=lambda row: str(row["contract_id"]))
    chosen_focal = focal_id
    if chosen_focal is None and records:
        chosen_focal = str(records[0]["contract_id"])
    document = {
        "as_of": as_of,
        "source": "fixture",
        "producer": "official_contract_semantics",
        "catalog_mode": catalog_mode if catalog_mode != "official_live" else "fixture",
        "question_id": "paving_nominal_total_value_position",
        "export_version": EXPORT_COMPARABLES_VERSION,
        "does_not_authorize_publication": True,
        "projection_notes": {
            "valor_global_or_contratado_maps_to": COMPARABLES_CANONICAL_SEMANTIC,
            "other_semantics_pass_through": True,
            "conflict_and_unknown_remain_unknown": True,
        },
        "cases": {
            case_id: {
                "focal_id": chosen_focal,
                "contracts": records,
            }
        },
    }
    document["content_hash"] = content_hash({key: value for key, value in document.items() if key != "content_hash"})
    return document
