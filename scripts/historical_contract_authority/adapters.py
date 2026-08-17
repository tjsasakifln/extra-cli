"""Read-only adapters over #414, #415 and public-read-contract-analysis/1.0."""

from __future__ import annotations

from typing import Any

from scripts.contract_comparables.engine import build_peer_group
from scripts.contract_comparables.models import PeerRequest
from scripts.contract_publication.engine import rank_candidates
from scripts.historical_contract_authority.models import Comparability
from scripts.historical_contract_authority.schema import CONSUMER_SCHEMA, FORBIDDEN_PUBLIC_STATES, STATE_TO_DATA
from scripts.public_read_consumers.contract_analysis import PAYLOAD_FIELDS
from scripts.public_read_consumers.contract_analysis import SCHEMA as PUBLIC_READ_SCHEMA


def case_to_publication_record(case: dict[str, Any]) -> dict[str, Any]:
    identity = case.get("identity") or {}
    values = case.get("values") or {}
    dates = case.get("dates") or {}
    documents = case.get("documents") or []
    return {
        "canonical_contract_id": identity.get("contract_id"),
        "contrato_id": identity.get("contract_id"),
        "numero_controle_pncp": identity.get("contract_id"),
        "source": case.get("source") or "pncp",
        "source_id": identity.get("contract_id"),
        "objeto_contrato": identity.get("objeto"),
        "orgao_cnpj": identity.get("orgao_cnpj"),
        "orgao_nome": identity.get("orgao_nome"),
        "fornecedor_cnpj": identity.get("fornecedor_cnpj"),
        "fornecedor_nome": identity.get("fornecedor_nome"),
        "valor_total": values.get("valor_atual") or values.get("valor_original"),
        "data_assinatura": dates.get("assinatura"),
        "data_inicio": dates.get("inicio"),
        "data_fim": dates.get("fim"),
        "observed_at": dates.get("observed_at") or dates.get("reference"),
        "uf": identity.get("uf") or "SC",
        "municipio": identity.get("municipio"),
        "documents": documents,
        "amendments": case.get("amendments") or [],
        "value_changes": case.get("value_changes") or [],
        "term_changes": case.get("term_changes") or [],
        "scope_changes": case.get("scope_changes") or [],
        "evidence_ref": (documents[0] or {}).get("url") if documents else None,
        "source_urls": [item.get("url") for item in documents if item.get("url")],
        "catalog_mode": "fixture",
        "identity_swap": identity.get("identity_swap"),
        "conflicting_value": values.get("conflict_hidden"),
        "conflicting_date": (dates.get("conflicts") or [None])[0],
    }


def rank_via_414(cases: list[dict[str, Any]], *, as_of: str) -> list[Any]:
    records = [case_to_publication_record(case) for case in cases]
    return rank_candidates(records, as_of=as_of, catalog_mode="fixture")


