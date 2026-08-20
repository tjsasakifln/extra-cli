"""Versioned national universe construction.

Official catalogs reuse #302 ``build_universe`` for catalog hash / core id.
When the official enumerator is unavailable, the official denominator is
``BLOCKED`` with a cause and an ``OBSERVED_CORPUS`` companion is emitted.
Observed corpus is never sold as the official national denominator.
"""

from __future__ import annotations

from scripts.national_contract_truth.national_universe import (
    PublishingOrg as CoreOrg,
)
from scripts.national_contract_truth.national_universe import (
    build_universe,
)
from scripts.national_coverage.hashing import digest
from scripts.national_coverage.models import (
    CORE_METHOD_VERSION,
    DEFAULT_GRAIN,
    DEFAULT_NEXT_REFRESH,
    DEFAULT_OWNER,
    METHOD_VERSION,
    NATIONAL_EXCLUSION,
    NATIONAL_INCLUSION,
    OBSERVED_EXCLUSION,
    OBSERVED_INCLUSION,
    OFFICIAL_SOURCE_PNCP,
    OFFICIAL_SOURCE_URL_PNCP,
    SCHEMA_VERSION,
    NationalCoverageError,
    PublishingOrg,
    UniverseKind,
    VersionedUniverse,
    org_to_dict,
)
from scripts.national_coverage.policy import assert_not_extra_1093


def _core_orgs(
    orgs: tuple[PublishingOrg, ...],
    *,
    source: str,
    competence: str,
) -> tuple[CoreOrg, ...]:
    return tuple(
        CoreOrg(
            org_id=org.org_id,
            source=source,
            competence=competence,
            name=org.name,
            unit_count=org.unit_count,
        )
        for org in orgs
    )


def _coverage_universe_id(
    *,
    prefix: str,
    source: str,
    competence: str,
    cutoff: str,
    method_version: str,
    schema_version: str,
    universe_kind: UniverseKind,
    catalog_hash: str,
    grain: str,
    inclusion_rules: tuple[str, ...],
    exclusion_rules: tuple[str, ...],
) -> str:
    seed = {
        "source": source,
        "competence": competence,
        "cutoff": cutoff,
        "method_version": method_version,
        "schema_version": schema_version,
        "universe_kind": universe_kind,
        "catalog_hash": catalog_hash,
        "grain": grain,
        "inclusion_rules": list(inclusion_rules),
        "exclusion_rules": list(exclusion_rules),
    }
    return f"{prefix}-{source}-{competence}-{digest(seed)[:16]}"


def build_official_universe(
    *,
    source: str,
    source_url: str | None,
    competence: str,
    cutoff: str,
    as_of: str,
    raw_hash: str,
    orgs: tuple[PublishingOrg, ...],
    retrieved_at: str | None = None,
    method_version: str = CORE_METHOD_VERSION,
    coverage_method_version: str = METHOD_VERSION,
    grain: str = DEFAULT_GRAIN,
    inclusion_rules: tuple[str, ...] = NATIONAL_INCLUSION,
    exclusion_rules: tuple[str, ...] = NATIONAL_EXCLUSION,
    owner: str = DEFAULT_OWNER,
    next_refresh: str = DEFAULT_NEXT_REFRESH,
) -> VersionedUniverse:
    if not source or not competence or not cutoff or not raw_hash or not method_version:
        raise NationalCoverageError("source, competence, cutoff, raw_hash and method_version are required")
    if not orgs:
        raise NationalCoverageError("official universe has zero publishing orgs")
    assert_not_extra_1093(source=source, orgs=orgs, universe_kind="OFFICIAL")
    core = build_universe(
        source=source,
        competence=competence,
        cutoff=cutoff,
        orgs=_core_orgs(orgs, source=source, competence=competence),
        method=method_version,
    )
    universe_id = _coverage_universe_id(
        prefix="ncv",
        source=source,
        competence=competence,
        cutoff=cutoff,
        method_version=coverage_method_version,
        schema_version=SCHEMA_VERSION,
        universe_kind="OFFICIAL",
        catalog_hash=core.catalog_hash,
        grain=grain,
        inclusion_rules=inclusion_rules,
        exclusion_rules=exclusion_rules,
    )
    return VersionedUniverse(
        national_universe_id=universe_id,
        schema_version=SCHEMA_VERSION,
        method_version=coverage_method_version,
        core_method_version=method_version,
        universe_kind="OFFICIAL",
        official_source=source,
        official_source_url=source_url or OFFICIAL_SOURCE_URL_PNCP,
        competence=competence,
        cutoff=cutoff,
        retrieved_at=retrieved_at or as_of,
        as_of=as_of,
        raw_hash=raw_hash,
        catalog_hash=core.catalog_hash,
        inclusion_rules=inclusion_rules,
        exclusion_rules=exclusion_rules,
        grain=grain,
        expected_orgs=orgs,
        expected_partitions=core.org_count,
        expected_units=core.unit_count,
        owner=owner,
        next_refresh=next_refresh,
        official_status="AVAILABLE",
        official_block_cause=None,
        core_universe_id=core.national_universe_id,
        labeled_observed_corpus=False,
    )


