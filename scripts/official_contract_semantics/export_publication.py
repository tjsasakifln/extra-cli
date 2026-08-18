"""Project observations into a #414 snapshot plus coverage/HOLD matrix. No promotion."""

from __future__ import annotations

from collections.abc import Iterable

from scripts.official_contract_semantics.constants import (
    EXPORT_PUBLICATION_VERSION,
    FORBIDDEN_PUBLIC_STATES,
    SCHEMA_VERSION,
)
from scripts.official_contract_semantics.coverage import contract_hold_report, coverage_matrix
from scripts.official_contract_semantics.models import OfficialContractObservation
from scripts.official_contract_semantics.serialize import content_hash

DEFAULT_AS_OF = "2026-08-15T00:00:00+00:00"


def observation_to_snapshot_record(item: OfficialContractObservation) -> dict[str, object]:
    contract_id = item.contract_identifier or item.observation_id
    documents = []
    if item.source_document_id or item.source_document_sha256:
        documents.append(
            {
                "id": item.source_document_id,
                "sha256": item.source_document_sha256,
                "url": item.official_url,
                "type": item.source_kind,
            }
        )
    record: dict[str, object] = {
        "canonical_contract_id": contract_id,
        "source": item.source_system,
        "source_id": item.source_document_id or contract_id,
        "numero_controle_pncp": contract_id,
        "contrato_id": contract_id,
        "process_id": item.process_identifier,
        "objeto_contrato": item.object_text,
        "orgao_cnpj": item.contracting_entity_identifier,
        "fornecedor_cnpj": item.supplier_identifier,
        "valor_total": None
        if item.value_amount is None or item.status == "conflicted"
        else format(item.value_amount, "f"),
        "data_assinatura": item.effective_at,
        "data_inicio": item.period_start,
        "data_fim": item.period_end,
        "observed_at": item.observed_at,
        "uf": (item.extra or {}).get("uf"),
        "municipio": (item.extra or {}).get("municipio"),
        "evidence_ref": item.source_document_id or item.official_url or item.observation_id,
        "source_urls": [item.official_url] if item.official_url else [],
        "documents": documents,
        "observation_id": item.observation_id,
        "observation_status": item.status,
        "epistemic_class": item.epistemic_class,
        "field_epistemics": dict(item.field_epistemics or {}),
        "value_semantic": item.value_semantic,
        "unit": item.unit,
        "quantity": None if item.quantity is None else format(item.quantity, "f"),
        "execution_regime": item.execution_regime,
        "procurement_modality": item.procurement_modality,
    }
    if item.amendment_value_delta is not None:
        record["value_changes"] = [
            {
                "id": f"obs-value-{item.observation_id[:12]}",
                "delta": format(item.amendment_value_delta, "f"),
                "ref": item.source_document_id,
            }
        ]
    if item.amendment_term_delta is not None:
        record["term_changes"] = [
            {
                "id": f"obs-term-{item.observation_id[:12]}",
                "delta": item.amendment_term_delta,
                "ref": item.source_document_id,
            }
        ]
    if item.source_kind == "amendment":
        record["amendments"] = [
            {"id": item.source_document_id, "ref": item.source_document_id, "type": item.amendment_type}
        ]
    return record


def export_publication_evidence(
    observations: Iterable[OfficialContractObservation],
    *,
    as_of: str = DEFAULT_AS_OF,
    catalog_mode: str = "fixture",
) -> dict[str, object]:
    items = [item for item in observations if item.status != "superseded_by_official_evidence"]
    records = [observation_to_snapshot_record(item) for item in items]
    records.sort(key=lambda row: str(row.get("canonical_contract_id")))
    holds = contract_hold_report(observations)
    coverage = coverage_matrix(observations)
    hold_count = sum(1 for row in holds if row["hold"])
    eligible_count = sum(1 for row in holds if row["technically_eligible_for_engine"])
    snapshot = {
        "schema": "contract-publication-snapshot/1.0",
        "catalog_mode": catalog_mode if catalog_mode != "official_live" else "fixture",
        "snapshot_id": f"official-semantics-{content_hash(records)[:12]}",
        "as_of": as_of,
        "source_kind": "official_contract_semantics",
        "export_version": EXPORT_PUBLICATION_VERSION,
        "observation_schema": SCHEMA_VERSION,
        "authorizes_publication": False,
        "authorizes_indexation": False,
        "does_not_emit": sorted(FORBIDDEN_PUBLIC_STATES),
        "records": records,
        "coverage": coverage,
        "hold_report": holds,
        "hold_for_data_count": hold_count,
        "technically_eligible_for_engine_count": eligible_count,
        "reason_codes": sorted({code for row in holds for code in row["reason_codes"]}),
    }
    if any(state in snapshot for state in FORBIDDEN_PUBLIC_STATES):
        raise ValueError("forbidden_public_state_emitted")
    snapshot["content_hash"] = content_hash({key: value for key, value in snapshot.items() if key != "content_hash"})
    return snapshot
