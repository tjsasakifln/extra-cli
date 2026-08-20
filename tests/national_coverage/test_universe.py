"""Versioned universe construction via the shipped coverage functions."""

from __future__ import annotations

import pytest

from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import NationalCoverageError, PublishingOrg
from scripts.national_coverage.universe import (
    build_observed_corpus_universe,
    build_official_universe,
)


def _orgs() -> tuple[PublishingOrg, ...]:
    return (
        PublishingOrg("11111111000191", "Orgao A", 1, "SC"),
        PublishingOrg("22222222000191", "Orgao B", 3, "SP"),
    )


def test_official_universe_is_deterministic() -> None:
    first = build_official_universe(
        source="pncp",
        source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="raw-abc",
        orgs=_orgs(),
    )
    second = build_official_universe(
        source="pncp",
        source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="raw-abc",
        orgs=_orgs(),
    )
    assert first.national_universe_id == second.national_universe_id
    assert first.catalog_hash == second.catalog_hash
    assert len(first.catalog_hash) == 64
    assert first.national_universe_id.startswith("ncv-pncp-")
    assert first.core_universe_id and first.core_universe_id.startswith("nu-pncp-")
    assert first.official_source_url == "https://pncp.gov.br/api/pncp/v1/orgaos"
    assert first.expected_partitions == 2
    assert first.expected_units == 4
    assert first.universe_kind == "OFFICIAL"
    assert first.official_status == "AVAILABLE"
    assert "extra_1093_monitored_entes" in first.exclusion_rules


def test_required_source_hash_cutoff_version() -> None:
    orgs = _orgs()
    with pytest.raises(NationalCoverageError, match="required"):
        build_official_universe(
            source="",
            source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
            competence="contratos-2026",
            cutoff="2026-08-16T00:00:00Z",
            as_of="2026-08-16T00:00:00Z",
            raw_hash="raw",
            orgs=orgs,
        )
    with pytest.raises(NationalCoverageError, match="required"):
        build_official_universe(
            source="pncp",
            source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
            competence="contratos-2026",
            cutoff="",
            as_of="2026-08-16T00:00:00Z",
            raw_hash="raw",
            orgs=orgs,
        )
    with pytest.raises(NationalCoverageError, match="required"):
        build_official_universe(
            source="pncp",
            source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
            competence="contratos-2026",
            cutoff="2026-08-16T00:00:00Z",
            as_of="2026-08-16T00:00:00Z",
            raw_hash="",
            orgs=orgs,
        )


def test_1093_catalog_cannot_become_national_denominator() -> None:
    fake = tuple(PublishingOrg(f"{index:014d}", f"Org {index}") for index in range(1093))
    with pytest.raises(NationalCoverageError, match="extra_1093"):
        build_official_universe(
            source="pncp",
            source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
            competence="contratos-2026",
            cutoff="2026-08-16T00:00:00Z",
            as_of="2026-08-16T00:00:00Z",
            raw_hash="raw-1093",
            orgs=fake,
        )


def test_extra_1093_source_refused() -> None:
    with pytest.raises(NationalCoverageError, match="forbidden_national_source"):
        build_official_universe(
            source="extra_1093_monitored",
            source_url=None,
            competence="contratos-2026",
            cutoff="2026-08-16T00:00:00Z",
            as_of="2026-08-16T00:00:00Z",
            raw_hash="raw",
            orgs=_orgs(),
        )


def test_observed_corpus_is_labeled_and_cannot_be_official() -> None:
    universe = build_observed_corpus_universe(
        source="pncp_supplier_contracts",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="obs-raw",
        orgs=_orgs(),
        official_block_cause="official_catalog_not_provided",
    )
    assert universe.universe_kind == "OBSERVED_CORPUS"
    assert universe.labeled_observed_corpus is True
    assert universe.official_status == "BLOCKED"
    assert universe.official_block_cause == "official_catalog_not_provided"
    assert universe.national_universe_id.startswith("obs-")
    replay = build_observed_corpus_universe(
        source="pncp_supplier_contracts",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="obs-raw",
        orgs=_orgs(),
        official_block_cause="official_catalog_not_provided",
    )
    assert replay.national_universe_id == universe.national_universe_id
    assert replay.catalog_hash == universe.catalog_hash


def test_evaluate_blocked_official_emits_observed_corpus() -> None:
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "BLOCKED",
                "block_cause": "official_catalog_fetch_failed:timeout",
                "source": "pncp",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [{"raw_org_id": "11111111000191", "contract_count": 2, "uf": "SC"}],
            },
            "request": {"geography": "BR", "period": "2026-01/2026-08", "source": "pncp", "grain": "publishing_org"},
        }
    )
    assert payload["universe"]["universe_kind"] == "OBSERVED_CORPUS"
    assert payload["universe"]["labeled_observed_corpus"] is True
    assert payload["verdict"] == "BLOCKED"
    assert payload["national_claim_authorized"] is False
    assert "observed_corpus_cannot_authorize_national" in payload["reason_codes"]
