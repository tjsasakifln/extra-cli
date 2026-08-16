"""Orchestrate fail-closed peer groups for valor integral nominal de pavimentação."""

from __future__ import annotations

from typing import Any

from scripts.contract_comparables.constants import (
    MIN_COVERAGE_COMPARABLE,
    MIN_TYPOLOGY_CONFIDENCE,
    MIN_USABLE_N_COMPARABLE,
    REASON_DUPLICATE_OR_RECTIFICATION,
    REASON_MISSING_VALUE,
    REASON_STATISTICAL_DIFF,
    REASON_UNKNOWN_EXCLUDED,
    STATUS_COMPARABLE,
    UNIT_CANONICAL,
    VALUE_SEMANTIC_CANONICAL,
)
from scripts.contract_comparables.gates import decide_status, focal_gate_reasons, select_peers
from scripts.contract_comparables.metrics import compute_metrics, coverage_ratio, missingness_ratio
from scripts.contract_comparables.models import (
    ContractRecord,
    PeerGroupResult,
    PeerRequest,
    Recorte,
    RectificationEvent,
)
from scripts.contract_comparables.normalize import (
    apply_rectification,
    collapse_revisions,
    record_from_mapping,
    records_from_mappings,
    recorte_from_record,
)
from scripts.contract_comparables.serialize import serialize_result

INCLUSION_RULES = (
    "typology=pavimentacao AND typology_confidence>=0.80",
    "unit=BRL_TOTAL (valor integral nominal; never km or m2)",
    "value_semantic=valor_integral_nominal",
    "regime identical and known",
    "geography=same UF",
    "period=|year_delta|<=1",
    "UNKNOWN valor excluded from denominator",
    "highest revision only",
)

EXCLUSION_RULES = (
    "incompatible unit, typology, scope, regime, geography, period, value semantic",
    "original vs atualizado mix without explicit method",
    "unresolved duplicate or superseded identity",
    "pequeno vs grande porte",
    "text similarity or embeddings as inclusion key",
    "physical unit price without verified quantity/unit/scope/normalization/sample",
)

OUTLIER_TREATMENT = (
    "outliers remain in the sample; IQR 1.5 and MAD robust distance are descriptive; "
    "no legal accusation is emitted"
)

LIMITATIONS_BASE = (
    "Canary answers only the nominal total-value position question for paving contracts.",
    "This is not a physical-unit cost, a productivity benchmark, or a legal accusation.",
    "UNKNOWN is never coerced to zero and never enters the denominator.",
    "Fixture output is never official_live.",
    "No national ranking or complete-universe share claim is licensed by this document.",
)


def _recorte_map(records: tuple[ContractRecord, ...]) -> dict[str, Recorte]:
    return {record.contract_id: recorte_from_record(record) for record in records}