def _peer_mapping(
    identity: dict[str, Any], values: dict[str, Any], dates: dict[str, Any], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = {
        "contract_id": identity.get("contract_id"),
        "objeto": identity.get("objeto") or "",
        "valor": values.get("valor_atual") or values.get("valor_original"),
        "valor_is_unknown": values.get("valor_atual") in {None, "", "UNKNOWN"},
        "valor_semantic": values.get("valor_semantic") or "unknown",
        "value_basis": values.get("value_basis") or "unknown",
        "unidade": values.get("unidade"),
        "quantidade": values.get("quantidade"),
        "uf": identity.get("uf") or "SC",
        "municipio": identity.get("municipio"),
        "regime": values.get("regime"),
        "modalidade": values.get("modalidade"),
        "porte": values.get("porte"),
        "data_referencia": dates.get("reference"),
        "year": (dates.get("reference") or "0000")[:4],
        "evidence_ref": extra.get("evidence_ref") if extra else None,
        "source": "fixture",
        "orgao_id": identity.get("orgao_cnpj"),
        "orgao_nome": identity.get("orgao_nome"),
        "fornecedor_id": identity.get("fornecedor_cnpj"),
        "fornecedor_nome": identity.get("fornecedor_nome"),
    }
    if extra:
        payload.update(
            {key: value for key, value in extra.items() if key != "evidence_ref" or extra.get("evidence_ref")}
        )
    return payload


def compare_via_415(case: dict[str, Any], *, as_of: str) -> Comparability:
    identity = case.get("identity") or {}
    values = case.get("values") or {}
    dates = case.get("dates") or {}
    peers = case.get("comparable_peers") or []
    mappings = [_peer_mapping(identity, values, dates, {"evidence_ref": "focal"})]
    for peer in peers:
        mappings.append(
            _peer_mapping(
                peer.get("identity") or peer,
                peer.get("values") or peer,
                peer.get("dates") or {"reference": peer.get("data_referencia") or dates.get("reference")},
                {"evidence_ref": peer.get("evidence_ref") or peer.get("contract_id")},
            )
        )
    request = PeerRequest(
        focal_contract_id=str(identity.get("contract_id") or "unknown"),
        as_of=as_of,
        catalog_mode="fixture",
        source="fixture",
        consumer_id="public-read-contract-analysis/#400",
        live_semantic_columns_present=bool(
            values.get("unidade") and values.get("regime") and values.get("valor_semantic") not in {None, "", "unknown"}
        ),
    )
    result, document = build_peer_group(mappings, request)
    status = result.status if result.status in {"COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE"} else "NOT_COMPARABLE"
    return Comparability(
        status=status,  # type: ignore[arg-type]
        reason_codes=tuple(result.reason_codes),
        engine="scripts.contract_comparables.build_peer_group",
        schema=str(document.get("schema") or "comparable-contracts/1.0"),
        usable_n=result.usable_n,
        outlier_flag=bool(result.metrics.outlier_flag) if result.metrics else False,
        limitations=tuple(result.limitations),
        content_hash=document.get("content_hash"),
    )


def to_public_read(dossier: dict[str, Any]) -> dict[str, Any]:
    state = str(dossier.get("state") or "REJECT")
    data_state = STATE_TO_DATA.get(state, "DATA_REJECT")
    if data_state not in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}:
        raise ValueError("forbidden_data_state")
    identity = dossier.get("identity") or {}
    comparability = dossier.get("comparability") or {}
    peer_map = {"COMPARABLE": "PEER_VALID", "HOLD_FOR_DATA": "PEER_WEAK", "NOT_COMPARABLE": "NOT_COMPARABLE"}
    peer_status = peer_map.get(str(comparability.get("status") or "NOT_COMPARABLE"), "NOT_COMPARABLE")
    payload = {
        "schema": PUBLIC_READ_SCHEMA,
        "contract_version": "v1.0.0",
        "analysis_candidate_id": dossier.get("dossier_id"),
        "canonical_contract_ids": [identity.get("contract_id")] if identity.get("contract_id") else [],
        "candidate_score": {
            "value": (dossier.get("score") or {}).get("score"),
            "version": "v1.0.0",
            "schema": "dossier-authority-score/1.0",
            "formula_version": "dossier-authority-score/1.0",
            "status": "KNOWN",
        },
        "reason_summary": (dossier.get("reason_codes") or ["unspecified"])[0],
        "evidence_pack_version": "v1.0.0",
        "evidence_pack_hash": dossier.get("content_hash"),
        "peer_group": {
            "status": peer_status,
            "metrics": {},
            "version": "v1.0.0",
            "schema": comparability.get("schema"),
            "content_hash": comparability.get("content_hash"),
        },
        "timeline": dossier.get("chronology") or [],
        "official_refs": [
            {"url": item.get("url"), "locator": item.get("locator"), "sha256": item.get("binary_sha256")}
            for item in dossier.get("documents") or []
        ],
        "calculations": dossier.get("calculations") or [],
        "epistemic_classes": ["FACT", "CALCULATION", "INFERENCE", "UNKNOWN"],
        "as_of": dossier.get("as_of"),
        "freshness": dossier.get("freshness") or {},
        "coverage": {
            "claim_count": len(dossier.get("claims") or []),
            "document_count": len(dossier.get("documents") or []),
        },
        "limitations": dossier.get("limitations") or [],
        "safety_flags": {
            "data_ready_is_not_index_permission": True,
            "no_index_authorization": True,
            "no_publication_authorization": True,
        },
        "data_state": data_state,
        "data_state_facts": {"dossier_state": state, "data_ready_is_not_index_permission": True},
        "reason_codes": list(dossier.get("reason_codes") or []),
        "catalog_mode": dossier.get("catalog_mode") or "fixture",
    }
    missing = [field for field in PAYLOAD_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"public_read_missing:{missing}")
    blob = str(payload)
    for token in FORBIDDEN_PUBLIC_STATES:
        if token in blob:
            raise ValueError(f"forbidden_public_state:{token}")
    if payload["schema"] != CONSUMER_SCHEMA:
        raise ValueError("consumer_schema_mismatch")
    return payload
