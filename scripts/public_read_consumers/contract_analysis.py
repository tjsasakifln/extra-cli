"""Adapter for public-read-contract-analysis/1.0 (web-cfg PR #85).

Does not rescore #414 or recompute #415. Fan-in of labeled producer documents
into the already-consumed FACTUAL pack. Never emits INDEX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.public_read_consumers.gates import (
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    REASON_FIXTURE_AS_LIVE,
    freshness_block,
    is_stale,
    refuse_fixture_as_live,
)
from scripts.public_read_consumers.hashutil import assert_public_clean, attach_hash

SCHEMA = "public-read-contract-analysis/1.0"
SCORE_SCHEMA = "contract-publication-candidate/1.0"
EVIDENCE_SCHEMA = "contract-evidence-pack/1.0"
EVIDENCE_ALIASES = frozenset({EVIDENCE_SCHEMA, "contract_evidence_pack/1.0"})
PEER_SCHEMA = "comparable-contracts/1.0"
PEER_ALIASES = frozenset({PEER_SCHEMA, "public-read-comparable-contracts/1.0"})
EXPECTED_VERSIONS = frozenset({"1.0", "v1.0.0", "1.0.0"})
SCORE_FORMULA = "publication-value-score/1.0"

REASON_PRODUCER_MISSING = "producer_missing"
REASON_STALE_EVIDENCE = "stale_evidence"
REASON_SCORE_VERSION = "score_version_mismatch"
REASON_SOURCE_CONFLICT = "source_conflict"
REASON_CONTRACT_UPDATED = "contract_updated_after_evidence_pack"
REASON_MATERIAL_OBSERVATION = "material_observation_after_pack"
REASON_CANDIDATE_REJECTED = "candidate_rejected_after_refresh"
REASON_NOT_COMPARABLE = "NOT_COMPARABLE"

HOLD_CODES = frozenset({REASON_STALE_EVIDENCE, REASON_MATERIAL_OBSERVATION})
REJECT_CODES = frozenset(
    {
        REASON_PRODUCER_MISSING,
        REASON_SCORE_VERSION,
        REASON_SOURCE_CONFLICT,
        REASON_CONTRACT_UPDATED,
        REASON_CANDIDATE_REJECTED,
        REASON_FIXTURE_AS_LIVE,
    }
)
MATERIAL_CODES = (
    REASON_PRODUCER_MISSING,
    REASON_STALE_EVIDENCE,
    REASON_SCORE_VERSION,
    REASON_SOURCE_CONFLICT,
    REASON_CONTRACT_UPDATED,
    REASON_MATERIAL_OBSERVATION,
    REASON_CANDIDATE_REJECTED,
    REASON_FIXTURE_AS_LIVE,
    REASON_NOT_COMPARABLE,
)
INFORMATIONAL = frozenset({REASON_NOT_COMPARABLE})

PEER_MAP = {
    "COMPARABLE": "PEER_VALID",
    "HOLD_FOR_DATA": "PEER_WEAK",
    "NOT_COMPARABLE": "NOT_COMPARABLE",
    "PEER_VALID": "PEER_VALID",
    "PEER_WEAK": "PEER_WEAK",
    "NO_VALID_PEER_GROUP": "NOT_COMPARABLE",
    "ABSENT": "ABSENT",
}
PEER_STATUSES = frozenset({"PEER_VALID", "PEER_WEAK", "NOT_COMPARABLE", "ABSENT"})
EPISTEMIC = ("FACT", "CALCULATION", "INFERENCE", "UNKNOWN")
ANGLES = (
    "preco_bdi",
    "reajuste_reequilibrio",
    "aditivos_valor",
    "prazo",
    "comparavel",
    "exceptional",
)
CANARY_MIN = 5
CANARY_MAX = 10

PAYLOAD_FIELDS = (
    "analysis_candidate_id",
    "canonical_contract_ids",
    "candidate_score",
    "reason_summary",
    "evidence_pack_version",
    "evidence_pack_hash",
    "peer_group",
    "timeline",
    "official_refs",
    "calculations",
    "epistemic_classes",
    "as_of",
    "freshness",
    "coverage",
    "limitations",
    "safety_flags",
    "data_state",
    "data_state_facts",
    "reason_codes",
)


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == () or value == {}


def _text(value: Any) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip()
    return text or None


def _texts(value: Any) -> tuple[str, ...]:
    if _blank(value):
        return ()
    if isinstance(value, str):
        found = _text(value)
        return (found,) if found else ()
    return tuple(item for item in (_text(entry) for entry in value) if item)


def _tuple(value: Any) -> tuple[Any, ...]:
    if _blank(value):
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _float(value: Any) -> float | None:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _canonical_ids(raw: dict[str, Any]) -> tuple[str, ...]:
    ids = _texts(raw.get("canonical_contract_ids") or raw.get("canonical_contract_id"))
    if ids:
        return ids
    identity = raw.get("identity")
    if isinstance(identity, dict):
        inner = identity.get("value") if "value" in identity else identity
        if isinstance(inner, dict):
            return _texts(inner.get("canonical_contract_ids") or inner.get("id"))
        return _texts(inner)
    return ()


@dataclass(frozen=True)
class ScoreView:
    analysis_candidate_id: str | None
    canonical_contract_ids: tuple[str, ...]
    value: float | None
    version: str | None
    schema: str | None
    formula_version: str | None
    reason_summary: str | None
    angle: str | None
    status: str | None
    after_refresh: bool
    present: bool
    usable: bool


@dataclass(frozen=True)
class EvidenceView:
    version: str | None
    schema: str | None
    content_hash: str | None
    source_as_of: str | None
    canonical_contract_ids: tuple[str, ...]
    timeline: tuple[Any, ...]
    calculations: tuple[Any, ...]
    official_refs: tuple[Any, ...]
    limitations: tuple[Any, ...]
    coverage: dict[str, Any]
    epistemic_classes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    document_set_hash: str | None
    source_conflict: bool
    object_text: str | None
    organ: str | None
    supplier: str | None
    location: str | None
    present: bool
    usable: bool


@dataclass(frozen=True)
class PeerView:
    version: str | None
    schema: str | None
    content_hash: str | None
    status: str
    metrics: dict[str, Any]
    comparisons: tuple[Any, ...]
    present: bool
    not_comparable: bool
    canonical_contract_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContractView:
    canonical_contract_ids: tuple[str, ...]
    updated_at: str | None
    document_set_hash: str | None
    latest_observation_at: str | None


def adapt_score(raw: dict[str, Any] | None) -> ScoreView:
    if not isinstance(raw, dict) or not raw:
        return ScoreView(None, (), None, None, None, None, None, None, None, False, False, False)
    nested = raw.get("score") if isinstance(raw.get("score"), dict) else {}
    published = raw.get("publication_value_score") if isinstance(raw.get("publication_value_score"), dict) else {}
    value = _float(raw.get("value"))
    if value is None:
        value = _float(nested.get("value"))
    if value is None:
        value = _float(published.get("value"))
    version = _text(
        raw.get("version") or raw.get("contract_version") or nested.get("version") or published.get("version")
    )
    schema = _text(raw.get("schema") or nested.get("schema"))
    if schema is None and (version or value is not None):
        schema = SCORE_SCHEMA
    formula = _text(
        raw.get("formula_version")
        or raw.get("score_formula_version")
        or nested.get("formula_version")
        or published.get("formula_version")
    )
    candidate_id = _text(raw.get("analysis_candidate_id") or raw.get("candidate_id") or raw.get("id"))
    angle = _text(raw.get("angle") or nested.get("angle"))
    if angle not in ANGLES:
        for item in _tuple(raw.get("suggested_analysis_angles") or raw.get("analysis_angles")):
            if _text(item) in ANGLES:
                angle = _text(item)
                break
        else:
            angle = angle if angle in ANGLES else None
    reason = _text(raw.get("reason_summary") or nested.get("reason_summary") or published.get("reason_code"))
    status = _text(raw.get("status") or raw.get("candidate_status") or raw.get("candidate_state"))
    usable = bool(candidate_id or _canonical_ids(raw)) and bool(schema or version or formula or value is not None)
    return ScoreView(
        analysis_candidate_id=candidate_id,
        canonical_contract_ids=_canonical_ids(raw),
        value=value,
        version=version,
        schema=schema,
        formula_version=formula,
        reason_summary=reason,
        angle=angle,
        status=status,
        after_refresh=bool(raw.get("after_refresh")),
        present=True,
        usable=usable,
    )


def adapt_evidence(raw: dict[str, Any] | None) -> EvidenceView:
    if not isinstance(raw, dict) or not raw:
        return EvidenceView(
            None, None, None, None, (), (), (), (), (), {}, (), (), None, False, None, None, None, None, False, False
        )
    reasons = _texts(raw.get("reason_codes"))
    conflict = bool(raw.get("source_conflict")) or any(
        code in {"SOURCE_CONFLICT", "VALUE_CONFLICT"} for code in reasons
    )
    content_hash = _text(raw.get("content_hash") or raw.get("hash"))
    source_as_of = _text(raw.get("source_as_of") or raw.get("as_of"))
    identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
    parties = raw.get("parties") if isinstance(raw.get("parties"), dict) else {}
    location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    return EvidenceView(
        version=_text(raw.get("version") or raw.get("schema_version") or raw.get("contract_version")),
        schema=_text(raw.get("schema")),
        content_hash=content_hash,
        source_as_of=source_as_of,
        canonical_contract_ids=_canonical_ids(raw),
        timeline=_tuple(raw.get("timeline")),
        calculations=_tuple(raw.get("calculations")),
        official_refs=_tuple(raw.get("official_refs") or raw.get("source_refs") or raw.get("official_references")),
        limitations=_tuple(raw.get("limitations")),
        coverage=dict(raw.get("coverage") or {}),
        epistemic_classes=tuple(item for item in (_text(x) for x in _tuple(raw.get("epistemic_classes"))) if item),
        reason_codes=reasons,
        document_set_hash=_text(raw.get("document_set_hash")),
        source_conflict=conflict,
        object_text=_text(raw.get("object") or raw.get("objeto") or identity.get("object") or identity.get("objeto")),
        organ=_text(raw.get("organ") or raw.get("orgao") or parties.get("organ") or parties.get("orgao")),
        supplier=_text(
            raw.get("supplier") or raw.get("contratado") or parties.get("supplier") or parties.get("contratado")
        ),
        location=_text(raw.get("location_label") or location.get("label") or location.get("municipality")),
        present=True,
        usable=bool(content_hash) and bool(source_as_of),
    )


def adapt_peer(raw: dict[str, Any] | None) -> PeerView:
    if not isinstance(raw, dict) or not raw:
        return PeerView(None, None, None, "ABSENT", {}, (), False, False, ())
    producer = _text(raw.get("status") or raw.get("state") or raw.get("peer_status"))
    status = PEER_MAP.get(producer or "", "ABSENT")
    if producer is None:
        status = "ABSENT"
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    comparisons = _tuple(raw.get("comparisons"))
    not_comparable = status in {"NOT_COMPARABLE"} or bool(raw.get("not_comparable"))
    return PeerView(
        version=_text(raw.get("version") or raw.get("contract_version")),
        schema=_text(raw.get("schema")),
        content_hash=_text(raw.get("content_hash") or raw.get("hash")),
        status=status,
        metrics=dict(metrics),
        comparisons=comparisons,
        present=True,
        not_comparable=not_comparable,
        canonical_contract_ids=_canonical_ids(raw),
    )


def adapt_contract(raw: dict[str, Any] | None) -> ContractView:
    if not isinstance(raw, dict) or not raw:
        return ContractView((), None, None, None)
    return ContractView(
        canonical_contract_ids=_canonical_ids(raw),
        updated_at=_text(raw.get("updated_at") or raw.get("source_updated_at")),
        document_set_hash=_text(raw.get("document_set_hash")),
        latest_observation_at=_text(raw.get("latest_observation_at") or raw.get("observed_at")),
    )


def _score_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    score = raw.get("score")
    if isinstance(score, dict):
        merged = dict(score)
        if raw.get("analysis_candidate_id") and "analysis_candidate_id" not in merged:
            merged["analysis_candidate_id"] = raw["analysis_candidate_id"]
        return merged
    if isinstance(raw.get("candidate_score"), dict):
        merged = dict(raw["candidate_score"])
        if raw.get("analysis_candidate_id"):
            merged.setdefault("analysis_candidate_id", raw["analysis_candidate_id"])
        if raw.get("angle"):
            merged.setdefault("angle", raw["angle"])
        return merged
    return None


def _later_than(left: str | None, right: str | None) -> bool:
    from scripts.public_read_consumers.gates import parse_datetime

    later = parse_datetime(left)
    cutoff = parse_datetime(right)
    if later is None or cutoff is None:
        return False
    return later > cutoff


def _score_version_ok(score: ScoreView) -> bool:
    if not score.present:
        return False
    if score.schema and score.schema != SCORE_SCHEMA:
        return False
    if score.version and score.version not in EXPECTED_VERSIONS:
        return False
    if score.formula_version and score.formula_version != SCORE_FORMULA:
        return False
    if score.version is None and score.schema is None and score.formula_version is None:
        return False
    return True


def evaluate_readiness(
    *,
    score: ScoreView,
    evidence: EvidenceView,
    peer: PeerView,
    contract: ContractView,
    generated_at: str,
    catalog_mode: str,
    claimed_live: bool,
) -> tuple[str, tuple[str, ...], dict[str, Any]]:
    reasons: list[str] = []
    if not score.usable or not evidence.usable:
        reasons.append(REASON_PRODUCER_MISSING)
    if evidence.present and is_stale(generated_at=generated_at, source_as_of=evidence.source_as_of):
        reasons.append(REASON_STALE_EVIDENCE)
    if score.present and not _score_version_ok(score):
        reasons.append(REASON_SCORE_VERSION)
    if evidence.source_conflict:
        reasons.append(REASON_SOURCE_CONFLICT)
    if evidence.usable and _later_than(contract.updated_at, evidence.source_as_of):
        reasons.append(REASON_CONTRACT_UPDATED)
    if (
        evidence.usable
        and contract.document_set_hash
        and evidence.document_set_hash
        and contract.document_set_hash != evidence.document_set_hash
    ):
        reasons.append(REASON_CONTRACT_UPDATED)
    if evidence.usable and _later_than(contract.latest_observation_at, evidence.source_as_of):
        reasons.append(REASON_MATERIAL_OBSERVATION)
    if score.present and (score.status or "").lower() in {"rejected", "reject"}:
        reasons.append(REASON_CANDIDATE_REJECTED)
    reasons.extend(refuse_fixture_as_live({"catalog_mode": catalog_mode, "claimed_live": claimed_live}))
    if peer.not_comparable:
        reasons.append(REASON_NOT_COMPARABLE)
    ordered = tuple(code for code in MATERIAL_CODES if code in reasons)
    blocking = tuple(code for code in ordered if code not in INFORMATIONAL)
    if any(code in REJECT_CODES for code in blocking):
        state = DATA_REJECT
    elif any(code in HOLD_CODES for code in blocking):
        state = DATA_HOLD
    else:
        state = DATA_READY
    facts = {
        "producers_present": {
            "score": score.present and score.usable,
            "evidence_pack": evidence.present and evidence.usable,
            "peer_group": peer.present,
        },
        "peer_optional": True,
        "peer_status": peer.status,
        "score_version": score.version,
        "expected_score_version": "1.0",
        "score_schema": score.schema,
        "evidence_stale": REASON_STALE_EVIDENCE in ordered,
        "source_conflict": REASON_SOURCE_CONFLICT in ordered,
        "contract_updated_after_evidence_pack": REASON_CONTRACT_UPDATED in ordered,
        "material_observation_after_pack": REASON_MATERIAL_OBSERVATION in ordered,
        "candidate_status": score.status,
        "after_refresh": score.after_refresh,
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "data_ready_is_not_index_permission": True,
        "justification": (
            "producers present, versions match, evidence within freshness window"
            if state == DATA_READY and REASON_NOT_COMPARABLE not in ordered
            else (
                "producers present; informational NOT_COMPARABLE"
                if state == DATA_READY
                else ",".join(code for code in ordered if code not in INFORMATIONAL)
            )
        ),
    }
    return state, ordered, facts


def _typed_calculation(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "name": None,
            "value": item,
            "unit": None,
            "epistemic_class": "CALCULATION" if item is not None else "UNKNOWN",
            "method": None,
        }
    epistemic = item.get("epistemic_class") or item.get("class") or "CALCULATION"
    if epistemic not in EPISTEMIC:
        epistemic = "CALCULATION"
    value = item.get("value")
    if "amount" in item and value is None:
        value = item.get("amount")
    if epistemic == "UNKNOWN":
        value = None
    return {
        "name": item.get("name") or item.get("id"),
        "value": value,
        "unit": item.get("unit"),
        "epistemic_class": epistemic,
        "method": item.get("method"),
        "inputs": item.get("inputs"),
    }


def _official_refs(evidence: EvidenceView) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in evidence.official_refs:
        if isinstance(item, dict):
            refs.append(
                {
                    "source_id": item.get("source_id") or item.get("source"),
                    "source_record_id": item.get("source_record_id") or item.get("id"),
                    "locator": item.get("locator") or item.get("url") or item.get("raw_uri"),
                    "content_hash": item.get("content_hash") or item.get("hash"),
                }
            )
        else:
            refs.append({"locator": str(item)})
    return refs


def _merge_ids(*groups: tuple[str, ...]) -> list[str]:
    seen: list[str] = []
    for group in groups:
        for item in group:
            if item not in seen:
                seen.append(item)
    return seen


def project_analysis(
    raw: dict[str, Any],
    *,
    generated_at: str,
    catalog_mode: str,
    claimed_live: bool,
) -> dict[str, Any]:
    score = adapt_score(_score_raw(raw) or (raw if raw.get("publication_value_score") else None))
    if not score.present and raw.get("analysis_candidate_id"):
        score = adapt_score({"analysis_candidate_id": raw.get("analysis_candidate_id"), **(raw.get("score") or {})})
    evidence = adapt_evidence(raw.get("evidence_pack"))
    peer = adapt_peer(raw.get("peer_group") or raw.get("comparables"))
    contract = adapt_contract(raw.get("contract"))
    state, reasons, facts = evaluate_readiness(
        score=score,
        evidence=evidence,
        peer=peer,
        contract=contract,
        generated_at=generated_at,
        catalog_mode=catalog_mode,
        claimed_live=claimed_live,
    )
    candidate_id = score.analysis_candidate_id or _text(raw.get("analysis_candidate_id"))
    calculations = [_typed_calculation(item) for item in evidence.calculations]
    ids = _merge_ids(
        score.canonical_contract_ids,
        evidence.canonical_contract_ids,
        peer.canonical_contract_ids,
        contract.canonical_contract_ids,
    )
    classes: list[str] = []
    for item in evidence.epistemic_classes:
        if item in EPISTEMIC and item not in classes:
            classes.append(item)
    for item in calculations:
        klass = item.get("epistemic_class")
        if klass in EPISTEMIC and klass not in classes:
            classes.append(klass)
    if evidence.timeline and "FACT" not in classes:
        classes.append("FACT")
    if any(item.get("value") is None and item.get("epistemic_class") == "UNKNOWN" for item in calculations):
        if "UNKNOWN" not in classes:
            classes.append("UNKNOWN")
    epistemic = [item for item in EPISTEMIC if item in classes]
    sections = []
    if ids:
        sections.append({"name": "identity", "value": ids[0]})
    if evidence.object_text:
        sections.append({"name": "object", "value": evidence.object_text})
    if evidence.organ:
        sections.append({"name": "organ", "value": evidence.organ})
    if evidence.supplier:
        sections.append({"name": "supplier", "value": evidence.supplier})
    if evidence.location:
        sections.append({"name": "location", "value": evidence.location})
    for item in calculations:
        if item.get("name") in {"nominal_instrument", "nominal_value"} and item.get("value") is not None:
            sections.append(
                {"name": "nominal_value", "value": {"amount": item.get("value"), "currency": item.get("unit") or "BRL"}}
            )
            break
    coverage = dict(evidence.coverage)
    coverage.setdefault("known_timeline_events", len(evidence.timeline))
    coverage.setdefault("calculation_count", len(evidence.calculations))
    coverage.setdefault("official_ref_count", len(evidence.official_refs))
    coverage["peer_status"] = peer.status
    payload = {
        "schema": SCHEMA,
        "analysis_candidate_id": candidate_id,
        "canonical_contract_ids": ids,
        "candidate_score": {
            "value": score.value,
            "version": score.version,
            "schema": score.schema,
            "formula_version": score.formula_version,
            "reason_summary": score.reason_summary,
            "status": score.status,
        },
        "reason_summary": score.reason_summary,
        "evidence_pack_version": evidence.version,
        "evidence_pack_hash": evidence.content_hash,
        "peer_group": {
            "status": peer.status,
            "metrics": _jsonable(peer.metrics),
            "comparisons": _jsonable(peer.comparisons),
            "version": peer.version,
            "schema": peer.schema,
            "content_hash": peer.content_hash,
        },
        "timeline": _jsonable(evidence.timeline),
        "official_refs": _official_refs(evidence),
        "source_refs": _official_refs(evidence),
        "calculations": calculations,
        "epistemic_classes": epistemic,
        "as_of": evidence.source_as_of,
        "freshness": freshness_block(
            generated_at=generated_at,
            source_as_of=evidence.source_as_of,
            stale=REASON_STALE_EVIDENCE in reasons,
            invalidation_keys=(
                "facts",
                "events",
                "coverage",
                "policy",
                "score_hash",
                "evidence_hash",
                "peer_hash",
            ),
        ),
        "coverage": coverage,
        "limitations": _jsonable(evidence.limitations),
        "safety_flags": {
            "data_ready_is_not_index_permission": True,
            "unknown_preserved": True,
            "peer_not_comparable": peer.not_comparable,
            "contains_inference": any(item.get("epistemic_class") == "INFERENCE" for item in calculations),
            "source_conflict": REASON_SOURCE_CONFLICT in reasons,
            "fixture_catalog": catalog_mode == "fixture",
        },
        "data_state": state,
        "publication_readiness": state,
        "data_state_facts": facts,
        "publication_readiness_facts": facts,
        "reason_codes": list(reasons),
        "angle": score.angle or _text(raw.get("angle")),
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "producer_status": "CONTRACT_FIXTURE" if catalog_mode == "fixture" else "OFFICIAL_LIVE",
        "official_live": bool(claimed_live) and catalog_mode == "official_live",
        "selected_factual_sections": sections,
        "method_version": "public-read-consumers/contract-analysis/1.0",
        "schema_version": "v1.0.0",
    }
    missing = [name for name in PAYLOAD_FIELDS if name not in payload]
    if missing:
        raise ValueError(f"projector_field_set_mismatch:{missing}")
    if payload["data_state"] not in {DATA_READY, DATA_HOLD, DATA_REJECT}:
        raise ValueError(f"forbidden_data_state:{payload['data_state']}")
    assert_public_clean(payload)
    return payload


def project_catalog(raw: dict[str, Any]) -> list[dict[str, Any]]:
    generated_at = str(raw.get("generated_at") or "")
    if not generated_at:
        raise ValueError("generated_at is required")
    catalog_mode = str(raw.get("catalog_mode") or "fixture")
    claimed = bool(raw.get("claimed_live", False))
    if catalog_mode == "fixture":
        claimed = bool(raw.get("claimed_live", False))
    candidates = raw.get("candidates") or raw.get("analyses") or []
    return [
        project_analysis(dict(item), generated_at=generated_at, catalog_mode=catalog_mode, claimed_live=claimed)
        for item in candidates
    ]


@dataclass(frozen=True)
class CanaryResult:
    selected_ids: tuple[str, ...]
    selected: tuple[dict[str, Any], ...]
    angles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    shortfall: bool


def _score_value(item: dict[str, Any]) -> float:
    nested = item.get("candidate_score") or {}
    value = nested.get("value") if isinstance(nested, dict) else None
    if value is None:
        return float("-inf")
    return float(value)


def select_canary(items: list[dict[str, Any]]) -> CanaryResult:
    ready = sorted(
        [item for item in items if item.get("data_state") == DATA_READY],
        key=lambda item: (-_score_value(item), str(item.get("analysis_candidate_id") or "")),
    )
    if len(ready) <= CANARY_MAX:
        selected = ready
    else:
        picked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in ready:
            angle = item.get("angle")
            if angle and angle not in seen and len(picked) < CANARY_MAX:
                picked.append(item)
                seen.add(str(angle))
        ids = {item.get("analysis_candidate_id") for item in picked}
        for item in ready:
            if len(picked) >= CANARY_MAX:
                break
            if item.get("analysis_candidate_id") not in ids:
                picked.append(item)
                ids.add(item.get("analysis_candidate_id"))
        selected = sorted(picked, key=lambda item: (-_score_value(item), str(item.get("analysis_candidate_id") or "")))
    selected_ids = tuple(str(item["analysis_candidate_id"]) for item in selected if item.get("analysis_candidate_id"))
    angles = tuple(dict.fromkeys(item["angle"] for item in selected if item.get("angle")))
    shortfall = len(selected) < CANARY_MIN
    codes: set[str] = set()
    if shortfall:
        for item in items:
            if item.get("data_state") == DATA_READY:
                continue
            for code in item.get("reason_codes") or ():
                codes.add(str(code))
        if not items or not codes:
            codes.add(REASON_PRODUCER_MISSING)
    return CanaryResult(
        selected_ids=selected_ids,
        selected=tuple(selected),
        angles=angles,
        reason_codes=tuple(code for code in MATERIAL_CODES if code in codes),
        shortfall=shortfall,
    )


def status_report(canary: CanaryResult, *, catalog_mode: str, claimed_live: bool, generated_at: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "selected_candidate_ids": list(canary.selected_ids),
        "selected_count": len(canary.selected_ids),
        "target_min": CANARY_MIN,
        "target_max": CANARY_MAX,
        "angles": list(canary.angles),
        "shortfall": canary.shortfall,
        "reason_codes": list(canary.reason_codes),
        "data_ready_is_not_index_permission": True,
    }


def render_status_markdown(report: dict[str, Any]) -> str:
    ids = report["selected_candidate_ids"]
    lines = [
        "# Contract analysis canary status",
        "",
        f"- schema: `{report['schema']}`",
        f"- generated_at: `{report['generated_at']}`",
        f"- catalog_mode: `{report['catalog_mode']}`",
        f"- claimed_live: `{report['claimed_live']}`",
        f"- selected_count: `{report['selected_count']}` (target {report['target_min']}–{report['target_max']})",
        f"- shortfall: `{report['shortfall']}`",
        f"- angles: `{', '.join(report['angles']) or 'none'}`",
        "- DATA_READY is not permission to index",
        "",
        "## Selected",
    ]
    if ids:
        lines.extend(f"- `{item}`" for item in ids)
    else:
        lines.append("- none")
    if report["reason_codes"]:
        lines.extend(["", "## Shortfall reason codes"])
        lines.extend(f"- `{code}`" for code in report["reason_codes"])
    return "\n".join(lines) + "\n"


def validate_analysis_payload(document: dict[str, Any]) -> None:
    missing = [name for name in PAYLOAD_FIELDS if name not in document]
    if missing:
        raise ValueError(f"schema_validation_missing:{missing}")
    if document.get("schema") != SCHEMA:
        raise ValueError(f"schema_validation_schema:{document.get('schema')}")
    if document.get("data_state") not in {DATA_READY, DATA_HOLD, DATA_REJECT}:
        raise ValueError(f"schema_validation_data_state:{document.get('data_state')}")
    if document.get("data_state") in {"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX"}:
        raise ValueError("schema_validation_forbidden_state:INDEX")
    for klass in document.get("epistemic_classes") or ():
        if klass not in EPISTEMIC:
            raise ValueError(f"schema_validation_epistemic:{klass}")
    peer = document.get("peer_group") or {}
    if peer.get("status") not in PEER_STATUSES:
        raise ValueError(f"schema_validation_peer_status:{peer.get('status')}")
    assert_public_clean(document)


def hashed_analysis(document: dict[str, Any]) -> dict[str, Any]:
    validate_analysis_payload(document)
    return attach_hash(document)
