"""Immutable payloads for the research-flagship export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def parse_datetime(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


@dataclass(frozen=True)
class UniverseSpec:
    source: str
    competence: str
    cutoff: str
    method: str
    orgs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PartitionSpec:
    partition_id: str
    status: str
    evidence: str | None = None


@dataclass(frozen=True)
class FreshnessSpec:
    publication_age_hours: float
    publication_lag_p99_hours: float

    @property
    def age(self) -> timedelta:
        return timedelta(hours=self.publication_age_hours)

    @property
    def lag_p99(self) -> timedelta:
        return timedelta(hours=self.publication_lag_p99_hours)


@dataclass(frozen=True)
class SeriesRow:
    process_key: str
    uf: str
    archetype_id: str
    contract_value_brl: Decimal | None
    source_id: str
    source_record_id: str
    observed_at: str
    lineage: tuple[str, ...]
    value_status: str
    lineage_resolution: str | None = None


@dataclass(frozen=True)
class ResearchPayload:
    fixture_id: str
    as_of: str
    competence: str
    universe: UniverseSpec
    partitions: tuple[PartitionSpec, ...]
    freshness: FreshnessSpec
    rows: tuple[SeriesRow, ...]
    use_extra_1093_as_denominator: bool = False
    denominator_kind: str = "publishing_org"
    claimed_geography: str | None = None
    consumer_errors: tuple[str, ...] = ()
