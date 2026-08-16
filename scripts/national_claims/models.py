"""Versioned national-claims contract types.

This module is the small surface Goals 01–03 may import or simulate by
fixture. Candidate / comparables / read-model engines stay out of this tree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CONTRACT_VERSION = "national-claims/1.0"
POLICY_VERSION = "national-claims-gate/1.0"
METHOD_VERSION = "pncp-orgaos-publicantes-v1"
LKG_DEFAULT_TTL_HOURS = 48

AuthorizationState = Literal[
    "AUTHORIZED",
    "AUTHORIZED_WITH_LIMITATIONS",
    "NEEDS_DATA",
    "STALE",
    "BLOCKED",
    "FAILED",
]
ConsumerView = Literal["current", "lkg", "blocked"]
ClaimScope = Literal["national", "geo_limited", "period_limited", "geo_period_limited"]
UniverseKind = Literal[
    "national",
    "icp_commercial",
    "extra_1093_monitored",
    "observed_corpus",
]
PartitionStatus = Literal[
    "FOUND",
    "ZERO_CONFIRMED",
    "BLOCKED",
    "FAILED",
    "NOT_APPLICABLE",
    "UNKNOWN",
]
IdentityClass = Literal["IDENTITY_MAPPED", "SOURCE_WIDE_AGGREGATE", "UNMAPPABLE"]

AUTHORIZATION_STATES: frozenset[str] = frozenset(
    {
        "AUTHORIZED",
        "AUTHORIZED_WITH_LIMITATIONS",
        "NEEDS_DATA",
        "STALE",
        "BLOCKED",
        "FAILED",
    }
)
NATIONAL_SCOPES: frozenset[str] = frozenset({"national"})
LIMITED_SCOPES: frozenset[str] = frozenset({"geo_limited", "period_limited", "geo_period_limited"})
CLOSED_PARTITION_STATUSES: frozenset[str] = frozenset({"FOUND", "ZERO_CONFIRMED"})
FORBIDDEN_NATIONAL_DENOMINATORS: frozenset[str] = frozenset(
    {
        "icp_commercial",
        "extra_1093_monitored",
        "extra_commercial_1093",
        "observed_corpus",
        "row_count",
        "any_row",
        "entity_coverage.is_covered",
    }
)


@dataclass(frozen=True)
class OrgSpec:
    org_id: str
    name: str
    unit_count: int = 1
    geography: str | None = None


@dataclass(frozen=True)
class VersionedUniverse:
    universe_id: str
    universe_kind: UniverseKind
    official_source: str
    cutoff: str
    competence: str
    catalog_hash: str
    method_version: str
    expected_orgs: tuple[OrgSpec, ...]
    expected_units: int
    expected_partitions: int
    inclusion_rules: tuple[str, ...]
    exclusion_rules: tuple[str, ...]
    version_changes: tuple[str, ...]
    owner: str
    review_cadence: str

    @property
    def national_universe_id(self) -> str | None:
        if self.universe_kind != "national":
            return None
        return self.universe_id


@dataclass(frozen=True)
class UniverseBundle:
    """Four distinct universes. None may substitute another."""

    national: VersionedUniverse
    icp_commercial: VersionedUniverse
    extra_1093_monitored: VersionedUniverse
    observed_corpus: VersionedUniverse

    def by_kind(self, kind: str) -> VersionedUniverse:
        mapping = {
            "national": self.national,
            "icp_commercial": self.icp_commercial,
            "extra_1093_monitored": self.extra_1093_monitored,
            "observed_corpus": self.observed_corpus,
        }
        if kind not in mapping:
            raise KeyError(kind)
        return mapping[kind]


@dataclass(frozen=True)
class PartitionRecord:
    partition_id: str
    expected: bool
    attempted: bool
    status: PartitionStatus
    pages_fetched: int | None = None
    pages_expected: int | None = None
    records: int | None = None
    pagination_complete: bool = False
    request_complete: bool = False
    raw_ref: str | None = None
    evidence_ref: str | None = None
    checked_at: str | None = None
    as_of: str | None = None
    freshness_status: str | None = None
    identity_mapped: bool = False
    reason: str | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class EvidenceRow:
    source: str
    entity_id: str | None = None
    canonical_entity_key: str | None = None
    data_type: str | None = None
    state: str | None = None
    count_obtained: int | None = None
    count_persisted: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_ref: str | None = None
    evidence_ref: str | None = None
    partition_id: str | None = None


@dataclass(frozen=True)
class FreshnessInput:
    age_hours: float
    lag_p99_hours: float
    as_of: str
    layer: str = "publication"


@dataclass(frozen=True)
class LkgRecord:
    claim_id: str
    authorization_state: str
    national_universe_id: str
    catalog_hash: str
    method_version: str
    source_version: str
    content_hash: str
    authorized_at: str
    expires_at: str
    invalidated_at: str | None = None
    invalidation_reason: str | None = None


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    scope: ClaimScope
    period: str
    sources: tuple[str, ...]
    typology: str | None
    geography: str
    snapshot: str
    cutoff: str
    policy_version: str
    denominator_kind: str
    infer_completeness_from_row_count: bool = False


@dataclass(frozen=True)
class ClaimRequest:
    claim: ClaimSpec
    universes: UniverseBundle
    partitions: tuple[PartitionRecord, ...]
    evidence: tuple[EvidenceRow, ...]
    freshness: FreshnessInput
    prior_lkg: LkgRecord | None = None
    source_version: str = "pncp/1.0"
    producer_sha: str = "fixture"


@dataclass(frozen=True)
class IdentitySplit:
    mapped: tuple[EvidenceRow, ...]
    source_wide: tuple[EvidenceRow, ...]
    unmappable: tuple[EvidenceRow, ...]

    @property
    def mapped_count(self) -> int:
        return len(self.mapped)

    @property
    def source_wide_count(self) -> int:
        return len(self.source_wide)

    @property
    def unmappable_count(self) -> int:
        return len(self.unmappable)


@dataclass(frozen=True)
class PartitionReconciliation:
    expected: int
    attempted: int
    closed: int
    by_status: dict[str, int]
    records: tuple[PartitionRecord, ...]
    blockers: tuple[str, ...]
    next_actions: tuple[str, ...]


def org_to_dict(org: OrgSpec) -> dict[str, Any]:
    return asdict(org)


def universe_to_dict(universe: VersionedUniverse) -> dict[str, Any]:
    payload = asdict(universe)
    payload["expected_orgs"] = [org_to_dict(org) for org in universe.expected_orgs]
    payload["national_universe_id"] = universe.national_universe_id
    return payload


def partition_to_dict(record: PartitionRecord) -> dict[str, Any]:
    return asdict(record)


def evidence_to_dict(row: EvidenceRow) -> dict[str, Any]:
    return asdict(row)
