"""PUBLICATION_VALUE_SCORE — weighted geometric mean of KNOWN components.

UNKNOWN is omitted from the product. It is never stored as 0.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal

from scripts.contract_publication.detectors import DetectorResult
from scripts.contract_publication.facts import (
    ProjectedRecord,
    explicit_evidence_refs,
    fact_value,
    nominal_amount,
)
from scripts.contract_publication.models import AggregateScore, ScoreComponent
from scripts.contract_publication.schema import (
    COMPONENT_NAMES,
    INSIGHT_DETECTOR_IDS,
    SCORE_FORMULA_VERSION,
    STALE_MAX_AGE_HOURS,
    declared_weights,
)


def _quantize(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.000001")))


def _by_id(detectors: Iterable[DetectorResult]) -> dict[str, DetectorResult]:
    return {item.detector_id: item for item in detectors}


def _refs(*groups: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.append(item)
    return tuple(seen)


def _weights(policy: dict | None) -> dict[str, float]:
    return declared_weights(policy)


def _known_component(
    name: str,
    value: float,
    *,
    reason: str | None,
    evidence: tuple[str, ...],
    detectors: tuple[str, ...],
    weights: dict[str, float],
) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        status="KNOWN",
        value=_quantize(max(0.0, min(1.0, value))),
        weight=weights[name],
        reason_code=reason,
        evidence_refs=evidence,
        contributing_detectors=detectors,
    )


def _unknown_component(name: str, reason: str, weights: dict[str, float]) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        status="UNKNOWN",
        value=None,
        weight=weights[name],
        reason_code=reason,
        evidence_refs=(),
        contributing_detectors=(),
    )


def _value_relevance(amount: Decimal) -> float:
    if amount < Decimal("100000"):
        return 0.15
    if amount < Decimal("1000000"):
        return 0.35
    if amount < Decimal("10000000"):
        return 0.55
    if amount < Decimal("50000000"):
        return 0.75
    return 0.90


def commercial_relevance(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    amount = nominal_amount(projected)
    if amount is None:
        return _unknown_component("commercial_relevance", "missing_nominal_value", weights)
    material = detectors.get("material_value_change")
    return _known_component(
        "commercial_relevance",
        _value_relevance(amount),
        reason="editorial_instrument_size",
        evidence=explicit_evidence_refs(projected.record),
        detectors=("material_value_change",) if material and material.status == "KNOWN" else (),
        weights=weights,
    )


def demand_fit(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    del projected
    theme = detectors.get("demand_theme")
    if theme is None or theme.status != "KNOWN":
        return _unknown_component("demand_fit", theme.reason_code if theme else "missing_object", weights)
    return _known_component(
        "demand_fit",
        theme.strength or 0.0,
        reason=theme.reason_code,
        evidence=theme.evidence_refs,
        detectors=("demand_theme",),
        weights=weights,
    )


def insight_strength(detectors: dict[str, DetectorResult], weights: dict[str, float]) -> ScoreComponent:
    known_fired = [
        item
        for detector_id, item in detectors.items()
        if detector_id in INSIGHT_DETECTOR_IDS and item.status == "KNOWN" and item.fired
    ]
    known_any = [
        item
        for detector_id, item in detectors.items()
        if detector_id in INSIGHT_DETECTOR_IDS and item.status == "KNOWN"
    ]
    if not known_any:
        missing = sorted(
            item.reason_code
            for detector_id, item in detectors.items()
            if detector_id in INSIGHT_DETECTOR_IDS and item.status == "UNKNOWN"
        )
        return _unknown_component("insight_or_anomaly_strength", missing[0] if missing else "not_observed", weights)
    if not known_fired:
        return _known_component(
            "insight_or_anomaly_strength",
            0.05,
            reason="no_verifiable_insight",
            evidence=(),
            detectors=tuple(item.detector_id for item in known_any),
            weights=weights,
        )
    ranked = sorted((item.strength or 0.0 for item in known_fired), reverse=True)
    stacked = 0.0
    decay = 1.0
    for strength in ranked:
        stacked += strength * decay
        decay *= 0.55
    return _known_component(
        "insight_or_anomaly_strength",
        min(1.0, stacked),
        reason="sourced_insight_stack" if any(item.evidence_refs for item in known_fired) else "insight_without_source",
        evidence=_refs(*(item.evidence_refs for item in known_fired)),
        detectors=tuple(item.detector_id for item in known_fired),
        weights=weights,
    )


def documentary_richness(detectors: dict[str, DetectorResult], weights: dict[str, float]) -> ScoreComponent:
    item = detectors.get("unusual_documentary_richness")
    if item is None or item.status != "KNOWN":
        return _unknown_component("documentary_richness", item.reason_code if item else "missing_identity", weights)
    return _known_component(
        "documentary_richness",
        item.strength or 0.0,
        reason=item.reason_code,
        evidence=item.evidence_refs,
        detectors=("unusual_documentary_richness",),
        weights=weights,
    )


def comparability(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    del projected
    item = detectors.get("peer_difference")
    if item is None or item.status != "KNOWN":
        return _unknown_component("comparability", item.reason_code if item else "peer_group_absent", weights)
    strength = item.strength or 0.0
    value = 0.45 + 0.55 * strength if item.fired else 0.40
    return _known_component(
        "comparability",
        value,
        reason=item.reason_code,
        evidence=item.evidence_refs,
        detectors=("peer_difference",),
        weights=weights,
    )


def freshness_component(
    age_hours: float | None, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    if age_hours is None:
        return _unknown_component("freshness", "missing_observed_at", weights)
    if age_hours <= 24:
        value = 0.95
    elif age_hours <= STALE_MAX_AGE_HOURS:
        value = 0.80
    elif age_hours <= 24 * 7:
        value = 0.45
    elif age_hours <= 24 * 30:
        value = 0.25
    else:
        value = 0.10
    return _known_component(
        "freshness",
        value,
        reason="observation_age_vs_as_of",
        evidence=(),
        detectors=(),
        weights=weights,
    )


def defensibility(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    fired_insight = [
        item
        for detector_id, item in detectors.items()
        if detector_id in INSIGHT_DETECTOR_IDS and item.status == "KNOWN" and item.fired
    ]
    if not fired_insight:
        if not projected.canonical_contract_id:
            return _unknown_component("defensibility", "missing_identity", weights)
        return _known_component(
            "defensibility",
            0.15,
            reason="no_insight_to_defend",
            evidence=explicit_evidence_refs(projected.record),
            detectors=(),
            weights=weights,
        )
    sourced = [item for item in fired_insight if item.evidence_refs]
    unsourced = [item for item in fired_insight if not item.evidence_refs]
    if unsourced and not sourced:
        return _known_component(
            "defensibility",
            0.10,
            reason="anomaly_without_source",
            evidence=(),
            detectors=tuple(item.detector_id for item in unsourced),
            weights=weights,
        )
    ratio = len(sourced) / len(fired_insight)
    identity_bonus = 0.15 if projected.canonical_contract_id else 0.0
    return _known_component(
        "defensibility",
        min(1.0, 0.35 + 0.50 * ratio + identity_bonus),
        reason="sourced_insight_detectors" if not unsourced else "partial_source_coverage",
        evidence=_refs(*(item.evidence_refs for item in sourced)),
        detectors=tuple(item.detector_id for item in sourced),
        weights=weights,
    )


def citation_potential(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    source = projected.facts.source_id
    identity = projected.canonical_contract_id
    refs = explicit_evidence_refs(projected.record)
    if not identity:
        return _unknown_component("citation_potential", "missing_identity", weights)
    if not source and not refs:
        return _unknown_component("citation_potential", "missing_source", weights)
    score = 0.30
    if source:
        score += 0.25
    if refs:
        score += min(0.30, 0.10 * len(refs))
    if fact_value(projected, "signed_at"):
        score += 0.10
    insight = detectors.get("documented_price_index")
    if insight and insight.fired:
        score += 0.10
    return _known_component(
        "citation_potential",
        min(1.0, score),
        reason="official_identity_and_refs",
        evidence=refs,
        detectors=("documented_price_index",) if insight and insight.fired else (),
        weights=weights,
    )


def editorial_maintenance_cost(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    if not projected.canonical_contract_id:
        return _unknown_component("editorial_maintenance_cost", "missing_identity", weights)
    cost = 0.20
    amendments = detectors.get("documented_amendment")
    if amendments and amendments.fired and amendments.result:
        count = int((amendments.result or {}).get("count") or 0)
        cost += min(0.35, 0.07 * count)
    if any(item.status == "HOLD" for item in detectors.values()):
        cost += 0.15
    missing_docs = not explicit_evidence_refs(projected.record)
    if missing_docs:
        cost += 0.20
    richness = detectors.get("unusual_documentary_richness")
    if richness and richness.status == "KNOWN" and (richness.strength or 0) < 0.40:
        cost += 0.10
    ease = max(0.05, 1.0 - cost)
    return _known_component(
        "editorial_maintenance_cost",
        ease,
        reason="inverted_maintenance_burden",
        evidence=explicit_evidence_refs(projected.record),
        detectors=tuple(
            item.detector_id for item in detectors.values() if item.fired and item.detector_id.startswith("documented_")
        ),
        weights=weights,
    )


def reputational_sensitivity(
    projected: ProjectedRecord, detectors: dict[str, DetectorResult], weights: dict[str, float]
) -> ScoreComponent:
    if not projected.canonical_contract_id:
        return _unknown_component("reputational_sensitivity", "missing_identity", weights)
    exposure = 0.10
    rescission = detectors.get("documented_rescission")
    if rescission and rescission.fired:
        exposure += 0.35
    suspension = detectors.get("documented_suspension")
    if suspension and suspension.fired:
        exposure += 0.15
    contractor_type = str(projected.record.get("fornecedor_tipo") or projected.record.get("contractor_type") or "")
    if contractor_type.upper() in {"PF", "PESSOA FISICA", "FISICA", "NATURAL PERSON"}:
        exposure += 0.25
    if projected.record.get("fornecedor_cpf") or projected.record.get("cpf"):
        exposure += 0.20
    concentration = detectors.get("observable_concentration")
    if concentration and concentration.fired:
        exposure += 0.10
    safety = max(0.05, 1.0 - exposure)
    return _known_component(
        "reputational_sensitivity",
        safety,
        reason="inverted_reputational_exposure",
        evidence=explicit_evidence_refs(projected.record),
        detectors=tuple(item.detector_id for item in (rescission, suspension, concentration) if item and item.fired),
        weights=weights,
    )


def score_components(
    projected: ProjectedRecord,
    detectors: tuple[DetectorResult, ...],
    *,
    freshness_hours: float | None,
    policy: dict | None = None,
) -> tuple[ScoreComponent, ...]:
    weights = _weights(policy)
    by_id = _by_id(detectors)
    components = (
        commercial_relevance(projected, by_id, weights),
        demand_fit(projected, by_id, weights),
        insight_strength(by_id, weights),
        documentary_richness(by_id, weights),
        comparability(projected, by_id, weights),
        freshness_component(freshness_hours, by_id, weights),
        defensibility(projected, by_id, weights),
        citation_potential(projected, by_id, weights),
        editorial_maintenance_cost(projected, by_id, weights),
        reputational_sensitivity(projected, by_id, weights),
    )
    names = tuple(item.name for item in components)
    if names != COMPONENT_NAMES:
        raise ValueError(f"component_set_mismatch:{sorted(set(COMPONENT_NAMES) ^ set(names))}")
    return components


def aggregate_score(components: tuple[ScoreComponent, ...], *, policy: dict | None = None) -> AggregateScore:
    weights = _weights(policy)
    known = [item for item in components if item.status == "KNOWN" and item.value is not None]
    unknown = tuple(item.name for item in components if item.status != "KNOWN")
    weight_total = sum(weights[name] for name in COMPONENT_NAMES)
    known_weight = sum(item.weight for item in known)
    fraction = _quantize(known_weight / weight_total) if weight_total else 0.0
    if not known:
        return AggregateScore(
            formula_version=SCORE_FORMULA_VERSION,
            value=None,
            status="UNKNOWN",
            known_weight_fraction=fraction,
            unknown_components=unknown,
            reason_code="no_known_components",
            weights=weights,
        )
    clamp = (policy or {}).get("clamp") or {}
    clamp_min = float(clamp.get("min", 0.05))
    clamp_max = float(clamp.get("max", 1.0))
    log_sum = 0.0
    for item in known:
        clamped = min(clamp_max, max(clamp_min, float(item.value)))
        log_sum += item.weight * math.log(clamped)
    return AggregateScore(
        formula_version=SCORE_FORMULA_VERSION,
        value=_quantize(math.exp(log_sum / known_weight)),
        status="KNOWN",
        known_weight_fraction=fraction,
        unknown_components=unknown,
        reason_code=None if not unknown else "partial_components",
        weights=weights,
    )


def component_by_name(components: tuple[ScoreComponent, ...], name: str) -> ScoreComponent:
    for item in components:
        if item.name == name:
            return item
    raise KeyError(name)
