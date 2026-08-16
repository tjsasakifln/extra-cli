"""#350 identity split for the national-claims arbiter.

Source-wide / aggregated evidence is kept in a separate bucket. It is never
silently dropped and never used to prove entity or dual coverage.
Unmappable identity stays fail-closed with a reason code.
"""

from __future__ import annotations

from typing import Any

from scripts.coverage.covered_entity import (
    IDENTITY_MAPPED,
    UNMAPPABLE,
    classify_evidence_identity,
    dual_coverage_evidence_gate,
)
from scripts.national_claims.models import EvidenceRow, IdentitySplit


def classify_row(row: EvidenceRow) -> str:
    return classify_evidence_identity(
        entity_id=row.entity_id,
        canonical_entity_key=row.canonical_entity_key,
        metadata=row.metadata,
    )


def split_evidence(rows: tuple[EvidenceRow, ...]) -> IdentitySplit:
    mapped: list[EvidenceRow] = []
    source_wide: list[EvidenceRow] = []
    unmappable: list[EvidenceRow] = []
    for row in rows:
        kind = classify_row(row)
        if kind == IDENTITY_MAPPED:
            mapped.append(row)
        elif kind == UNMAPPABLE:
            unmappable.append(row)
        else:
            source_wide.append(row)
    return IdentitySplit(
        mapped=tuple(mapped),
        source_wide=tuple(source_wide),
        unmappable=tuple(unmappable),
    )


def dual_coverage_from_rows(rows: tuple[EvidenceRow, ...]) -> dict[str, Any]:
    """Reuse the #350 gate. Aggregates never enter the numerator."""
    payload = [
        {
            "entity_id": row.entity_id,
            "canonical_entity_key": row.canonical_entity_key,
            "source": row.source,
            "data_type": row.data_type,
            "state": row.state,
            "count_obtained": row.count_obtained,
            "count_persisted": row.count_persisted,
            "metadata": row.metadata,
        }
        for row in rows
    ]
    return dual_coverage_evidence_gate(payload)


def identity_reason_codes(split: IdentitySplit, *, dual_gate: dict[str, Any]) -> tuple[str, ...]:
    codes: list[str] = []
    if split.unmappable:
        codes.append("unmappable_evidence_cannot_drop")
    if split.source_wide and not split.mapped:
        codes.append("source_wide_aggregate_without_identity")
    if split.source_wide:
        codes.append("aggregated_evidence_not_entity_coverage")
    if dual_gate.get("measurement_success") is False:
        reason = str(dual_gate.get("reason") or "missing_evidence")
        if reason not in codes:
            codes.append(reason)
    return tuple(codes)


def identity_report(split: IdentitySplit) -> dict[str, Any]:
    return {
        "mapped": split.mapped_count,
        "source_wide": split.source_wide_count,
        "unmappable": split.unmappable_count,
        "source_wide_kept": True,
        "proves_entity_coverage": False if split.source_wide and not split.mapped else split.mapped_count > 0,
        "proves_dual_coverage": False,
        "aggregate_relation": "national_claims_aggregate_evidence",
        "identity_relation": "national_claims_identity_evidence",
    }
