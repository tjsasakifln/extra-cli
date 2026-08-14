"""Tests for #302 national publishing-org denominator."""

from __future__ import annotations

import pytest

from scripts.national_contract_truth.national_universe import (
    EXTRA_COMMERCIAL_DENOMINATOR,
    NationalUniverseError,
    PartitionResult,
    PublishingOrg,
    build_universe,
    reconcile_partitions,
)


def _orgs() -> tuple[PublishingOrg, ...]:
    return (
        PublishingOrg("org-a", "pncp", "2026", "Orgao A"),
        PublishingOrg("org-b", "pncp", "2026", "Orgao B", unit_count=3),
    )


def test_universe_has_id_source_cutoff_hash_and_counts() -> None:
    universe = build_universe(
        source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method="pncp-orgaos-publicantes-v1",
    )
    assert universe.national_universe_id.startswith("nu-pncp-")
    assert universe.source == "pncp"
    assert universe.cutoff == "2026-08-01"
    assert universe.org_count == 2
    assert universe.unit_count == 4
    assert len(universe.catalog_hash) == 64
    again = build_universe(
        source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method="pncp-orgaos-publicantes-v1",
    )
    assert again.catalog_hash == universe.catalog_hash
    assert again.national_universe_id == universe.national_universe_id


def test_nacional_completo_only_when_every_partition_closes() -> None:
    universe = build_universe(
        source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method="pncp-orgaos-publicantes-v1",
    )
    report = reconcile_partitions(
        universe,
        (
            PartitionResult("org-a", "FOUND", evidence="raw:a"),
            PartitionResult("org-b", "ZERO_CONFIRMED", evidence="raw:b-empty"),
        ),
    )
    assert report["nacional_completo"] is True
    assert report["extra_1093_used_as_denominator"] is False
    assert report["extra_commercial_denominator"] == EXTRA_COMMERCIAL_DENOMINATOR == 1093
    replay = reconcile_partitions(
        universe,
        (
            PartitionResult("org-a", "FOUND", evidence="raw:a"),
            PartitionResult("org-b", "ZERO_CONFIRMED", evidence="raw:b-empty"),
        ),
    )
    assert replay["reconciliation_hash"] == report["reconciliation_hash"]


def test_blocked_partition_and_1093_substitution_fail_closed() -> None:
    universe = build_universe(
        source="pncp",
        competence="contratos-2026",
        cutoff="2026-08-01",
        orgs=_orgs(),
        method="pncp-orgaos-publicantes-v1",
    )
    report = reconcile_partitions(
        universe,
        (
            PartitionResult("org-a", "FOUND", evidence="raw:a"),
            PartitionResult("org-b", "BLOCKED", evidence="429"),
        ),
    )
    assert report["nacional_completo"] is False
    with pytest.raises(NationalUniverseError, match="partition_set_mismatch"):
        reconcile_partitions(
            universe,
            (PartitionResult("org-a", "FOUND", evidence="raw:a"),),
        )
