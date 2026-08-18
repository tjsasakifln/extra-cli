"""Field coverage matrix and HOLD_FOR_DATA reasons. Absence is never a negative fact."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from scripts.official_contract_semantics.constants import (
    COVERAGE_FIELDS,
    EPISTEMIC_NOT_APPLICABLE,
    REASON_FIELDS_UNAVAILABLE,
    REASON_HOLD_FOR_DATA,
)
from scripts.official_contract_semantics.models import OfficialContractObservation


def field_known(item: OfficialContractObservation, name: str) -> bool:
    value = getattr(item, name)
    return value not in {None, "", "unknown"}


def field_epistemic(item: OfficialContractObservation, name: str) -> str:
    mapped = (item.field_epistemics or {}).get(name)
    if mapped:
        return str(mapped)
    return "FACT_OFFICIAL" if field_known(item, name) else "UNKNOWN"


def field_resolved(item: OfficialContractObservation, name: str) -> bool:
    if field_epistemic(item, name) == EPISTEMIC_NOT_APPLICABLE:
        return True
    return field_known(item, name)


def coverage_matrix(observations: Iterable[OfficialContractObservation]) -> dict[str, object]:
    items = list(observations)
    counts: dict[str, dict[str, int]] = {}
    for name in COVERAGE_FIELDS:
        known = sum(1 for item in items if field_known(item, name))
        not_applicable = sum(1 for item in items if field_epistemic(item, name) == EPISTEMIC_NOT_APPLICABLE)
        counts[name] = {
            "known": known,
            "unknown": len(items) - known - not_applicable,
            "not_applicable": not_applicable,
            "coverage": round(known / len(items), 4) if items else 0.0,
        }
    statuses = Counter(item.status for item in items)
    return {
        "observation_count": len(items),
        "by_status": dict(sorted(statuses.items())),
        "fields": counts,
    }


def hold_reasons_for(item: OfficialContractObservation) -> list[str]:
    reasons: list[str] = []
    if item.status == "conflicted":
        reasons.append("official_conflict_preserved")
    if item.status == "unknown":
        reasons.append("observation_status_unknown")
    for name in (
        "unit",
        "quantity",
        "execution_regime",
        "procurement_modality",
        "value_semantic",
        "period_start",
        "period_end",
    ):
        if not field_resolved(item, name):
            reasons.append(f"missing_{name}")
    if not field_resolved(item, "value_amount"):
        reasons.append("missing_value_amount")
    if not reasons:
        return []
    return [REASON_HOLD_FOR_DATA, REASON_FIELDS_UNAVAILABLE, *reasons]


def contract_hold_report(observations: Iterable[OfficialContractObservation]) -> list[dict[str, object]]:
    grouped: dict[str, list[OfficialContractObservation]] = {}
    for item in observations:
        key = item.contract_identifier or item.observation_id
        grouped.setdefault(key, []).append(item)
    report: list[dict[str, object]] = []
    for contract_id, members in sorted(grouped.items()):
        live = [item for item in members if item.status != "superseded_by_official_evidence"]
        conflicted = [item for item in live if item.status == "conflicted"]
        reasons: list[str] = []
        if conflicted:
            reasons.append("official_conflict_preserved")
        known_union = {name: any(field_resolved(item, name) for item in live) for name in COVERAGE_FIELDS}
        for name, known in known_union.items():
            if not known:
                reasons.append(f"missing_{name}")
        if any(item.status == "conflicted" for item in live):
            eligible = False
        else:
            required = (
                "unit",
                "execution_regime",
                "procurement_modality",
                "value_semantic",
                "period_start",
                "value_amount",
            )
            eligible = all(known_union.get(name) for name in required)
        report.append(
            {
                "contract_identifier": contract_id,
                "observation_ids": [item.observation_id for item in members],
                "hold": not eligible,
                "technically_eligible_for_engine": eligible,
                "reason_codes": reasons if not eligible else [],
                "field_known": known_union,
            }
        )
    return report