def build_observed_corpus_universe(
    *,
    source: str,
    competence: str,
    cutoff: str,
    as_of: str,
    raw_hash: str,
    orgs: tuple[PublishingOrg, ...],
    official_block_cause: str,
    retrieved_at: str | None = None,
    grain: str = DEFAULT_GRAIN,
    owner: str = DEFAULT_OWNER,
    next_refresh: str = DEFAULT_NEXT_REFRESH,
) -> VersionedUniverse:
    """Partial denominator from the observed corpus. Cannot authorize a national claim."""
    if not source or not competence or not cutoff or not raw_hash:
        raise NationalCoverageError("source, competence, cutoff and raw_hash are required")
    catalog_seed = {
        "universe_kind": "OBSERVED_CORPUS",
        "source": source,
        "competence": competence,
        "cutoff": cutoff,
        "orgs": [org_to_dict(org) for org in orgs],
    }
    catalog_hash = digest(catalog_seed)
    universe_id = _coverage_universe_id(
        prefix="obs",
        source=source,
        competence=competence,
        cutoff=cutoff,
        method_version=METHOD_VERSION,
        schema_version=SCHEMA_VERSION,
        universe_kind="OBSERVED_CORPUS",
        catalog_hash=catalog_hash,
        grain=grain,
        inclusion_rules=OBSERVED_INCLUSION,
        exclusion_rules=OBSERVED_EXCLUSION,
    )
    return VersionedUniverse(
        national_universe_id=universe_id,
        schema_version=SCHEMA_VERSION,
        method_version=METHOD_VERSION,
        core_method_version=CORE_METHOD_VERSION,
        universe_kind="OBSERVED_CORPUS",
        official_source=source,
        official_source_url=None,
        competence=competence,
        cutoff=cutoff,
        retrieved_at=retrieved_at or as_of,
        as_of=as_of,
        raw_hash=raw_hash,
        catalog_hash=catalog_hash,
        inclusion_rules=OBSERVED_INCLUSION,
        exclusion_rules=OBSERVED_EXCLUSION,
        grain=grain,
        expected_orgs=orgs,
        expected_partitions=len(orgs),
        expected_units=sum(org.unit_count for org in orgs),
        owner=owner,
        next_refresh=next_refresh,
        official_status="BLOCKED",
        official_block_cause=official_block_cause,
        core_universe_id=None,
        labeled_observed_corpus=True,
    )


def blocked_official(
    *,
    cause: str,
    source: str = OFFICIAL_SOURCE_PNCP,
    source_url: str = OFFICIAL_SOURCE_URL_PNCP,
    competence: str,
    cutoff: str,
    as_of: str,
    retrieved_at: str | None = None,
) -> dict[str, str | None]:
    if not cause:
        raise NationalCoverageError("official BLOCKED requires a cause")
    return {
        "official_status": "BLOCKED",
        "official_block_cause": cause,
        "official_source": source,
        "official_source_url": source_url,
        "competence": competence,
        "cutoff": cutoff,
        "retrieved_at": retrieved_at or as_of,
        "as_of": as_of,
    }


def universe_to_dict(universe: VersionedUniverse) -> dict[str, object]:
    return {
        "national_universe_id": universe.national_universe_id,
        "schema_version": universe.schema_version,
        "method_version": universe.method_version,
        "core_method_version": universe.core_method_version,
        "universe_kind": universe.universe_kind,
        "official_source": universe.official_source,
        "official_source_url": universe.official_source_url,
        "competence": universe.competence,
        "cutoff": universe.cutoff,
        "retrieved_at": universe.retrieved_at,
        "as_of": universe.as_of,
        "raw_hash": universe.raw_hash,
        "catalog_hash": universe.catalog_hash,
        "inclusion_rules": list(universe.inclusion_rules),
        "exclusion_rules": list(universe.exclusion_rules),
        "grain": universe.grain,
        "expected_partitions": universe.expected_partitions,
        "expected_units": universe.expected_units,
        "org_count": len(universe.expected_orgs),
        "owner": universe.owner,
        "next_refresh": universe.next_refresh,
        "official_status": universe.official_status,
        "official_block_cause": universe.official_block_cause,
        "core_universe_id": universe.core_universe_id,
        "labeled_observed_corpus": universe.labeled_observed_corpus,
    }
