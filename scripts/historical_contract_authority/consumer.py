"""Consumer-bound official-live dossier. Producer of facts, never of INDEX."""

from __future__ import annotations

from typing import Any

from scripts.historical_contract_authority.analysis import (
    commercial_adjacency,
    detect_comparative_language,
    resolve_analysis_mode,
    resolve_comparability,
)
from scripts.historical_contract_authority.freshness import dossier_freshness, strip_temporal_for_hash
from scripts.historical_contract_authority.schema import (
    CONSUMER_ID,
    FORBIDDEN_CONCLUSION,
    FORBIDDEN_PUBLIC_STATES,
    content_hash,
    is_sha256,
)

OFFICIAL_LIVE_SCHEMA = "official-live-authority-dossier/1.1"
OFFICIAL_LIVE_SCHEMA_V10 = "official-live-authority-dossier/1.0"
ACCEPTED_OFFICIAL_LIVE_SCHEMAS = frozenset({OFFICIAL_LIVE_SCHEMA, OFFICIAL_LIVE_SCHEMA_V10})
HANDOFF_STATUSES = frozenset({"HANDOFF_READY", "DATA_HOLD", "DATA_REJECT", "UNKNOWN"})


def _blob(*parts: Any) -> str:
    return " ".join(str(item) for item in parts if item).casefold()


def claim_is_located(claim: dict[str, Any]) -> bool:
    locator = claim.get("locator") or claim.get("locators")
    if isinstance(locator, (list, tuple)):
        locator = next((item for item in locator if item), None)
    if isinstance(locator, dict):
        locator = "|".join(str(value) for value in locator.values() if value)
    evidence_id = claim.get("evidence_id") or (claim.get("source_refs") or [None])[0]
    url = claim.get("url") or claim.get("official_url")
    digest = claim.get("sha256") or claim.get("hash") or claim.get("source_document_sha256")
    return bool(evidence_id and url and is_sha256(str(digest or "")) and locator and str(locator) != "UNSPECIFIED")


