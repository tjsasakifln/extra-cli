"""Continuous enrichment over the construction universe — no pilot capacity cap."""

from __future__ import annotations

import inspect

import pytest

from scripts.confenge_contact_resolution import continuous_from_target_fit
from scripts.confenge_contact_resolution.contact_coverage import MINIMUM_PILOT_ACCEPTANCE_SAMPLE
from scripts.confenge_contact_resolution.continuous_from_target_fit import (
    ContinuousEnrichmentConfig,
    load_attempted_keys,
    run_continuous_enrichment,
)
from scripts.confenge_contact_resolution.enrichment_batch import CompanyJob


def test_refuse_max_companies_equal_to_pilot_sample(tmp_path) -> None:  # noqa: ANN001
    cfg = ContinuousEnrichmentConfig(
        output_dir=tmp_path,
        max_companies=MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
    )
    with pytest.raises(ValueError, match="MINIMUM_PILOT_ACCEPTANCE_SAMPLE"):
        run_continuous_enrichment(
            "postgresql://invalid",
            cfg=cfg,
        )


def test_load_attempted_keys_from_checkpoint(tmp_path) -> None:  # noqa: ANN001
    ck = tmp_path / "checkpoint.json"
    ck.write_text(
        '{"completed_cnpjs": ["12345678000199", "87654321000100"]}\n',
        encoding="utf-8",
    )
    keys = load_attempted_keys(ck)
    assert "12345678" in keys
    assert "87654321" in keys


def test_company_job_priority_order() -> None:
    from scripts.confenge_contact_resolution.enrichment_batch import priority_sort_key

    jobs = [
        CompanyJob(cnpj14="22222222000100", priority_tier="universe"),
        CompanyJob(cnpj14="11111111000100", priority_tier="A1", priority_rank=1),
        CompanyJob(cnpj14="33333333000100", priority_tier="A2"),
    ]
    ordered = sorted(jobs, key=priority_sort_key)
    assert ordered[0].priority_tier == "A1"
    assert ordered[1].priority_tier == "A2"


def test_continuous_enrichment_population_is_sector_not_target_fit() -> None:
    src = inspect.getsource(continuous_from_target_fit.load_construction_jobs_from_dsn)
    assert "confenge_company_sector_current" in src
    assert "CONSTRUCTION_CONFIRMED" in src
    assert "CONSTRUCTION_PROBABLE" in src
    assert "WHERE shadow_class" not in src
    assert "WHERE target_fit_class" not in src
    assert 'raiz + "0001"' not in src
    assert "representative_cnpj14" in src


def test_process_harvest_never_synthesizes_establishment_cnpj() -> None:
    from scripts.confenge_process_enrichment.national_confirmed import (
        normalize_cnpj14,
    )

    class EmptyResult:
        process_graph = None

    assert normalize_cnpj14("11222333", EmptyResult()) is None
    assert (
        normalize_cnpj14(
            "11222333",
            EmptyResult(),
            observed_fallback="11222333000181",
        )
        == "11222333000181"
    )


def test_legacy_default_checkpoint_is_migrated_once(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    old = tmp_path / "continuous-confirmed"
    new = tmp_path / "continuous-construction"
    old.mkdir()
    (old / "checkpoint.json").write_text('{"completed_cnpjs":["123"]}\n', encoding="utf-8")
    monkeypatch.setattr(continuous_from_target_fit, "LEGACY_DEFAULT_OUT", old)
    monkeypatch.setattr(continuous_from_target_fit, "DEFAULT_OUT", new)

    assert continuous_from_target_fit.migrate_legacy_checkpoint(new) is True
    assert (new / "checkpoint.json").read_text(encoding="utf-8") == '{"completed_cnpjs":["123"]}\n'
    (new / "checkpoint.json").write_text("keep\n", encoding="utf-8")
    assert continuous_from_target_fit.migrate_legacy_checkpoint(new) is False
    assert (new / "checkpoint.json").read_text(encoding="utf-8") == "keep\n"
