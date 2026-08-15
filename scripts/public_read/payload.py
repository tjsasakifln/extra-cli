"""Load a research fixture into the shipped payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_read.models import (
    FreshnessSpec,
    PartitionSpec,
    ResearchPayload,
    SeriesRow,
    UniverseSpec,
    parse_decimal,
)


def load_research_payload(path: str | Path) -> ResearchPayload:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload_from_mapping(raw)


def payload_from_mapping(raw: dict[str, Any]) -> ResearchPayload:
    universe = raw["universe"]
    freshness = raw["freshness"]
    rows = []
    for item in raw["series_rows"]:
        rows.append(
            SeriesRow(
                process_key=str(item["process_key"]),
                uf=str(item["uf"]),
                archetype_id=str(item["archetype_id"]),
                contract_value_brl=parse_decimal(item.get("contract_value_brl")),
                source_id=str(item["source_id"]),
                source_record_id=str(item["source_record_id"]),
                observed_at=str(item["observed_at"]),
                lineage=tuple(str(part) for part in item.get("lineage", ())),
                value_status=str(item.get("value_status") or "KNOWN"),
                lineage_resolution=item.get("lineage_resolution"),
            )
        )
    return ResearchPayload(
        fixture_id=str(raw["fixture_id"]),
        as_of=str(raw["as_of"]),
        competence=str(raw.get("competence") or universe["competence"]),
        universe=UniverseSpec(
            source=str(universe["source"]),
            competence=str(universe["competence"]),
            cutoff=str(universe["cutoff"]),
            method=str(universe["method"]),
            orgs=tuple(dict(org) for org in universe["orgs"]),
        ),
        partitions=tuple(
            PartitionSpec(
                partition_id=str(part["partition_id"]),
                status=str(part["status"]),
                evidence=part.get("evidence"),
            )
            for part in raw["partitions"]
        ),
        freshness=FreshnessSpec(
            publication_age_hours=float(freshness["publication_age_hours"]),
            publication_lag_p99_hours=float(freshness["publication_lag_p99_hours"]),
        ),
        rows=tuple(rows),
        use_extra_1093_as_denominator=bool(raw.get("use_extra_1093_as_denominator", False)),
        denominator_kind=str(raw.get("denominator_kind") or "publishing_org"),
        claimed_geography=raw.get("claimed_geography"),
        consumer_errors=tuple(str(code) for code in raw.get("consumer_errors", ())),
    )
