"""Continuous enrichment over TARGET_CONFIRMED — no pilot capacity cap."""

from __future__ import annotations

import pytest

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
