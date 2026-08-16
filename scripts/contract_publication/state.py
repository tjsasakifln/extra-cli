"""Explicit REJECT / HOLD_FOR_DATA / EDITORIAL_REVIEW policy.

Value alone never promotes. UNKNOWN freshness blocks review. An unsourced
anomaly holds. High reputational exposure adds a review flag, never an accusation.
"""

from __future__ import annotations

from scripts.contract_publication.facts import ProjectedRecord, claims_national, geographic_scope
from scripts.contract_publication.models import DetectorResult, ScoreComponent
from scripts.contract_publication.schema import INSIGHT_DETECTOR_IDS, CandidateState, policy_thresholds
from scripts.contract_publication.score import AggregateScore, component_by_name


def sourced_insight_detectors(detectors: tuple[DetectorResult, ...]) -> tuple[DetectorResult, ...]:
    return tuple(
        item
        for item in detectors
        if item.detector_id in INSIGHT_DETECTOR_IDS and item.status == "KNOWN" and item.fired and item.evidence_refs
    )


def unsourced_insight_detectors(detectors: tuple[DetectorResult, ...]) -> tuple[DetectorResult, ...]:
    return tuple(
        item
        for item in detectors
        if item.detector_id in INSIGHT_DETECTOR_IDS and item.status == "KNOWN" and item.fired and not item.evidence_refs
    )


def missing_detector_fields(detectors: tuple[DetectorResult, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for item in detectors:
        if item.status in {"UNKNOWN", "HOLD"} and item.missing_fields:
            for field in item.missing_fields:
                if field not in missing:
                    missing.append(field)
    return tuple(missing)


def sensitivity_flags(projected: ProjectedRecord, detectors: tuple[DetectorResult, ...]) -> tuple[str, ...]:
    flags: list[str] = []
    by_id = {item.detector_id: item for item in detectors}
    if by_id.get("documented_rescission") and by_id["documented_rescission"].fired:
        flags.append("lifecycle_rescission")
    if by_id.get("documented_suspension") and by_id["documented_suspension"].fired:
        flags.append("lifecycle_suspension")
    contractor_type = str(projected.record.get("fornecedor_tipo") or projected.record.get("contractor_type") or "")
    if contractor_type.upper() in {"PF", "PESSOA FISICA", "FISICA", "NATURAL PERSON"}:
        flags.append("natural_person_contractor")
    if projected.record.get("fornecedor_cpf") or projected.record.get("cpf"):
        flags.append("natural_person_identifier")
    if by_id.get("observable_concentration") and by_id["observable_concentration"].fired:
        flags.append("observable_concentration")
    if flags:
        flags.append("reputational_review_required")
    return tuple(flags)


def dominant_single_component(components: tuple[ScoreComponent, ...]) -> bool:
    known = [item for item in components if item.status == "KNOWN" and item.value is not None]
    if len(known) < 2:
        return False
    ranked = sorted(known, key=lambda item: float(item.value), reverse=True)
    top = float(ranked[0].value)
    rest = [float(item.value) for item in ranked[1:]]
    if top < 0.70:
        return False
    return all(value <= 0.35 for value in rest)


def decide_state(
    projected: ProjectedRecord,
    detectors: tuple[DetectorResult, ...],
    components: tuple[ScoreComponent, ...],
    aggregate: AggregateScore,
    *,
    freshness_status: str,
    duplicate: bool,
    policy: dict | None = None,
) -> tuple[CandidateState, tuple[str, ...]]:
    thresholds = policy_thresholds(policy)
    if duplicate:
        return "REJECT", ("duplicate_collapsed",)
    if not projected.canonical_contract_id:
        return "REJECT", ("missing_identity",)
    if projected.catalog_mode == "official_live":
        return "REJECT", ("fixture_as_live",)

    scope = geographic_scope(projected.record)
    if claims_national(projected.record) and scope in {"local", None}:
        return "REJECT", ("local_labeled_national",)
    if claims_national(projected.record) and not projected.record.get("national_denominator"):
        if scope in {"local", "municipal", "uf"} or projected.record.get("uf"):
            return "REJECT", ("local_labeled_national",)

    insight = component_by_name(components, "insight_or_anomaly_strength")
    defense = component_by_name(components, "defensibility")
    commercial = component_by_name(components, "commercial_relevance")
    sourced = sourced_insight_detectors(detectors)
    unsourced = unsourced_insight_detectors(detectors)
    flags = sensitivity_flags(projected, detectors)

    if unsourced and not sourced:
        return "HOLD_FOR_DATA", ("anomaly_without_source",)

    if freshness_status == "STALE":
        return "HOLD_FOR_DATA", ("snapshot_stale",)

    anniversary = next((item for item in detectors if item.detector_id == "adjustment_anniversary"), None)
    if (
        anniversary
        and anniversary.status == "UNKNOWN"
        and projected.record.get("adjustment_anniversary")
        and not sourced
    ):
        return "HOLD_FOR_DATA", ("detector_field_missing",)

    if freshness_status == "UNKNOWN" and sourced:
        return "HOLD_FOR_DATA", ("missing_observed_at",)

    insight_ok = (
        insight.status == "KNOWN"
        and insight.value is not None
        and insight.value >= thresholds.get("review_min_insight", 0.40)
    )
    defense_ok = (
        defense.status == "KNOWN"
        and defense.value is not None
        and defense.value >= thresholds.get("review_min_defensibility", 0.50)
    )
    score_ok = (
        aggregate.status == "KNOWN"
        and aggregate.value is not None
        and aggregate.value >= thresholds.get("review_min_score", 0.42)
        and aggregate.known_weight_fraction >= thresholds.get("review_min_known_weight_fraction", 0.50)
    )
    sourced_ok = len(sourced) >= int(thresholds.get("review_min_sourced_insight_detectors", 1))

    if insight_ok and defense_ok and score_ok and sourced_ok and freshness_status == "FRESH":
        reasons = ["review_gates_passed"]
        if "reputational_review_required" in flags:
            reasons.append("reputational_review_required")
        return "EDITORIAL_REVIEW", tuple(reasons)

    if dominant_single_component(components) and not insight_ok:
        return "REJECT", ("single_component_dominance",)

    high_value = (
        commercial.status == "KNOWN" and commercial.value is not None and commercial.value >= 0.55 and not insight_ok
    )
    if high_value:
        return "REJECT", ("high_value_without_insight",)

    if not insight_ok:
        return "REJECT", ("no_verifiable_insight",)

    return "HOLD_FOR_DATA", ("hold_for_missing_evidence",)
