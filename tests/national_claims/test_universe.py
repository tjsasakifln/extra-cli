"""Deterministic national universe and four-kind separation."""

from __future__ import annotations

import pytest

from scripts.national_claims.models import OrgSpec
from scripts.national_claims.sample_fixtures import fixture_needs_data
from scripts.national_claims.universe import (
    UniverseSeparationError,
    assert_national_denominator,
    build_companion_universe,
    build_national_universe,
    build_universe_bundle,
    universe_diff,
)
from scripts.national_contract_truth.national_universe import EXTRA_COMMERCIAL_DENOMINATOR


def _orgs() -> tuple[OrgSpec, ...]:
    return (
        OrgSpec("org-a", "Orgao A", 1, "SP"),
        OrgSpec("org-b", "Orgao B", 3, "RJ"),
    )


def test_denominator_and_universe_hash_are_deterministic() -> None:
    first = build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method_version="pncp-orgaos-publicantes-v1",
    )
    second = build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method_version="pncp-orgaos-publicantes-v1",
    )
    assert first.universe_id == second.universe_id
    assert first.catalog_hash == second.catalog_hash
    assert first.universe_id.startswith("nu-pncp-")
    assert len(first.catalog_hash) == 64
    assert first.expected_partitions == 2
    assert first.expected_units == 4
    assert first.national_universe_id == first.universe_id
    assert first.owner
    assert first.review_cadence
    assert "extra_1093_monitored_entes" in first.exclusion_rules


def test_four_universes_are_not_substitutable() -> None:
    national = build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method_version="pncp-orgaos-publicantes-v1",
    )
    icp = build_companion_universe(
        universe_kind="icp_commercial",
        official_source="icp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=(OrgSpec("icp-1", "ICP 1"),),
        method_version="icp-v1",
        inclusion_rules=("commercial_icp",),
        exclusion_rules=("national",),
    )
    extra = build_companion_universe(
        universe_kind="extra_1093_monitored",
        official_source="sc_public_entities",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=(OrgSpec("ent-1", "Ente 1"),),
        method_version="extra-1093-v1",
        inclusion_rules=("raio_200km",),
        exclusion_rules=("national",),
    )
    observed = build_companion_universe(
        universe_kind="observed_corpus",
        official_source="snapshot",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=(OrgSpec("org-a", "seen"),),
        method_version="obs-v1",
        inclusion_rules=("snapshot_rows",),
        exclusion_rules=("unobserved",),
    )
    bundle = build_universe_bundle(
        national=national,
        icp_commercial=icp,
        extra_1093_monitored=extra,
        observed_corpus=observed,
    )
    assert bundle.national.universe_kind == "national"
    assert extra.national_universe_id is None
    assert extra.expected_partitions != EXTRA_COMMERCIAL_DENOMINATOR
    with pytest.raises(UniverseSeparationError):
        assert_national_denominator("extra_1093_monitored")
    with pytest.raises(UniverseSeparationError):
        assert_national_denominator("observed_corpus")
    with pytest.raises(UniverseSeparationError):
        assert_national_denominator("icp_commercial")


def test_1093_org_count_is_refused_as_national_catalog() -> None:
    fake = tuple(OrgSpec(f"org-{index}", f"Org {index}") for index in range(1093))
    with pytest.raises(UniverseSeparationError, match="1.093"):
        build_national_universe(
            official_source="pncp",
            competence="contratos-2026",
            cutoff="2026-08-01",
            orgs=fake,
            method_version="pncp-orgaos-publicantes-v1",
        )


def test_universe_change_is_material() -> None:
    prior = build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method_version="pncp-orgaos-publicantes-v1",
    )
    current = build_national_universe(
        official_source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-02",
        orgs=_orgs(),
        method_version="pncp-orgaos-publicantes-v2",
    )
    diff = universe_diff(prior, current)
    assert diff["material"] is True
    assert "catalog_hash" in diff["changed"]
    assert "method_version" in diff["changed"]


def test_sample_fixture_keeps_four_distinct_hashes() -> None:
    from scripts.national_claims.loader import request_from_dict

    request = request_from_dict(fixture_needs_data())
    hashes = {
        request.universes.national.catalog_hash,
        request.universes.icp_commercial.catalog_hash,
        request.universes.extra_1093_monitored.catalog_hash,
        request.universes.observed_corpus.catalog_hash,
    }
    assert len(hashes) == 4
    assert request.universes.national.expected_partitions != EXTRA_COMMERCIAL_DENOMINATOR