def validate_consumer_dossier(payload: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    schema = payload.get("schema")
    if schema not in ACCEPTED_OFFICIAL_LIVE_SCHEMAS and schema not in {
        "historical-contract-authority-dossier/1.0",
        "historical-contract-authority-dossier/1.1",
        "public-read-contract-analysis/1.0",
        "official-contract-observation/1.0",
        "official-contract-observation/1.1",
    }:
        if schema:
            reasons.append("unsupported_schema")
    if payload.get("schema") == OFFICIAL_LIVE_SCHEMA:
        for required in (
            "analysis_id",
            "identity",
            "provenance",
            "factual_matrix",
            "analysis",
            "gates",
        ):
            if not payload.get(required):
                reasons.append(f"missing_{required}")
    gates = payload.get("gates") or {}
    if gates.get("official_live") is True:
        provenance = payload.get("provenance") or {}
        if not provenance.get("verified_at") or not provenance.get("retrieved_at"):
            reasons.append("official_live_without_verification_clock")
        if not (payload.get("artifacts") or provenance.get("artifact_hashes")):
            reasons.append("official_live_without_verified_bytes")
    if gates.get("publication_authorization") is True:
        reasons.append("publication_authorization_must_be_false")
    if gates.get("index_authorization") is True:
        reasons.append("index_authorization_must_be_false")
    if gates.get("commercial_relationship_claim") is True:
        reasons.append("commercial_relationship_claim_must_be_false")
    if gates.get("handoff_status") == "HANDOFF_READY":
        claims = (payload.get("factual_matrix") or {}).get("claims") or payload.get("claims") or []
        facts = [item for item in claims if item.get("class") == "FACT" or item.get("klass") == "FACT"]
        if not facts or any(not claim_is_located(item) for item in facts):
            reasons.append("missing_locator_blocks_handoff_ready")
        analysis = payload.get("analysis") or {}
        if not analysis.get("singular_insight"):
            reasons.append("missing_singular_insight")
        if analysis.get("comparability_status") == "NOT_APPLICABLE":
            hits = detect_comparative_language(
                analysis.get("singular_insight"),
                *(item.get("text") for item in claims),
            )
            if hits:
                reasons.append("comparative_language_with_not_applicable")
        if analysis.get("analysis_mode") == "COMPARATIVE" and analysis.get("comparability_status") != "COMPARABLE":
            reasons.append("comparative_not_handoff_ready")
        if gates.get("official_live") is not True:
            reasons.append("handoff_ready_requires_official_live")
    blob = _blob(
        payload.get("analysis", {}).get("singular_insight"),
        *(item.get("text") for item in (payload.get("factual_matrix") or {}).get("claims") or ()),
    )
    if any(term in blob for term in FORBIDDEN_CONCLUSION):
        reasons.append("forbidden_conclusion")
    dumped = str(payload)
    if any(token in dumped for token in FORBIDDEN_PUBLIC_STATES):
        reasons.append("forbidden_public_state")
    return (not reasons), tuple(dict.fromkeys(reasons))


def assemble_consumer_dossier(
    *,
    analysis_id: str,
    identity: dict[str, Any],
    artifacts: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    inferences: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
    insight: str,
    limitations: list[str],
    method: str,
    producer_repo: str,
    producer_commit: str,
    replay_command: str,
    query_window: dict[str, Any],
    retrieved_at: str | None,
    verified_at: str | None,
    source_as_of: str | None,
    event_effective_at: str | None,
    source_published_at: str | None,
    as_of: str,
    bytes_obtained: bool,
    requested_mode: str | None = None,
    engine_status: str | None = None,
    engine_reason_codes: tuple[str, ...] = (),
    unit_compatible: bool = False,
    regime_compatible: bool = False,
    scope_compatible: bool = False,
    period_compatible: bool = False,
    catalog_mode: str = "official_live",
    candidate_disposition: str = "entered",
    candidate_reason: str = "",
) -> dict[str, Any]:
    claim_texts = tuple(str(item.get("text") or "") for item in (*claims, *inferences))
    analysis_mode, comparative_hits = resolve_analysis_mode(
        requested=requested_mode,
        claims=claim_texts,
        insight=insight,
        limitations=tuple(limitations),
        comparative_engine_used=engine_status == "COMPARABLE",
    )
    no_comparison = any("sem compara" in item.casefold() or "no comparison" in item.casefold() for item in limitations)
    comparability = resolve_comparability(
        analysis_mode=analysis_mode,
        comparative_hits=comparative_hits,
        singular_insight=insight,
        limitations_declare_no_comparison=no_comparison and bool(insight),
        engine_status=engine_status,
        engine_reason_codes=engine_reason_codes,
        unit_compatible=unit_compatible,
        regime_compatible=regime_compatible,
        scope_compatible=scope_compatible,
        period_compatible=period_compatible,
    )
    adjacency = commercial_adjacency(insight, identity.get("objeto"), identity.get("object_text"), *claim_texts)
    freshness = dossier_freshness(
        as_of=as_of,
        event_effective_at=event_effective_at,
        source_published_at=source_published_at,
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        source_as_of=source_as_of,
        bytes_obtained=bytes_obtained,
    )
    official_live = bool(bytes_obtained and retrieved_at and verified_at and artifacts)
    artifact_hashes = {
        str(item.get("evidence_id") or item.get("url")): item.get("sha256") for item in artifacts if item.get("sha256")
    }
    matrix = {
        "facts": [item for item in claims if (item.get("class") or item.get("klass")) == "FACT"],
        "calculations": calculations,
        "inferences": inferences,
        "unknowns": unknowns,
        "claims": claims,
    }
    gates = {
        "official_live": official_live,
        "handoff_status": "DATA_HOLD",
        "publication_authorization": False,
        "index_authorization": False,
        "commercial_relationship_claim": False,
    }
    provenance = {
        "schema": OFFICIAL_LIVE_SCHEMA,
        "version": "1.1",
        "producer_repo": producer_repo,
        "producer_commit": producer_commit,
        "query_window": query_window,
        "replay_command": replay_command,
        "retrieved_at": retrieved_at,
        "verified_at": verified_at,
        "source_as_of": source_as_of,
        "event_effective_at": event_effective_at,
        "source_published_at": source_published_at,
        "artifact_hashes": artifact_hashes,
        "consumer": CONSUMER_ID,
    }
    analysis = {
        "analysis_mode": analysis_mode,
        "singular_insight": insight,
        "commercial_adjacency": list(adjacency),
        "method": method,
        "limitations": limitations,
        "comparability_status": comparability["status"],
        "comparability_justification": comparability["justification"],
        "comparability": comparability,
        "reputational_safety": "atipico_nao_e_irregular",
    }
    payload: dict[str, Any] = {
        "schema": OFFICIAL_LIVE_SCHEMA,
        "analysis_id": analysis_id,
        "identity": identity,
        "provenance": provenance,
        "factual_matrix": matrix,
        "analysis": analysis,
        "gates": gates,
        "artifacts": artifacts,
        "freshness": freshness,
        "catalog_mode": catalog_mode,
        "candidate_disposition": candidate_disposition,
        "candidate_reason": candidate_reason,
        "handoff_status": "DATA_HOLD",
    }
    ok, reasons = validate_consumer_dossier({**payload, "gates": {**gates, "handoff_status": "HANDOFF_READY"}})
    if official_live and ok and comparability["status"] in {"NOT_APPLICABLE", "COMPARABLE"}:
        gates["handoff_status"] = "HANDOFF_READY"
        payload["handoff_status"] = "HANDOFF_READY"
        payload["reason_codes"] = ["quality_gates_passed"]
    else:
        extra = [] if ok else list(reasons)
        if not official_live:
            extra.append("official_sources_not_verified_this_run")
        if comparability["status"] not in {"NOT_APPLICABLE", "COMPARABLE"}:
            extra.append(str(comparability["status"]))
        payload["reason_codes"] = list(dict.fromkeys(extra or ["DATA_HOLD"]))
        payload["handoff_status"] = "DATA_HOLD"
        gates["handoff_status"] = "DATA_HOLD"
    payload["gates"] = gates
    payload["content_hash"] = content_hash(strip_temporal_for_hash(payload))
    return payload
