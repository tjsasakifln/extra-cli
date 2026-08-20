"""Versioned national-coverage contract types.

This tree is the coverage denominator + stock reconciliation + consumer facts.
It does not replace the six-state ``national_claims`` arbiter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "national-coverage/1.0"
METHOD_VERSION = "national-coverage-v1"
CORE_METHOD_VERSION = "pncp-orgaos-publicantes-v1"
OFFICIAL_SOURCE_PNCP = "pncp"
OFFICIAL_SOURCE_URL_PNCP = "https://pncp.gov.br/api/pncp/v1/orgaos"
DEFAULT_OWNER = "contracts-truth"
DEFAULT_NEXT_REFRESH = "weekly"
DEFAULT_GRAIN = "publishing_org"
DEFAULT_FRESHNESS_WINDOW_HOURS = 48.0
MAX_INMEMORY_CONTRACT_ROWS = 50_000

VerdictToken = Literal["NATIONAL_CLAIM_AUTHORIZED", "PARTIAL", "NOT_MEASURED", "BLOCKED"]
PartitionStatus = Literal["FOUND", "ZERO_CONFIRMED", "BLOCKED", "FAILED", "NOT_APPLICABLE"]
UniverseKind = Literal["OFFICIAL", "OBSERVED_CORPUS"]
OfficialStatus = Literal["AVAILABLE", "BLOCKED"]
MappingStatus = Literal["MAPPED", "UNMAPPED", "DUPLICATE", "CONFLICT", "ALIAS"]

VERDICT_TOKENS: frozenset[str] = frozenset({"NATIONAL_CLAIM_AUTHORIZED", "PARTIAL", "NOT_MEASURED", "BLOCKED"})
CLOSED_PARTITION_STATUSES: frozenset[str] = frozenset({"FOUND", "ZERO_CONFIRMED"})
NATIONAL_GEOGRAPHIES: frozenset[str] = frozenset({"BR", "BRASIL", "BRAZIL", "NATIONAL", "NACIONAL"})
FORBIDDEN_NATIONAL_SOURCES: frozenset[str] = frozenset(
    {
        "extra_1093",
        "extra-1093",
        "extra_1093_monitored",
        "extra-canonical-seed",
        "sc_public_entities.raio_200km",
        "icp_commercial",
        "observed_corpus",
        "raw_national",
        "row_count",
    }
)
NATIONAL_INCLUSION = (
    "official_publishing_org_catalog",
    "competence_window",
    "cutoff_inclusive",
)
NATIONAL_EXCLUSION = (
    "extra_1093_monitored_entes",
    "icp_commercial_universe",
    "observed_corpus_at_snapshot",
    "row_count_as_completeness",
    "unconsulted_as_zero",
)
OBSERVED_INCLUSION = ("observed_corpus_publishers_at_snapshot",)
OBSERVED_EXCLUSION = (
    "national_claim_authorization",
    "extra_1093_as_national",
    "unobserved_as_zero",
)


class NationalCoverageError(ValueError):
    """Coverage denominator or verdict cannot be materialized."""


@dataclass(frozen=True)
class PublishingOrg:
    org_id: str
    name: str
    unit_count: int = 1
    uf: str | None = None
    esfera: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class PartitionState:
    partition_id: str
    status: PartitionStatus
    expected: bool
    queried: bool
    evidence_ref: str | None = None
    reason: str | None = None
    uf: str | None = None


@dataclass(frozen=True)
class VersionedUniverse:
    national_universe_id: str
    schema_version: str
    method_version: str
    core_method_version: str
    universe_kind: UniverseKind
    official_source: str
    official_source_url: str | None
    competence: str
    cutoff: str
    retrieved_at: str
    as_of: str
    raw_hash: str
    catalog_hash: str
    inclusion_rules: tuple[str, ...]
    exclusion_rules: tuple[str, ...]
    grain: str
    expected_orgs: tuple[PublishingOrg, ...]
    expected_partitions: int
    expected_units: int
    owner: str
    next_refresh: str
    official_status: OfficialStatus
    official_block_cause: str | None
    core_universe_id: str | None = None
    labeled_observed_corpus: bool = False


@dataclass(frozen=True)
class CorpusPublisher:
    raw_org_id: str
    contract_count: int
    uf: str | None = None
    esfera: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorpusSnapshot:
    snapshot_id: str
    snapshot_hash: str
    as_of: str
    source: str
    publisher_count: int
    contract_count: int
    publishers: tuple[CorpusPublisher, ...]
    relation: str = "pncp_supplier_contracts_aggregate"


@dataclass(frozen=True)
class MappedPublisher:
    raw_org_id: str
    canonical_org_id: str | None
    status: MappingStatus
    contract_count: int
    uf: str | None = None
    last_seen: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class MappingStats:
    mapped: int
    unmapped: int
    duplicate: int
    conflict: int
    alias: int
    unresolved_identities: int
    records: tuple[MappedPublisher, ...]


@dataclass(frozen=True)
class StockCoverage:
    expected: int
    observed_found: int
    unobserved: int


@dataclass(frozen=True)
class FreshnessCoverage:
    window_hours: float
    as_of: str
    fresh_found: int
    stale_found: int
    unknown_freshness: int


@dataclass(frozen=True)
class CoverageRequest:
    geography: str
    period: str
    source: str
    grain: str


@dataclass(frozen=True)
class ConsultedPartitions:
    found: frozenset[str] = field(default_factory=frozenset)
    zero_confirmed: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    blocked: dict[str, str] = field(default_factory=dict)
    queried: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class CoverageRecord:
    schema_version: str
    universe: VersionedUniverse
    partitions: tuple[PartitionState, ...]
    expected_count: int
    queried_count: int
    closed_count: int
    by_status: dict[str, int]
    corpus: CorpusSnapshot | None
    mapping: MappingStats
    stock: StockCoverage
    freshness: FreshnessCoverage
    verdict: VerdictToken
    national_claim_authorized: bool
    reason_codes: tuple[str, ...]
    request: CoverageRequest
    content_hash: str


def org_to_dict(org: PublishingOrg) -> dict[str, Any]:
    return {
        "org_id": org.org_id,
        "name": org.name,
        "unit_count": org.unit_count,
        "uf": org.uf,
        "esfera": org.esfera,
        "aliases": list(org.aliases),
    }


def partition_to_dict(state: PartitionState) -> dict[str, Any]:
    return {
        "partition_id": state.partition_id,
        "status": state.status,
        "expected": state.expected,
        "queried": state.queried,
        "evidence_ref": state.evidence_ref,
        "reason": state.reason,
        "uf": state.uf,
    }


def is_national_geography(geography: str) -> bool:
    return geography.strip().upper() in NATIONAL_GEOGRAPHIES