def build_peer_group(
    records: tuple[ContractRecord, ...] | list[dict[str, Any]],
    request: PeerRequest,
) -> tuple[PeerGroupResult, dict[str, Any]]:
    if records and isinstance(records[0], dict):
        typed = records_from_mappings(records)  # type: ignore[arg-type]
    else:
        typed = tuple(records)  # type: ignore[arg-type]
    collapsed, unresolved = collapse_revisions(typed)
    recortes = _recorte_map(collapsed)
    focal = recortes.get(request.focal_contract_id)
    if focal is None:
        dummy = recorte_from_record(
            record_from_mapping(
                {
                    "contract_id": request.focal_contract_id,
                    "objeto": "",
                    "valor": None,
                    "valor_is_unknown": True,
                }
            )
        )
        result = PeerGroupResult(
            status="NOT_COMPARABLE",
            reason_codes=("target_not_found",),
            focal=dummy,
            peers=(),
            exclusions=(),
            total_n=0,
            eligible_n=0,
            usable_n=0,
            coverage=0.0,
            missingness=1.0,
            metrics=None,
            limitations=LIMITATIONS_BASE,
            inclusion_rules=INCLUSION_RULES,
            exclusion_rules=EXCLUSION_RULES,
            outlier_treatment=OUTLIER_TREATMENT,
            request=request,
        )
        return result, serialize_result(result)

    candidates = tuple(item for item in recortes.values() if item.contract.contract_id != focal.contract.contract_id)
    total_n = len(candidates)
    selected, exclusions, eligible = select_peers(focal, tuple(recortes.values()), request)
    usable_n = len(selected)
    eligible_n = len(eligible)
    coverage = coverage_ratio(usable_n, total_n)
    missingness = missingness_ratio(usable_n, eligible_n)
    focal_reasons = list(focal_gate_reasons(focal, request))
    group_reasons: list[str] = []
    if unresolved:
        group_reasons.append(REASON_DUPLICATE_OR_RECTIFICATION)
    if any(REASON_MISSING_VALUE in item.reason_codes for item in exclusions):
        group_reasons.append(REASON_UNKNOWN_EXCLUDED)
    if usable_n == 0:
        for item in exclusions:
            group_reasons.extend(item.reason_codes)
    status, reason_codes = decide_status(
        focal_reasons=tuple(focal_reasons),
        group_reasons=tuple(group_reasons),
        usable_n=usable_n,
        coverage=coverage,
        unresolved_duplicates=unresolved,
    )
    metrics = None
    extra_limitations = list(LIMITATIONS_BASE)
    if status == STATUS_COMPARABLE:
        if focal.contract.valor is None:
            raise RuntimeError("COMPARABLE requires a known focal valor")
        metrics = compute_metrics(
            focal_value=focal.contract.valor,
            peers=selected,
            eligible_n=eligible_n,
            total_n=total_n,
        )
        if metrics.outlier_flag:
            extra_limitations.append(
                "Focal value is a statistical difference versus the sample (IQR/MAD). "
                "No legal accusation follows from that distance."
            )
            reason_codes = tuple(dict.fromkeys((*reason_codes, REASON_STATISTICAL_DIFF)))
        extra_limitations.append(
            f"Metrics emitted only after gates: usable_n>={MIN_USABLE_N_COMPARABLE}, "
            f"coverage>={MIN_COVERAGE_COMPARABLE}, typology_confidence>={MIN_TYPOLOGY_CONFIDENCE}, "
            f"unit={UNIT_CANONICAL}, semantic={VALUE_SEMANTIC_CANONICAL}."
        )
    else:
        extra_limitations.append("Metrics withheld because the peer-group gate did not pass.")
    result = PeerGroupResult(
        status=status,
        reason_codes=reason_codes,
        focal=focal,
        peers=selected,
        exclusions=exclusions,
        total_n=total_n,
        eligible_n=eligible_n,
        usable_n=usable_n if status == STATUS_COMPARABLE else usable_n,
        coverage=coverage,
        missingness=missingness,
        metrics=metrics,
        limitations=tuple(extra_limitations),
        inclusion_rules=INCLUSION_RULES,
        exclusion_rules=EXCLUSION_RULES,
        outlier_treatment=OUTLIER_TREATMENT,
        request=request,
    )
    return result, serialize_result(result)


def build_document(
    records: tuple[ContractRecord, ...] | list[dict[str, Any]],
    request: PeerRequest,
) -> dict[str, Any]:
    _result, document = build_peer_group(records, request)
    return document


def rebuild_after_rectification(
    records: tuple[ContractRecord, ...] | list[dict[str, Any]],
    requests: tuple[PeerRequest, ...],
    event: RectificationEvent,
) -> dict[str, dict[str, Any]]:
    if records and isinstance(records[0], dict):
        typed = records_from_mappings(records)  # type: ignore[arg-type]
    else:
        typed = tuple(records)  # type: ignore[arg-type]
    before = {item.focal_contract_id: build_document(typed, item) for item in requests}
    after_records = apply_rectification(typed, event)
    after = {item.focal_contract_id: build_document(after_records, item) for item in requests}
    return {"before": before, "after": after, "rectified_contract_id": event.contract_id}


def groups_changed_by_rectification(
    records: tuple[ContractRecord, ...] | list[dict[str, Any]],
    requests: tuple[PeerRequest, ...],
    event: RectificationEvent,
) -> tuple[str, ...]:
    payload = rebuild_after_rectification(records, requests, event)
    changed: list[str] = []
    for focal_id, before in payload["before"].items():
        after = payload["after"][focal_id]
        if before["content_hash"] != after["content_hash"]:
            changed.append(focal_id)
    return tuple(sorted(changed))
