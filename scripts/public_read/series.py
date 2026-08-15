"""Deterministic source-agnostic research series."""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import Any

from scripts.public_read.claim_gate import ClaimDecision
from scripts.public_read.models import ResearchPayload, SeriesRow

GEO_UF = "UF"
GEO_BR = "BR"


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _percentile(values: tuple[Decimal, ...], percent: int) -> Decimal | None:
    if not values:
        return None
    ordered = tuple(sorted(values))
    index = math.ceil(percent / 100 * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _cell(
    *,
    competence: str,
    geography_kind: str,
    geography_code: str,
    archetype_id: str,
    members: tuple[SeriesRow, ...],
    as_of: str,
    completeness: str,
    extra_reasons: tuple[str, ...],
) -> dict[str, Any]:
    unknown = any(row.value_status == "UNKNOWN" or row.contract_value_brl is None for row in members)
    known = tuple(row.contract_value_brl for row in members if row.contract_value_brl is not None)
    reasons = list(extra_reasons)
    if unknown:
        reasons.append("unknown_values")
    value_status = "UNKNOWN" if unknown else "KNOWN"
    cell_completeness = "UNKNOWN" if unknown else completeness
    lineage = sorted({item for row in members for item in row.lineage})
    sources = sorted({(row.source_id, row.source_record_id) for row in members})
    return {
        "series_key": "|".join((competence, geography_kind, geography_code, archetype_id)),
        "competence": competence,
        "geography_kind": geography_kind,
        "geography_code": geography_code,
        "archetype_id": archetype_id,
        "contract_count": len(members),
        "total_value_brl": None if unknown else _decimal_text(sum(known, Decimal("0"))),
        "ticket_p25_brl": None if unknown else _decimal_text(_percentile(known, 25)),
        "ticket_median_brl": None if unknown else _decimal_text(_percentile(known, 50)),
        "ticket_p75_brl": None if unknown else _decimal_text(_percentile(known, 75)),
        "value_status": value_status,
        "as_of": as_of,
        "completeness": cell_completeness,
        "reason_codes": sorted(set(reasons)),
        "provenance": {
            "source_records": [
                {"source_id": source_id, "source_record_id": record_id} for source_id, record_id in sources
            ],
            "lineage": lineage,
        },
    }


def project_series(payload: ResearchPayload, claim: ClaimDecision) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[SeriesRow]] = defaultdict(list)
    for row in payload.rows:
        grouped[(row.uf, row.archetype_id)].append(row)

    completeness = "COMPLETE" if claim.national_claim_allowed else "INCOMPLETE"
    extra = claim.reason_codes
    cells: list[dict[str, Any]] = []
    for (uf, archetype_id), members in grouped.items():
        cells.append(
            _cell(
                competence=payload.competence,
                geography_kind=GEO_UF,
                geography_code=uf,
                archetype_id=archetype_id,
                members=tuple(members),
                as_of=payload.as_of,
                completeness=completeness,
                extra_reasons=extra,
            )
        )

    if claim.national_claim_allowed:
        by_archetype: dict[str, list[SeriesRow]] = defaultdict(list)
        for row in payload.rows:
            by_archetype[row.archetype_id].append(row)
        for archetype_id, members in by_archetype.items():
            cells.append(
                _cell(
                    competence=payload.competence,
                    geography_kind=GEO_BR,
                    geography_code=GEO_BR,
                    archetype_id=archetype_id,
                    members=tuple(members),
                    as_of=payload.as_of,
                    completeness="COMPLETE",
                    extra_reasons=(),
                )
            )

    return sorted(
        cells,
        key=lambda cell: (
            cell["competence"],
            cell["geography_kind"],
            cell["geography_code"],
            cell["archetype_id"],
        ),
    )
