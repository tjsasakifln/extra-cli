"""National claim gate. Reuses #302; Extra 1093 is never a national denominator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.national_contract_truth.freshness_slo import (
    LayerObservation,
    evaluate_layer,
)
from scripts.national_contract_truth.national_universe import (
    EXTRA_COMMERCIAL_DENOMINATOR,
    NationalUniverseError,
    PartitionResult,
    PublishingOrg,
    build_universe,
    reconcile_partitions,
)
from scripts.public_read.models import ResearchPayload

MATERIAL_REASON_CODES = (
    "missing_partitions",
    "blocked_or_failed_partitions",
    "national_denominator_incomplete",
    "freshness_stale",
    "unknown_values",
    "duplicated_source_lineage",
    "inconsistent_denominator_extra_1093",
    "inconsistent_denominator",
)


@dataclass(frozen=True)
class ClaimDecision:
    national_claim_allowed: bool
    nacional_completo: bool
    reason_codes: tuple[str, ...]
    catalog_hash: str | None
    reconciliation_hash: str | None
    national_universe_id: str | None
    extra_1093_used_as_denominator: bool
    expected_partitions: int
    closed_partitions: int
    reconciliation: dict[str, Any]


def _orgs(payload: ResearchPayload) -> tuple[PublishingOrg, ...]:
    return tuple(
        PublishingOrg(
            org_id=str(org["org_id"]),
            source=str(org.get("source") or payload.universe.source),
            competence=str(org.get("competence") or payload.universe.competence),
            name=str(org["name"]),
            unit_count=int(org.get("unit_count") or 1),
        )
        for org in payload.universe.orgs
    )


def _duplicate_lineage(payload: ResearchPayload) -> bool:
    seen: dict[str, set[tuple[str, ...]]] = {}
    for row in payload.rows:
        if row.lineage_resolution:
            continue
        bucket = seen.setdefault(row.process_key, set())
        bucket.add(row.lineage)
        if len(bucket) > 1:
            return True
    return False


def evaluate_national_claim(payload: ResearchPayload) -> ClaimDecision:
    reasons: list[str] = []
    extra_1093 = bool(payload.use_extra_1093_as_denominator)
    if extra_1093 or payload.denominator_kind == "extra_commercial_1093":
        extra_1093 = True
        reasons.append("inconsistent_denominator_extra_1093")
    if payload.claimed_geography == "BR" and extra_1093:
        reasons.append("inconsistent_denominator")
    if len(payload.universe.orgs) == EXTRA_COMMERCIAL_DENOMINATOR and payload.denominator_kind != "publishing_org":
        extra_1093 = True
        if "inconsistent_denominator_extra_1093" not in reasons:
            reasons.append("inconsistent_denominator_extra_1093")

    reconciliation: dict[str, Any] = {
        "nacional_completo": False,
        "catalog_hash": None,
        "reconciliation_hash": None,
        "national_universe_id": None,
        "expected_partitions": len(payload.universe.orgs),
        "consulted_partitions": len(payload.partitions),
        "extra_1093_used_as_denominator": extra_1093,
        "extra_commercial_denominator": EXTRA_COMMERCIAL_DENOMINATOR,
    }
    catalog_hash = None
    reconciliation_hash = None
    universe_id = None
    closed = 0
    expected = len(payload.universe.orgs)

    if not extra_1093:
        try:
            universe = build_universe(
                source=payload.universe.source,
                competence=payload.universe.competence,
                cutoff=payload.universe.cutoff,
                orgs=_orgs(payload),
                method=payload.universe.method,
            )
            results = tuple(
                PartitionResult(
                    partition_id=part.partition_id,
                    status=part.status,  # type: ignore[arg-type]
                    evidence=part.evidence,
                )
                for part in payload.partitions
            )
            reconciliation = reconcile_partitions(universe, results)
            catalog_hash = str(reconciliation["catalog_hash"])
            reconciliation_hash = str(reconciliation["reconciliation_hash"])
            universe_id = str(reconciliation["national_universe_id"])
            expected = int(reconciliation["expected_partitions"])
            by_status = reconciliation["by_status"]
            closed = int(by_status["FOUND"]) + int(by_status["ZERO_CONFIRMED"])
        except NationalUniverseError:
            reasons.append("missing_partitions")
            try:
                universe = build_universe(
                    source=payload.universe.source,
                    competence=payload.universe.competence,
                    cutoff=payload.universe.cutoff,
                    orgs=_orgs(payload),
                    method=payload.universe.method,
                )
                catalog_hash = universe.catalog_hash
                universe_id = universe.national_universe_id
                expected = universe.org_count
            except NationalUniverseError:
                catalog_hash = None

    if any(part.status in {"BLOCKED", "FAILED"} for part in payload.partitions):
        reasons.append("blocked_or_failed_partitions")
    if not reconciliation.get("nacional_completo"):
        reasons.append("national_denominator_incomplete")

    publication = evaluate_layer(
        LayerObservation(
            layer="publication",
            age_since_complete_run=payload.freshness.age,
            lag_p50=payload.freshness.lag_p99,
            lag_p95=payload.freshness.lag_p99,
            lag_p99=payload.freshness.lag_p99,
        )
    )
    if publication.status == "BREACH":
        reasons.append("freshness_stale")

    if any(row.value_status == "UNKNOWN" or row.contract_value_brl is None for row in payload.rows):
        reasons.append("unknown_values")
    if _duplicate_lineage(payload):
        reasons.append("duplicated_source_lineage")

    ordered = tuple(code for code in MATERIAL_REASON_CODES if code in reasons)
    allowed = not ordered and bool(reconciliation.get("nacional_completo"))
    return ClaimDecision(
        national_claim_allowed=allowed,
        nacional_completo=bool(reconciliation.get("nacional_completo")),
        reason_codes=ordered,
        catalog_hash=catalog_hash,
        reconciliation_hash=reconciliation_hash,
        national_universe_id=universe_id,
        extra_1093_used_as_denominator=extra_1093,
        expected_partitions=expected,
        closed_partitions=closed,
        reconciliation=reconciliation,
    )
