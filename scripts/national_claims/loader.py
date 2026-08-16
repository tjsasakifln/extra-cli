"""Load a national-claims request from a Goal 01–03 fixture JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.national_claims.models import (
    METHOD_VERSION,
    POLICY_VERSION,
    ClaimRequest,
    ClaimSpec,
    EvidenceRow,
    FreshnessInput,
    LkgRecord,
    OrgSpec,
    PartitionRecord,
    VersionedUniverse,
)
from scripts.national_claims.universe import (
    build_companion_universe,
    build_national_universe,
    build_universe_bundle,
)


def _orgs(raw: list[Any]) -> tuple[OrgSpec, ...]:
    orgs: list[OrgSpec] = []
    for item in raw:
        orgs.append(
            OrgSpec(
                org_id=str(item["org_id"]),
                name=str(item.get("name") or item["org_id"]),
                unit_count=int(item.get("unit_count") or 1),
                geography=item.get("geography"),
            )
        )
    return tuple(orgs)


def _universe(raw: dict[str, Any], *, kind: str) -> VersionedUniverse:
    orgs = _orgs(list(raw.get("orgs") or raw.get("expected_orgs") or []))
    common = {
        "official_source": str(raw.get("official_source") or raw.get("source") or "pncp"),
        "competence": str(raw["competence"]),
        "cutoff": str(raw["cutoff"]),
        "orgs": orgs,
        "method_version": str(raw.get("method_version") or raw.get("method") or METHOD_VERSION),
        "inclusion_rules": tuple(raw.get("inclusion_rules") or ("declared",)),
        "exclusion_rules": tuple(raw.get("exclusion_rules") or ("none",)),
        "version_changes": tuple(raw.get("version_changes") or ()),
        "owner": str(raw.get("owner") or "contracts-truth"),
        "review_cadence": str(raw.get("review_cadence") or "weekly"),
    }
    if kind == "national":
        return build_national_universe(**common)
    return build_companion_universe(universe_kind=kind, **common)


def _partition(raw: dict[str, Any]) -> PartitionRecord:
    return PartitionRecord(
        partition_id=str(raw["partition_id"]),
        expected=bool(raw.get("expected", True)),
        attempted=bool(raw.get("attempted", False)),
        status=raw.get("status") or "UNKNOWN",  # type: ignore[arg-type]
        pages_fetched=raw.get("pages_fetched"),
        pages_expected=raw.get("pages_expected"),
        records=raw.get("records"),
        pagination_complete=bool(raw.get("pagination_complete", False)),
        request_complete=bool(raw.get("request_complete", False)),
        raw_ref=raw.get("raw_ref"),
        evidence_ref=raw.get("evidence_ref") or raw.get("evidence"),
        checked_at=raw.get("checked_at"),
        as_of=raw.get("as_of"),
        freshness_status=raw.get("freshness_status"),
        identity_mapped=bool(raw.get("identity_mapped", False)),
        reason=raw.get("reason"),
        next_action=raw.get("next_action"),
    )


def _evidence(raw: dict[str, Any]) -> EvidenceRow:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return EvidenceRow(
        source=str(raw.get("source") or "pncp"),
        entity_id=raw.get("entity_id"),
        canonical_entity_key=raw.get("canonical_entity_key"),
        data_type=raw.get("data_type"),
        state=raw.get("state"),
        count_obtained=raw.get("count_obtained"),
        count_persisted=raw.get("count_persisted"),
        metadata=metadata,
        raw_ref=raw.get("raw_ref"),
        evidence_ref=raw.get("evidence_ref"),
        partition_id=raw.get("partition_id"),
    )


def _lkg(raw: dict[str, Any] | None) -> LkgRecord | None:
    if not raw:
        return None
    return LkgRecord(
        claim_id=str(raw["claim_id"]),
        authorization_state=str(raw.get("authorization_state") or "AUTHORIZED"),
        national_universe_id=str(raw["national_universe_id"]),
        catalog_hash=str(raw["catalog_hash"]),
        method_version=str(raw["method_version"]),
        source_version=str(raw["source_version"]),
        content_hash=str(raw["content_hash"]),
        authorized_at=str(raw["authorized_at"]),
        expires_at=str(raw["expires_at"]),
        invalidated_at=raw.get("invalidated_at"),
        invalidation_reason=raw.get("invalidation_reason"),
    )


def request_from_dict(document: dict[str, Any]) -> ClaimRequest:
    claim_raw = document["claim"]
    universes_raw = document["universes"]
    bundle = build_universe_bundle(
        national=_universe(universes_raw["national"], kind="national"),
        icp_commercial=_universe(universes_raw["icp_commercial"], kind="icp_commercial"),
        extra_1093_monitored=_universe(universes_raw["extra_1093_monitored"], kind="extra_1093_monitored"),
        observed_corpus=_universe(universes_raw["observed_corpus"], kind="observed_corpus"),
    )
    freshness_raw = document["freshness"]
    claim = ClaimSpec(
        claim_id=str(claim_raw["claim_id"]),
        scope=claim_raw["scope"],  # type: ignore[arg-type]
        period=str(claim_raw["period"]),
        sources=tuple(str(item) for item in claim_raw.get("sources") or ("pncp",)),
        typology=claim_raw.get("typology"),
        geography=str(claim_raw["geography"]),
        snapshot=str(claim_raw["snapshot"]),
        cutoff=str(claim_raw["cutoff"]),
        policy_version=str(claim_raw.get("policy_version") or POLICY_VERSION),
        denominator_kind=str(claim_raw.get("denominator_kind") or "national"),
        infer_completeness_from_row_count=bool(claim_raw.get("infer_completeness_from_row_count", False)),
    )
    return ClaimRequest(
        claim=claim,
        universes=bundle,
        partitions=tuple(_partition(item) for item in document.get("partitions") or []),
        evidence=tuple(_evidence(item) for item in document.get("evidence") or []),
        freshness=FreshnessInput(
            age_hours=float(freshness_raw.get("age_hours") or 0),
            lag_p99_hours=float(freshness_raw.get("lag_p99_hours") or 0),
            as_of=str(freshness_raw["as_of"]),
            layer=str(freshness_raw.get("layer") or "publication"),
        ),
        prior_lkg=_lkg(document.get("prior_lkg")),
        source_version=str(document.get("source_version") or "pncp/1.0"),
        producer_sha=str(document.get("producer_sha") or "fixture"),
    )


def load_request(path: str | Path) -> ClaimRequest:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("fixture must be a JSON object")
    return request_from_dict(document)
