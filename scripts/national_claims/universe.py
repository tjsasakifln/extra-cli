"""Versioned national universe plus the three non-substitutable companions.

Replays the same raws/hashes through #302 ``build_universe`` so id, catalog
hash and org counts stay deterministic. Extra 1.093, ICP/commercial and the
observed corpus are first-class records and are never accepted as the
national denominator.
"""

from __future__ import annotations

from typing import Any

from scripts.national_claims.hashing import digest
from scripts.national_claims.models import (
    FORBIDDEN_NATIONAL_DENOMINATORS,
    OrgSpec,
    UniverseBundle,
    VersionedUniverse,
)
from scripts.national_contract_truth.national_universe import (
    EXTRA_COMMERCIAL_DENOMINATOR,
    NationalUniverseError,
    PublishingOrg,
    build_universe,
)

DEFAULT_OWNER = "contracts-truth"
DEFAULT_REVIEW_CADENCE = "weekly"
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
)


class UniverseSeparationError(ValueError):
    """A non-national universe was offered as the national denominator."""


def _orgs_from_specs(
    specs: tuple[OrgSpec, ...],
    *,
    source: str,
    competence: str,
) -> tuple[PublishingOrg, ...]:
    return tuple(
        PublishingOrg(
            org_id=spec.org_id,
            source=source,
            competence=competence,
            name=spec.name,
            unit_count=spec.unit_count,
        )
        for spec in specs
    )


def build_national_universe(
    *,
    official_source: str,
    competence: str,
    cutoff: str,
    orgs: tuple[OrgSpec, ...],
    method_version: str,
    inclusion_rules: tuple[str, ...] = NATIONAL_INCLUSION,
    exclusion_rules: tuple[str, ...] = NATIONAL_EXCLUSION,
    version_changes: tuple[str, ...] = (),
    owner: str = DEFAULT_OWNER,
    review_cadence: str = DEFAULT_REVIEW_CADENCE,
) -> VersionedUniverse:
    """Materialize the #302 publishing-org denominator with gate metadata."""
    if not orgs:
        raise NationalUniverseError("national universe has zero publishing orgs")
    if len(orgs) == EXTRA_COMMERCIAL_DENOMINATOR:
        raise UniverseSeparationError("refusing Extra 1.093 org count as a national publishing-org catalog")
    core = build_universe(
        source=official_source,
        competence=competence,
        cutoff=cutoff,
        orgs=_orgs_from_specs(orgs, source=official_source, competence=competence),
        method=method_version,
    )
    return VersionedUniverse(
        universe_id=core.national_universe_id,
        universe_kind="national",
        official_source=official_source,
        cutoff=cutoff,
        competence=competence,
        catalog_hash=core.catalog_hash,
        method_version=method_version,
        expected_orgs=orgs,
        expected_units=core.unit_count,
        expected_partitions=core.org_count,
        inclusion_rules=inclusion_rules,
        exclusion_rules=exclusion_rules,
        version_changes=version_changes,
        owner=owner,
        review_cadence=review_cadence,
    )


def build_companion_universe(
    *,
    universe_kind: str,
    official_source: str,
    competence: str,
    cutoff: str,
    orgs: tuple[OrgSpec, ...],
    method_version: str,
    inclusion_rules: tuple[str, ...],
    exclusion_rules: tuple[str, ...],
    version_changes: tuple[str, ...] = (),
    owner: str = DEFAULT_OWNER,
    review_cadence: str = DEFAULT_REVIEW_CADENCE,
) -> VersionedUniverse:
    if universe_kind == "national":
        return build_national_universe(
            official_source=official_source,
            competence=competence,
            cutoff=cutoff,
            orgs=orgs,
            method_version=method_version,
            inclusion_rules=inclusion_rules,
            exclusion_rules=exclusion_rules,
            version_changes=version_changes,
            owner=owner,
            review_cadence=review_cadence,
        )
    if universe_kind not in {
        "icp_commercial",
        "extra_1093_monitored",
        "observed_corpus",
    }:
        raise UniverseSeparationError(f"unknown universe kind: {universe_kind}")
    seed = {
        "universe_kind": universe_kind,
        "official_source": official_source,
        "competence": competence,
        "cutoff": cutoff,
        "method_version": method_version,
        "orgs": [
            {
                "org_id": org.org_id,
                "name": org.name,
                "unit_count": org.unit_count,
                "geography": org.geography,
            }
            for org in orgs
        ],
    }
    digest_hex = digest(seed)
    prefix = {
        "icp_commercial": "icp",
        "extra_1093_monitored": "x1093",
        "observed_corpus": "obs",
    }[universe_kind]
    return VersionedUniverse(
        universe_id=f"{prefix}-{official_source}-{competence}-{digest_hex[:16]}",
        universe_kind=universe_kind,  # type: ignore[arg-type]
        official_source=official_source,
        cutoff=cutoff,
        competence=competence,
        catalog_hash=digest_hex,
        method_version=method_version,
        expected_orgs=orgs,
        expected_units=sum(org.unit_count for org in orgs),
        expected_partitions=len(orgs),
        inclusion_rules=inclusion_rules,
        exclusion_rules=exclusion_rules,
        version_changes=version_changes,
        owner=owner,
        review_cadence=review_cadence,
    )


def build_universe_bundle(
    *,
    national: VersionedUniverse,
    icp_commercial: VersionedUniverse,
    extra_1093_monitored: VersionedUniverse,
    observed_corpus: VersionedUniverse,
) -> UniverseBundle:
    kinds = {
        national.universe_kind,
        icp_commercial.universe_kind,
        extra_1093_monitored.universe_kind,
        observed_corpus.universe_kind,
    }
    if kinds != {
        "national",
        "icp_commercial",
        "extra_1093_monitored",
        "observed_corpus",
    }:
        raise UniverseSeparationError(f"bundle must carry four distinct kinds, got {sorted(kinds)}")
    ids = {
        national.universe_id,
        icp_commercial.universe_id,
        extra_1093_monitored.universe_id,
        observed_corpus.universe_id,
    }
    if len(ids) != 4:
        raise UniverseSeparationError("universe ids must be distinct")
    if national.catalog_hash in {
        icp_commercial.catalog_hash,
        extra_1093_monitored.catalog_hash,
        observed_corpus.catalog_hash,
    }:
        raise UniverseSeparationError("national catalog hash collides with a companion universe")
    return UniverseBundle(
        national=national,
        icp_commercial=icp_commercial,
        extra_1093_monitored=extra_1093_monitored,
        observed_corpus=observed_corpus,
    )


def assert_national_denominator(kind: str) -> None:
    if kind in FORBIDDEN_NATIONAL_DENOMINATORS or kind != "national":
        raise UniverseSeparationError(f"refusing {kind!r} as the national denominator")


def universe_diff(prior: VersionedUniverse, current: VersionedUniverse) -> dict[str, Any]:
    """Material changes that invalidate last-known-good."""
    changes: list[str] = []
    if prior.catalog_hash != current.catalog_hash:
        changes.append("catalog_hash")
    if prior.method_version != current.method_version:
        changes.append("method_version")
    if prior.official_source != current.official_source:
        changes.append("official_source")
    if prior.competence != current.competence:
        changes.append("competence")
    if prior.cutoff != current.cutoff:
        changes.append("cutoff")
    if prior.expected_partitions != current.expected_partitions:
        changes.append("expected_partitions")
    return {
        "changed": tuple(changes),
        "material": bool(changes),
        "prior_id": prior.universe_id,
        "current_id": current.universe_id,
        "prior_hash": prior.catalog_hash,
        "current_hash": current.catalog_hash,
    }
