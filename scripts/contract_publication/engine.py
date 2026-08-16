"""Deterministic ranking of publication candidates. No I/O."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from scripts.contract_publication.detectors import CohortIndex, build_cohort, observation_freshness, run_detectors
from scripts.contract_publication.facts import (
    catalog_mode_of,
    material_fingerprint,
    parse_optional_datetime,
    project_record,
)
from scripts.contract_publication.invalidate import invalidation_report
from scripts.contract_publication.models import Candidate
from scripts.contract_publication.pack import build_evidence_pack
from scripts.contract_publication.schema import (
    CANDIDATE_STATES,
    COMPONENT_NAMES,
    CONTRACT_VERSION,
    SCHEMA,
    SCORE_FORMULA_VERSION,
    canonical_dumps,
    content_hash,
    declared_weights,
    hash_without_content_hash,
    load_candidate_contract,
    load_policy,
    producer_sha,
)
from scripts.contract_publication.score import aggregate_score, component_by_name, score_components
from scripts.contract_publication.state import decide_state, missing_detector_fields, sensitivity_flags
from scripts.public_read.export import assert_truth_plane_clean

_STATE_RANK = {"EDITORIAL_REVIEW": 0, "HOLD_FOR_DATA": 1, "REJECT": 2}


def _in_window(record: dict[str, Any], *, window_start: str | None, window_end: str | None) -> bool:
    if not window_start and not window_end:
        return True
    stamps = [
        record.get("data_assinatura"),
        record.get("signed_at"),
        record.get("data_inicio"),
        record.get("start_at"),
        record.get("observed_at"),
    ]
    known = [item for item in (parse_optional_datetime(stamp) for stamp in stamps) if item is not None]
    if not known:
        return True
    moment = known[0]
    if window_start:
        start = parse_optional_datetime(window_start)
        if start and moment < start:
            return False
    if window_end:
        end = parse_optional_datetime(window_end)
        if end and moment > end:
            return False
    return True


def evaluate_record(
    record: dict[str, Any],
    *,
    as_of: str,
    cohort: CohortIndex,
    seen_ids: set[str],
    catalog_mode: str,
    policy: dict[str, Any] | None,
) -> Candidate:
    mode = catalog_mode_of(record, catalog_mode)
    projected = project_record(record, as_of=as_of, catalog_mode=mode)
    duplicate = bool(projected.canonical_contract_id and projected.canonical_contract_id in seen_ids)
    detectors = run_detectors(projected, cohort, as_of=as_of)
    age_hours, freshness_status = observation_freshness(projected, as_of=as_of)
    components = score_components(projected, detectors, freshness_hours=age_hours, policy=policy)
    aggregate = aggregate_score(components, policy=policy)
    state, state_reasons = decide_state(
        projected,
        detectors,
        components,
        aggregate,
        freshness_status=freshness_status,
        duplicate=duplicate,
        policy=policy,
    )
    flags = sensitivity_flags(projected, detectors)
    missing = missing_detector_fields(detectors)
    unknown_reasons = tuple(item.reason_code for item in components if item.status == "UNKNOWN" and item.reason_code)
    reason_codes = tuple(dict.fromkeys((*state_reasons, *unknown_reasons, *projected.facts.reason_codes)))
    evidence = tuple(dict.fromkeys(ref for item in (*components, *detectors) for ref in item.evidence_refs))
    event_ids = tuple(dict.fromkeys(event_id for item in detectors for event_id in item.event_ids))
    angles = tuple(dict.fromkeys(angle for item in detectors if item.fired for angle in item.analysis_angles))
    peers = tuple(dict.fromkeys(dim for item in detectors for dim in item.peer_dimensions))
    identity = projected.canonical_contract_id or projected.facts.source_record_id or "unknown"
    return Candidate(
        schema=SCHEMA,
        contract_version=CONTRACT_VERSION,
        score_formula_version=SCORE_FORMULA_VERSION,
        analysis_candidate_id=identity,
        canonical_contract_id=projected.canonical_contract_id,
        source_id=projected.facts.source_id,
        source_record_id=projected.facts.source_record_id,
        as_of=as_of,
        observed_at=projected.facts.observed_at or record.get("observed_at"),
        freshness_hours=round(age_hours, 6) if age_hours is not None else None,
        freshness_status=freshness_status,  # type: ignore[arg-type]
        candidate_state=state,
        publication_value_score=aggregate,
        components=components,
        detectors=detectors,
        reason_codes=reason_codes,
        missing=missing,
        evidence_refs=evidence,
        event_ids=event_ids,
        suggested_analysis_angles=angles,
        suggested_peer_dimensions=peers,
        sensitivity_flags=flags,
        material_fingerprint=material_fingerprint(record),
        catalog_mode=mode if mode != "official_live" else "fixture",
        authorizes_publication=False,
        authorizes_indexation=False,
    )


def rank_candidates(
    records: Iterable[dict[str, Any]],
    *,
    as_of: str,
    window_start: str | None = None,
    window_end: str | None = None,
    catalog_mode: str = "fixture",
    policy: dict[str, Any] | None = None,
) -> list[Candidate]:
    material = [record for record in records if _in_window(record, window_start=window_start, window_end=window_end)]
    cohort = build_cohort(material)
    seen: set[str] = set()
    ranked: list[Candidate] = []
    for record in material:
        candidate = evaluate_record(
            record,
            as_of=as_of,
            cohort=cohort,
            seen_ids=seen,
            catalog_mode=catalog_mode,
            policy=policy,
        )
        if candidate.canonical_contract_id:
            seen.add(candidate.canonical_contract_id)
        ranked.append(candidate)
    ranked.sort(
        key=lambda item: (
            _STATE_RANK[item.candidate_state],
            -(item.publication_value_score.value or -1.0),
            -(component_by_name(item.components, "insight_or_anomaly_strength").value or 0.0),
            item.canonical_contract_id or "",
        )
    )
    return ranked


def shortlist(candidates: list[Candidate], *, limit: int = 10) -> list[Candidate]:
    review = [item for item in candidates if item.candidate_state == "EDITORIAL_REVIEW"]
    return review[: max(0, limit)]


def _record_identity(record: dict[str, Any]) -> str | None:
    return (
        record.get("canonical_contract_id")
        or record.get("contrato_id")
        or record.get("source_record_id")
        or record.get("numero_controle_pncp")
    )


def build_packs(
    records: list[dict[str, Any]],
    candidates: list[Candidate],
    *,
    as_of: str,
    catalog_mode: str,
    policy: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    del policy
    by_record_id: dict[str, dict[str, Any]] = {}
    leftover = list(records)
    for record in records:
        identity = _record_identity(record)
        if identity:
            by_record_id[str(identity)] = record
    packs: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        record = None
        if candidate.canonical_contract_id and candidate.canonical_contract_id in by_record_id:
            record = by_record_id[candidate.canonical_contract_id]
        elif candidate.source_record_id and candidate.source_record_id in by_record_id:
            record = by_record_id[candidate.source_record_id]
        elif leftover:
            record = leftover.pop(0)
        if record is None:
            continue
        projected = project_record(record, as_of=as_of, catalog_mode=catalog_mode_of(record, catalog_mode))
        packs[candidate.analysis_candidate_id] = build_evidence_pack(projected, candidate)
    return packs


def input_payload_hash(
    records: list[dict[str, Any]],
    *,
    as_of: str,
    policy: dict[str, Any],
    window_start: str | None,
    window_end: str | None,
) -> str:
    return content_hash(
        {
            "as_of": as_of,
            "window_start": window_start,
            "window_end": window_end,
            "schema": SCHEMA,
            "score_formula_version": SCORE_FORMULA_VERSION,
            "weights": declared_weights(policy),
            "records": records,
        }
    )


def build_run_document(
    candidates: list[Candidate],
    packs: dict[str, dict[str, Any]],
    *,
    as_of: str,
    input_hash: str,
    catalog_mode: str,
    policy: dict[str, Any],
    snapshot_id: str | None,
    window_start: str | None = None,
    window_end: str | None = None,
    previous_candidates: list[dict[str, Any]] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    contract = load_candidate_contract()
    by_state = {state: 0 for state in CANDIDATE_STATES}
    for item in candidates:
        by_state[item.candidate_state] += 1
    selected = shortlist(candidates)
    document = {
        "schema": SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "score_formula_version": SCORE_FORMULA_VERSION,
        "producer_sha": producer_sha(),
        "policy_version": SCORE_FORMULA_VERSION,
        "weights": declared_weights(policy),
        "component_names": list(COMPONENT_NAMES),
        "unknown_policy": policy.get("unknown_policy") or "UNKNOWN remains UNKNOWN",
        "as_of": as_of,
        "snapshot_id": snapshot_id,
        "window": {"start": window_start, "end": window_end},
        "input_hash": input_hash,
        "catalog_mode": catalog_mode,
        "status": status or catalog_mode,
        "does_not_authorize": contract["does_not_authorize"],
        "candidate_states": list(CANDIDATE_STATES),
        "coverage": {
            "candidate_count": len(candidates),
            "by_state": by_state,
            "review_count": by_state["EDITORIAL_REVIEW"],
            "shortlist_count": len(selected),
        },
        "shortlist_ids": [item.analysis_candidate_id for item in selected],
        "candidates": [item.as_dict() for item in candidates],
        "packs": {
            key: {"schema": pack.get("schema"), "content_hash": pack.get("content_hash")} for key, pack in packs.items()
        },
    }
    if previous_candidates is not None:
        current_meta = [
            {
                "analysis_candidate_id": item.analysis_candidate_id,
                "material_fingerprint": item.material_fingerprint,
                "evidence_pack_hash": (packs.get(item.analysis_candidate_id) or {}).get("content_hash"),
            }
            for item in candidates
        ]
        document["invalidation"] = invalidation_report(previous_candidates, current_meta)
    assert_truth_plane_clean(document)
    document["content_hash"] = hash_without_content_hash(document)
    return document


def load_snapshot(path_or_payload: Any) -> tuple[str, list[dict[str, Any]], str, str | None]:
    import json
    from pathlib import Path

    if isinstance(path_or_payload, dict):
        payload = path_or_payload
    else:
        raw = Path(path_or_payload).read_text(encoding="utf-8")
        if str(path_or_payload).endswith(".jsonl"):
            records = [json.loads(line) for line in raw.splitlines() if line.strip()]
            as_of = records[0].get("as_of") if records else None
            if not as_of:
                raise ValueError("jsonl_missing_as_of")
            return str(as_of), records, "fixture", None
        payload = json.loads(raw)
    if isinstance(payload, list):
        raise ValueError("snapshot_must_be_object")
    as_of = payload.get("as_of")
    records = payload.get("records") or payload.get("contracts") or []
    if not as_of:
        raise ValueError("snapshot_missing_as_of")
    mode = payload.get("catalog_mode") or "fixture"
    if mode == "official_live":
        mode = "fixture"
        for record in records:
            record = record
    snapshot_id = payload.get("snapshot_id") or payload.get("id")
    return str(as_of), list(records), str(mode), snapshot_id


def load_policy_file(path: Any | None) -> dict[str, Any]:
    from pathlib import Path

    if path is None:
        return load_policy()
    return load_policy(Path(path))


def dumps(payload: Any) -> str:
    return canonical_dumps(payload)
