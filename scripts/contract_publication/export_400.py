"""Stable export for the public-read-contract-analysis/1.0 consumer (#400)."""

from __future__ import annotations

from typing import Any

from scripts.contract_publication.models import Candidate
from scripts.contract_publication.schema import (
    CONSUMER_SCHEMA,
    CONTRACT_VERSION,
    PACK_SCHEMA,
    SCHEMA,
    SCORE_FORMULA_VERSION,
    hash_without_content_hash,
)
from scripts.public_read.export import assert_truth_plane_clean

PEER_STATUS = {
    "COMPARABLE": "PEER_VALID",
    "HOLD_FOR_DATA": "PEER_WEAK",
    "NOT_COMPARABLE": "NOT_COMPARABLE",
    "ABSENT": "ABSENT",
    "NO_VALID_PEER_GROUP": "NOT_COMPARABLE",
}


def _data_state(
    candidate: Candidate, pack: dict[str, Any], *, claimed_live: bool
) -> tuple[str, list[str], dict[str, Any]]:
    reasons: list[str] = []
    if claimed_live or candidate.catalog_mode == "official_live" or pack.get("catalog_mode") == "official_live":
        return "DATA_REJECT", ["fixture_as_live"], {"claimed_live": True}
    if candidate.candidate_state == "REJECT":
        return "DATA_REJECT", ["candidate_rejected_after_refresh"], {"candidate_state": "REJECT"}
    if candidate.freshness_status == "STALE":
        return "DATA_HOLD", ["stale_evidence"], {"freshness": candidate.freshness_status}
    if candidate.candidate_state == "HOLD_FOR_DATA":
        return (
            "DATA_HOLD",
            ["material_observation_after_pack"]
            if "missing_observed_at" not in candidate.reason_codes
            else ["stale_evidence"],
            {"candidate_state": "HOLD_FOR_DATA"},
        )
    peer = pack.get("peer_group") or {}
    if peer.get("status") in {"NOT_COMPARABLE", "ABSENT", "NO_VALID_PEER_GROUP"}:
        reasons.append("NOT_COMPARABLE")
    return (
        "DATA_READY",
        reasons,
        {"candidate_state": candidate.candidate_state, "data_ready_is_not_index_permission": True},
    )


def export_analysis(candidate: Candidate, pack: dict[str, Any], *, claimed_live: bool = False) -> dict[str, Any]:
    score = candidate.publication_value_score
    peer = pack.get("peer_group") or {}
    peer_status = PEER_STATUS.get(str(peer.get("status") or "ABSENT"), "ABSENT")
    data_state, reason_codes, facts = _data_state(candidate, pack, claimed_live=claimed_live)
    angles = candidate.suggested_analysis_angles
    angle = next(
        (
            item
            for item in angles
            if item
            in {
                "preco_bdi",
                "reajuste_reequilibrio",
                "aditivos_valor",
                "prazo",
                "comparavel",
                "exceptional",
            }
        ),
        None,
    )
    payload = {
        "schema": CONSUMER_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "analysis_candidate_id": candidate.analysis_candidate_id,
        "canonical_contract_ids": [candidate.canonical_contract_id] if candidate.canonical_contract_id else [],
        "candidate_score": {
            "value": score.value,
            "version": CONTRACT_VERSION,
            "schema": SCHEMA,
            "formula_version": SCORE_FORMULA_VERSION,
            "status": score.status,
        },
        "reason_summary": candidate.reason_codes[0] if candidate.reason_codes else None,
        "evidence_pack_version": pack.get("contract_version") or CONTRACT_VERSION,
        "evidence_pack_hash": pack.get("content_hash"),
        "peer_group": {
            "status": peer_status,
            "metrics": peer.get("metrics") or {},
            "version": peer.get("version"),
            "schema": peer.get("schema"),
            "content_hash": peer.get("content_hash"),
        },
        "timeline": pack.get("timeline") or [],
        "official_refs": pack.get("official_refs") or [],
        "calculations": pack.get("calculations") or [],
        "epistemic_classes": ["FACT", "CALCULATION", "INFERENCE", "UNKNOWN"],
        "as_of": pack.get("as_of") or candidate.as_of,
        "freshness": pack.get("freshness") or {},
        "coverage": pack.get("coverage") or {},
        "limitations": pack.get("limitations") or [],
        "safety_flags": {
            "data_ready_is_not_index_permission": True,
            "sensitivity_flags": list(candidate.sensitivity_flags),
            "peer_absent": peer_status in {"ABSENT", "NOT_COMPARABLE"},
        },
        "data_state": data_state,
        "data_state_facts": facts,
        "reason_codes": reason_codes,
        "catalog_mode": "fixture",
        "angle": angle,
        "score_formula_version": SCORE_FORMULA_VERSION,
        "evidence_pack_schema": pack.get("schema") or PACK_SCHEMA,
    }
    assert_truth_plane_clean(payload)
    if data_state not in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}:
        raise ValueError("forbidden_data_state")
    if "INDEX" in payload["reason_codes"] or payload["data_state"].startswith("PUBLISHABLE"):
        raise ValueError("forbidden_index_state")
    payload["content_hash"] = hash_without_content_hash(payload)
    return payload


def export_bundle(
    candidates: list[Candidate],
    packs: dict[str, dict[str, Any]],
    *,
    claimed_live: bool = False,
) -> dict[str, Any]:
    analyses = []
    for candidate in candidates:
        pack = packs.get(candidate.analysis_candidate_id)
        if pack is None:
            continue
        analyses.append(export_analysis(candidate, pack, claimed_live=claimed_live))
    document = {
        "schema": CONSUMER_SCHEMA,
        "catalog_mode": "fixture",
        "analyses": analyses,
        "count": len(analyses),
    }
    assert_truth_plane_clean(document)
    document["content_hash"] = hash_without_content_hash(document)
    return document
