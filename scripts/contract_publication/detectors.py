"""Fact-backed detectors. Absence is UNKNOWN, never a negative event.

Atypical is not irregular. A potential adjustment is not a right to adjust.
A municipality or CNPJ swap is not insight. Peer gaps require a versioned interface.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from scripts.contract_publication.facts import (
    ProjectedRecord,
    explicit_evidence_refs,
    fact_reason,
    fact_status,
    fact_value,
    freshness_hours,
    nominal_amount,
    parse_as_of,
    text,
)
from scripts.contract_publication.models import DetectorResult
from scripts.contract_publication.schema import (
    DETECTOR_VERSION,
    MIN_PEER_SAMPLE,
    PEER_SCHEMAS,
    STALE_MAX_AGE_HOURS,
    policy_thresholds,
)
from scripts.national_contract_truth.contract_events import EVENT_FAMILIES

_SHORT_TERM_DAYS = 30
_LONG_TERM_DAYS = 3650
_PEER_GAP_RATIO = Decimal("0.25")


@dataclass(frozen=True)
class CohortIndex:
    counts_by_supplier: dict[str, int]
    counts_by_organ: dict[str, int]
    counts_by_supplier_organ: dict[tuple[str, str], int]


def _party_key(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def build_cohort(records: Iterable[dict[str, Any]]) -> CohortIndex:
    suppliers: Counter[str] = Counter()
    organs: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for record in records:
        supplier = _party_key(record, "fornecedor_cnpj", "contractor_id")
        organ = _party_key(record, "orgao_cnpj")
        if supplier:
            suppliers[supplier] += 1
        if organ:
            organs[organ] += 1
        if supplier and organ:
            pairs[(supplier, organ)] += 1
    return CohortIndex(
        counts_by_supplier=dict(suppliers),
        counts_by_organ=dict(organs),
        counts_by_supplier_organ=dict(pairs),
    )


def _freshness_payload(projected: ProjectedRecord, as_of: str) -> dict[str, Any]:
    observed = projected.facts.observed_at or text(projected.record.get("observed_at"))
    age = freshness_hours(as_of, observed)
    if age is None:
        status = "UNKNOWN"
    elif age > STALE_MAX_AGE_HOURS:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "as_of": as_of,
        "observed_at": observed,
        "age_hours": None if age is None else round(age, 6),
        "status": status,
    }


def _method(method_id: str, description: str) -> dict[str, str]:
    return {"id": method_id, "version": DETECTOR_VERSION, "description": description}


def _empty(
    detector_id: str,
    reason: str,
    *,
    missing: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    freshness: dict[str, Any] | None = None,
    status: str = "UNKNOWN",
) -> DetectorResult:
    return DetectorResult(
        detector_id=detector_id,
        detector_version=DETECTOR_VERSION,
        fired=False,
        status=status,  # type: ignore[arg-type]
        strength=None,
        result=None,
        reason_code=reason,
        evidence_refs=(),
        epistemic_class="UNKNOWN",
        method=_method(f"{detector_id}/1.0", "fail-closed; absence is not an event"),
        limitations=limitations or ("source_field_absent",),
        freshness=freshness or {},
        missing_fields=missing,
    )


def _known(
    detector_id: str,
    *,
    fired: bool,
    strength: float | None,
    reason: str,
    evidence: tuple[str, ...],
    epistemic: str,
    method: dict[str, str],
    freshness: dict[str, Any],
    result: Any = None,
    events: tuple[str, ...] = (),
    angles: tuple[str, ...] = (),
    peers: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    status: str = "KNOWN",
) -> DetectorResult:
    return DetectorResult(
        detector_id=detector_id,
        detector_version=DETECTOR_VERSION,
        fired=fired,
        status=status,  # type: ignore[arg-type]
        strength=strength,
        result=result,
        reason_code=reason,
        evidence_refs=evidence,
        epistemic_class=epistemic,
        method=method,
        limitations=limitations,
        freshness=freshness,
        missing_fields=missing,
        event_ids=events,
        analysis_angles=angles,
        peer_dimensions=peers,
    )


def _event_ids(items: Any, prefix: str) -> tuple[str, ...]:
    if not items:
        return ()
    if isinstance(items, dict):
        items = (items,)
    ids: list[str] = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            found = item.get("id") or item.get("source_event_id") or item.get("ref")
            ids.append(str(found) if found else f"{prefix}:{index}")
        else:
            ids.append(f"{prefix}:{index}")
    return tuple(ids)


def _delta_amount(items: Any) -> Decimal | None:
    if not items:
        return None
    if isinstance(items, dict):
        items = (items,)
    total = Decimal("0")
    seen = False
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get("delta")
        if raw is None:
            raw = item.get("value_delta")
        if raw is None:
            continue
        total += abs(Decimal(str(raw)))
        seen = True
    return total if seen else None


def _as_items(value: Any) -> tuple[Any, ...]:
    if not value:
        return ()
    if isinstance(value, dict):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def detect_material_value_change(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    if fact_status(projected, "value_changes") != "KNOWN":
        return _empty(
            "material_value_change",
            fact_reason(projected, "value_changes") or "no_amendment_signal",
            missing=("value_changes",),
            freshness=freshness,
        )
    changes = fact_value(projected, "value_changes")
    delta = _delta_amount(changes)
    amount = nominal_amount(projected)
    if delta is None:
        return _empty(
            "material_value_change",
            "value_change_delta_missing",
            missing=("value_changes.delta",),
            freshness=freshness,
            status="HOLD",
            limitations=("delta_not_stated",),
        )
    thresholds = policy_thresholds()
    material_abs = Decimal(str(thresholds.get("value_material_abs_brl", 100000)))
    material_ratio = Decimal(str(thresholds.get("value_material_ratio", 0.05)))
    material = delta >= material_abs or (amount is not None and amount > 0 and (delta / amount) >= material_ratio)
    method = _method(
        "material_value_change/1.0",
        "abs(delta) >= abs_threshold or abs(delta)/nominal >= ratio",
    )
    if not material:
        return _known(
            "material_value_change",
            fired=False,
            strength=0.0,
            reason="value_change_below_materiality",
            evidence=explicit_evidence_refs(projected.record),
            events=_event_ids(changes, "value_change"),
            epistemic="CALCULATION",
            method=method,
            freshness=freshness,
            result={"delta": str(delta), "material": False},
            limitations=("below_materiality_is_not_an_event",),
        )
    ratio = float(delta / amount) if amount and amount > 0 else 0.5
    return _known(
        "material_value_change",
        fired=True,
        strength=min(1.0, 0.45 + ratio),
        reason="material_value_change",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(changes, "value_change"),
        angles=("aditivos_valor",),
        epistemic="CALCULATION",
        method=method,
        freshness=freshness,
        result={"delta": str(delta), "ratio": ratio, "material": True},
        limitations=("atypical_is_not_an_accusation",),
    )


def detect_material_term_change(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    if fact_status(projected, "term_changes") != "KNOWN":
        return _empty(
            "material_term_change",
            fact_reason(projected, "term_changes") or "no_amendment_signal",
            missing=("term_changes",),
            freshness=freshness,
        )
    changes = fact_value(projected, "term_changes")
    return _known(
        "material_term_change",
        fired=True,
        strength=0.55,
        reason="term_change_observed",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(changes, "term_change"),
        angles=("prazo",),
        epistemic="FACT",
        method=_method("material_term_change/1.0", "documented term change on official record"),
        freshness=freshness,
        result={"count": len(_as_items(changes))},
        limitations=("duration_change_is_not_an_accusation",),
    )


def detect_documented_amendment(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    if fact_status(projected, "amendments") != "KNOWN":
        return _empty(
            "documented_amendment",
            fact_reason(projected, "amendments") or "no_amendment_signal",
            missing=("amendments",),
            freshness=freshness,
        )
    amendments = fact_value(projected, "amendments") or ()
    count = len(amendments) if not isinstance(amendments, dict) else 1
    if count <= 0:
        return _empty("documented_amendment", "no_amendment_signal", missing=("amendments",), freshness=freshness)
    return _known(
        "documented_amendment",
        fired=True,
        strength=min(1.0, 0.35 + 0.15 * count),
        reason="amendments_observed",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(amendments, "amendment"),
        angles=("aditivos_valor",),
        epistemic="FACT",
        method=_method("documented_amendment/1.0", "count of sourced official amendments"),
        freshness=freshness,
        result={"count": count},
    )


def detect_documented_apostille(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    apostilles = projected.record.get("apostilas") or projected.record.get("apostilles")
    events = []
    for item in projected.record.get("events") or ():
        if (
            isinstance(item, dict)
            and str(item.get("family") or "") == "apostilamento"
            and "apostilamento" in EVENT_FAMILIES
        ):
            events.append(item)
    if not apostilles and not events:
        return _empty(
            "documented_apostille",
            "not_observed",
            missing=("apostilas",),
            freshness=freshness,
        )
    items = _as_items(apostilles) + tuple(events)
    return _known(
        "documented_apostille",
        fired=True,
        strength=0.50,
        reason="apostille_documented",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(items, "apostille"),
        angles=("aditivos_valor",),
        epistemic="FACT",
        method=_method("documented_apostille/1.0", "official apostille or apostilamento event"),
        freshness=freshness,
        result={"count": len(items)},
    )


def _lifecycle(
    projected: ProjectedRecord, detector_id: str, field: str, family: str, angle: str, as_of: str
) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    observed = fact_status(projected, field) == "KNOWN" if field in projected.by_name else False
    raw = projected.record.get(field) or projected.record.get(detector_id.replace("documented_", ""))
    events = []
    for item in projected.record.get("events") or ():
        if isinstance(item, dict) and str(item.get("family") or "") == family and family in EVENT_FAMILIES:
            events.append(item)
    if not observed and not raw and not events:
        return _empty(detector_id, "not_observed", missing=(field,), freshness=freshness)
    payload = raw if raw else fact_value(projected, field) if observed else events
    return _known(
        detector_id,
        fired=True,
        strength=0.70,
        reason=f"{field}_documented",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(payload, field) + _event_ids(events, family),
        angles=(angle,),
        epistemic="FACT",
        method=_method(f"{detector_id}/1.0", f"documented {field} or official {family} event"),
        freshness=freshness,
        result={"observed": True},
        limitations=("documented_lifecycle_is_not_an_accusation",),
    )


def detect_documented_suspension(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    return _lifecycle(projected, "documented_suspension", "suspension", "suspensao", "prazo", as_of)


def detect_documented_resumption(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    return _lifecycle(projected, "documented_resumption", "resumption", "prorrogacao", "prazo", as_of)


def detect_documented_rescission(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    raw = projected.record.get("rescission") or projected.record.get("rescisao")
    events = [
        item
        for item in projected.record.get("events") or ()
        if isinstance(item, dict)
        and str(item.get("family") or "") in {"rescisao", "cancelamento"}
        and str(item.get("family") or "") in EVENT_FAMILIES
    ]
    if not raw and not events:
        return _empty("documented_rescission", "not_observed", missing=("rescission",), freshness=freshness)
    return _known(
        "documented_rescission",
        fired=True,
        strength=0.75,
        reason="rescission_documented",
        evidence=explicit_evidence_refs(projected.record),
        events=_event_ids(raw, "rescission") + _event_ids(events, "rescisao"),
        angles=("exceptional",),
        epistemic="FACT",
        method=_method("documented_rescission/1.0", "documented rescission or cancellation event"),
        freshness=freshness,
        result={"observed": True},
        limitations=("documented_lifecycle_is_not_an_accusation",),
    )


def detect_adjustment_anniversary(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    if fact_status(projected, "adjustment_anniversary") != "KNOWN":
        return _empty(
            "adjustment_anniversary",
            fact_reason(projected, "adjustment_anniversary") or "no_explicit_adjustment_document",
            missing=("adjustment_anniversary", "adjustment_base_document_id"),
            freshness=freshness,
        )
    value = fact_value(projected, "adjustment_anniversary")
    return _known(
        "adjustment_anniversary",
        fired=True,
        strength=0.55,
        reason="explicit_adjustment_anniversary",
        evidence=explicit_evidence_refs(projected.record),
        events=(f"anniversary:{value}",),
        angles=("reajuste_reequilibrio",),
        epistemic="FACT",
        method=_method(
            "adjustment_anniversary/1.0",
            "requires dated anniversary AND an explicit adjustment instrument",
        ),
        freshness=freshness,
        result={"anniversary": value},
        limitations=("potential_adjustment_is_not_a_right",),
    )


def detect_documented_price_index(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    if fact_status(projected, "indices") != "KNOWN":
        return _empty(
            "documented_price_index",
            fact_reason(projected, "indices") or "bdi_sinapi_sicro_absent",
            missing=("indices", "index_document_id"),
            freshness=freshness,
        )
    indices = fact_value(projected, "indices") or ()
    names: list[str] = []
    if isinstance(indices, dict):
        names.append(str(indices.get("name") or indices.get("kind") or "index"))
    else:
        for item in indices:
            if isinstance(item, dict):
                names.append(str(item.get("name") or item.get("kind") or "index"))
    return _known(
        "documented_price_index",
        fired=True,
        strength=0.65,
        reason="documented_reference_index",
        evidence=explicit_evidence_refs(projected.record),
        events=tuple(f"index:{name}" for name in names),
        angles=("preco_bdi",),
        epistemic="FACT",
        method=_method("documented_price_index/1.0", "BDI/SINAPI/SICRO/price only when a document id is present"),
        freshness=freshness,
        result={"names": names},
        limitations=("documented_index_is_not_overprice",),
    )


def detect_unusual_documentary_richness(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    known = projected.facts.known_count
    total = len(projected.facts.fields)
    if total == 0:
        return _empty(
            "unusual_documentary_richness",
            "missing_identity",
            missing=("canonical_contract_id",),
            freshness=freshness,
        )
    docs = explicit_evidence_refs(projected.record)
    ratio = known / total
    extra = min(0.20, 0.04 * len(docs))
    strength = min(1.0, ratio + extra)
    unusual = ratio >= 0.70 and len(docs) >= 3
    return _known(
        "unusual_documentary_richness",
        fired=unusual,
        strength=strength,
        reason="unusual_known_field_ratio" if unusual else "known_field_ratio",
        evidence=docs,
        angles=("exceptional",) if unusual else (),
        epistemic="CALCULATION",
        method=_method("unusual_documentary_richness/1.0", "known_field_ratio + sourced document count"),
        freshness=freshness,
        result={"known": known, "total": total, "documents": len(docs), "unusual": unusual},
    )


def detect_observable_concentration(projected: ProjectedRecord, cohort: CohortIndex, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    supplier = _party_key(projected.record, "fornecedor_cnpj", "contractor_id")
    organ = _party_key(projected.record, "orgao_cnpj")
    if not supplier:
        return _empty(
            "observable_concentration",
            "missing_contractor",
            missing=("contractor",),
            freshness=freshness,
        )
    pair_count = cohort.counts_by_supplier_organ.get((supplier, organ or ""), 0)
    supplier_count = cohort.counts_by_supplier.get(supplier, 0)
    recurrence = max(pair_count, supplier_count)
    min_rec = int(policy_thresholds().get("concentration_min_recurrence", 3))
    method = _method(
        "observable_concentration/1.0",
        "recurrence of supplier or supplier-organ pair inside the snapshot cohort",
    )
    if recurrence < min_rec:
        return _known(
            "observable_concentration",
            fired=False,
            strength=0.0,
            reason="recurrence_below_threshold",
            evidence=explicit_evidence_refs(projected.record),
            epistemic="CALCULATION",
            method=method,
            freshness=freshness,
            result={"recurrence": recurrence, "threshold": min_rec},
            limitations=("snapshot_cohort_is_not_a_market",),
        )
    return _known(
        "observable_concentration",
        fired=True,
        strength=min(1.0, 0.30 + 0.10 * recurrence),
        reason="supplier_or_pair_recurrence",
        evidence=explicit_evidence_refs(projected.record),
        angles=("exceptional",),
        peers=("supplier", "organ"),
        epistemic="CALCULATION",
        method=method,
        freshness=freshness,
        result={"recurrence": recurrence},
        limitations=("recurrence_is_not_collusion",),
    )


def detect_peer_difference(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    provided = projected.record.get("peer_group")
    if not isinstance(provided, dict):
        return _empty(
            "peer_difference",
            "peer_group_absent",
            missing=("peer_group",),
            freshness=freshness,
            limitations=("comparable_requires_versioned_interface",),
        )
    schema = text(provided.get("schema"))
    if schema not in PEER_SCHEMAS:
        return _empty(
            "peer_difference",
            "peer_interface_unversioned",
            missing=("peer_group.schema",),
            freshness=freshness,
            limitations=("unversioned_peer_is_refused",),
        )
    status = text(provided.get("status"))
    if status in {"NOT_COMPARABLE", "NO_VALID_PEER_GROUP"}:
        return _known(
            "peer_difference",
            fired=False,
            strength=None,
            reason="NOT_COMPARABLE",
            evidence=explicit_evidence_refs(projected.record),
            epistemic="UNKNOWN",
            method=_method("peer_difference/1.0", "versioned peer interface only"),
            freshness=freshness,
            result={"status": "NOT_COMPARABLE"},
            status="HOLD",
            limitations=("honest_not_comparable",),
            angles=("comparavel",),
        )
    if status == "HOLD_FOR_DATA":
        return _empty(
            "peer_difference",
            "insufficient_peer_sample",
            missing=("peer_group.sample_size",),
            freshness=freshness,
            status="HOLD",
            limitations=("peer_hold_for_data",),
        )
    sample = int(provided.get("sample_size") or 0)
    median_raw = provided.get("median_value")
    if sample < MIN_PEER_SAMPLE or median_raw in (None, ""):
        return _empty(
            "peer_difference",
            "insufficient_peer_sample",
            missing=("peer_group.sample_size",),
            freshness=freshness,
            status="HOLD",
        )
    amount = nominal_amount(projected)
    if amount is None:
        return _empty(
            "peer_difference",
            "missing_nominal_value",
            missing=("nominal_value",),
            freshness=freshness,
        )
    median = Decimal(str(median_raw))
    if median <= 0:
        return _empty(
            "peer_difference",
            "insufficient_peer_sample",
            missing=("peer_group.median_value",),
            freshness=freshness,
        )
    gap = abs(amount - median) / median
    dimensions = tuple(str(item) for item in (provided.get("dimensions") or ("object_family",)))
    method = _method("peer_difference/1.0", "abs(nominal-median)/median on a versioned peer group")
    if gap < _PEER_GAP_RATIO:
        return _known(
            "peer_difference",
            fired=False,
            strength=0.0,
            reason="peer_gap_within_band",
            evidence=explicit_evidence_refs(projected.record),
            peers=dimensions,
            epistemic="CALCULATION",
            method=method,
            freshness=freshness,
            result={"gap": float(gap), "sample_size": sample},
            angles=("comparavel",),
            limitations=("statistical_difference_is_not_an_accusation",),
        )
    return _known(
        "peer_difference",
        fired=True,
        strength=min(1.0, float(gap)),
        reason="peer_gap_outside_band",
        evidence=explicit_evidence_refs(projected.record),
        peers=dimensions,
        angles=("comparavel",),
        epistemic="CALCULATION",
        method=method,
        freshness=freshness,
        result={"gap": float(gap), "sample_size": sample},
        limitations=("statistical_difference_is_not_irregular",),
    )


def detect_identity_swap_is_not_insight(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    return _known(
        "identity_swap_is_not_insight",
        fired=False,
        strength=0.0,
        reason="municipality_or_party_swap_is_not_insight",
        evidence=(),
        epistemic="INFERENCE",
        method=_method("identity_swap_is_not_insight/1.0", "explicit non-event"),
        freshness=_freshness_payload(projected, as_of),
        result={"insight": False},
        limitations=("identity_swap_never_promotes",),
    )


def detect_demand_theme(projected: ProjectedRecord, *, as_of: str) -> DetectorResult:
    freshness = _freshness_payload(projected, as_of)
    hits: list[str] = []
    for name in ("adjustment_anniversary", "adjustment_base", "indices", "value_changes", "amendments"):
        if fact_status(projected, name) == "KNOWN":
            hits.append(name)
    objeto = fact_value(projected, "object")
    blob = str(objeto or "").casefold()
    if any(token in blob for token in ("reajuste", "aditivo", "obra", "engenharia", "bdi", "sinapi", "sicro")):
        hits.append("object_theme")
    if not hits:
        if fact_status(projected, "object") != "KNOWN":
            return _empty("demand_theme", "missing_object", missing=("object",), freshness=freshness)
        return _known(
            "demand_theme",
            fired=False,
            strength=0.0,
            reason="theme_not_observed",
            evidence=explicit_evidence_refs(projected.record),
            epistemic="CALCULATION",
            method=_method("demand_theme/1.0", "thematic tokens and documented technical families"),
            freshness=freshness,
            result={"hits": []},
        )
    return _known(
        "demand_theme",
        fired=True,
        strength=min(1.0, 0.25 + 0.15 * len(hits)),
        reason="technical_analysis_theme_present",
        evidence=explicit_evidence_refs(projected.record),
        angles=("preco_bdi",) if "indices" in hits else (),
        epistemic="CALCULATION",
        method=_method("demand_theme/1.0", "thematic tokens and documented technical families"),
        freshness=freshness,
        result={"hits": hits},
    )


def run_detectors(projected: ProjectedRecord, cohort: CohortIndex, *, as_of: str) -> tuple[DetectorResult, ...]:
    return (
        detect_material_value_change(projected, as_of=as_of),
        detect_material_term_change(projected, as_of=as_of),
        detect_documented_amendment(projected, as_of=as_of),
        detect_documented_apostille(projected, as_of=as_of),
        detect_documented_suspension(projected, as_of=as_of),
        detect_documented_resumption(projected, as_of=as_of),
        detect_documented_rescission(projected, as_of=as_of),
        detect_adjustment_anniversary(projected, as_of=as_of),
        detect_documented_price_index(projected, as_of=as_of),
        detect_unusual_documentary_richness(projected, as_of=as_of),
        detect_observable_concentration(projected, cohort, as_of=as_of),
        detect_peer_difference(projected, as_of=as_of),
        detect_demand_theme(projected, as_of=as_of),
        detect_identity_swap_is_not_insight(projected, as_of=as_of),
    )


def observation_freshness(projected: ProjectedRecord, *, as_of: str) -> tuple[float | None, str]:
    observed = projected.facts.observed_at or text(projected.record.get("observed_at"))
    age = freshness_hours(as_of, observed)
    if age is None:
        return None, "UNKNOWN"
    if age > STALE_MAX_AGE_HOURS:
        return age, "STALE"
    return age, "FRESH"


def parse_cutoff(as_of: str) -> Any:
    return parse_as_of(as_of)
