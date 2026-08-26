"""Canonical population selection for full TARGET_CONFIRMED enrichment."""

from __future__ import annotations

import pytest

from scripts.confenge_contact_resolution.enrichment_batch import CompanyJob
from scripts.confenge_target_fit.company_key import canonical_target_membership
from scripts.decision_unit_intelligence.batch_population import (
    TARGET_CONFIRMED_POPULATION,
    build_discovery_population,
    priority_for_job,
)
from scripts.decision_unit_intelligence.cli import main


def _job(
    cnpj: str,
    *,
    target_class: str = "TARGET_CONFIRMED",
    observed: bool = True,
    tier: str = "A1",
) -> CompanyJob:
    root = cnpj[:8]
    return CompanyJob(
        cnpj14=cnpj if observed else root,
        priority_tier=tier,
        priority_rank=10,
        meta={
            "company_key": f"cnpj:{root}",
            "cnpj_raiz": root,
            "representative_establishment_observed": observed,
            "sector_class": "CONSTRUCTION_CONFIRMED",
            "sector_version": "sector.v1",
            "sector_classifier_sha256": "sha256:sector-test",
            "sector_input_fingerprint": f"sector-fp-{root}",
            "sector_source_watermark": "sector-wm-20260824",
            "sector_computed_at": "2026-08-24T11:00:00+00:00",
            "target_fit_class": target_class,
            "target_fit_version": "target-fit.v3",
            "target_fit_classifier_sha": "sha256:target-fit-test",
            "target_fit_mode": "SHADOW",
            "target_fit_input_fingerprint": f"fp-{root}",
            "target_fit_source_watermark": "wm-20260824",
            "target_fit_computed_at": "2026-08-24T12:00:00+00:00",
        },
    )


def test_population_selects_every_confirmed_account_without_a_cap() -> None:
    jobs = [
        _job("22222222000102", tier="A2"),
        _job("11111111000101", tier="A1"),
        _job("33333333000103", target_class="TARGET_PROBABLE_RESEARCH"),
    ]

    selected = build_discovery_population(jobs, population=TARGET_CONFIRMED_POPULATION)

    assert [job.cnpj14 for job in selected.jobs] == ["11111111000101", "22222222000102"]
    assert selected.metadata["population_total"] == 2
    assert selected.metadata["population_count"] == 2
    assert selected.metadata["population_hash"] == selected.selection_hash
    expected_membership = canonical_target_membership(["11111111000101", "22222222000102"])
    assert selected.metadata["membership_count"] == 2
    assert selected.metadata["membership_hash"] == expected_membership["membership_hash"]
    assert selected.metadata["membership_hash_algorithm"] == expected_membership["hash_algorithm"]
    assert selected.metadata["population_as_of"] == "2026-08-24T12:00:00+00:00"
    assert selected.metadata["target_fit_mode"] == "SHADOW"
    assert selected.metadata["target_fit_classifier_sha"] == "sha256:target-fit-test"
    assert selected.metadata["sector_classifier_sha"] == "sha256:sector-test"
    assert selected.metadata["selection_complete"] is True
    assert selected.metadata["sampled"] is False
    assert selected.metadata["source_watermarks"] == ["wm-20260824"]
    assert selected.input_evidence_version.startswith("target-fit.")
    assert len(selected.selection_hash) == 64
    assert priority_for_job(selected.jobs[0]) > priority_for_job(selected.jobs[1])


def test_population_hash_is_stable_across_input_order() -> None:
    first = _job("11111111000101")
    second = _job("22222222000102")
    left = build_discovery_population([first, second], population=TARGET_CONFIRMED_POPULATION)
    right = build_discovery_population([second, first], population=TARGET_CONFIRMED_POPULATION)
    assert left.selection_hash == right.selection_hash


def test_population_refuses_to_invent_an_establishment_cnpj() -> None:
    with pytest.raises(ValueError, match="Refusing to synthesize establishments"):
        build_discovery_population(
            [_job("11111111000101", observed=False)],
            population=TARGET_CONFIRMED_POPULATION,
        )


def test_population_refuses_zero_denominator_and_missing_evidence() -> None:
    with pytest.raises(ValueError, match="population is empty"):
        build_discovery_population([], population=TARGET_CONFIRMED_POPULATION)
    missing = _job("11111111000101")
    missing.meta["target_fit_source_watermark"] = ""
    with pytest.raises(ValueError, match="lacks authoritative target-fit evidence metadata"):
        build_discovery_population([missing], population=TARGET_CONFIRMED_POPULATION)


def test_canonical_population_refuses_disabled_public_discovery() -> None:
    with pytest.raises(SystemExit, match="requires a public --search-backend"):
        main(
            [
                "batch",
                "enqueue",
                "--cohort",
                "target-confirmed-test",
                "--population",
                TARGET_CONFIRMED_POPULATION,
            ]
        )
