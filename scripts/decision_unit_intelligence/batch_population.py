"""Canonical datalake populations for durable contact discovery."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from scripts.confenge_contact_resolution.continuous_from_target_fit import (
    load_construction_jobs_from_dsn,
)
from scripts.confenge_contact_resolution.enrichment_batch import CompanyJob
from scripts.confenge_target_fit import TARGET_CONFIRMED

TARGET_CONFIRMED_POPULATION = "target-confirmed"

_TIER_PRIORITY = {
    "PRIORITARIO_AGORA": 4_000_000,
    "A1": 3_000_000,
    "A2": 2_000_000,
    "strategic": 1_000_000,
    "universe": 0,
}


@dataclass(frozen=True)
class DiscoveryPopulation:
    name: str
    jobs: tuple[CompanyJob, ...]
    selection_hash: str
    input_evidence_version: str
    metadata: dict[str, Any]


def _stable_selection_row(job: CompanyJob) -> dict[str, Any]:
    meta = job.meta or {}
    return {
        "canonical_account_id": job.cnpj14,
        "company_key": meta.get("company_key"),
        "cnpj_raiz": meta.get("cnpj_raiz"),
        "sector_class": meta.get("sector_class"),
        "target_fit_class": meta.get("target_fit_class"),
        "target_fit_version": meta.get("target_fit_version"),
        "target_fit_input_fingerprint": meta.get("target_fit_input_fingerprint"),
        "target_fit_source_watermark": meta.get("target_fit_source_watermark"),
        "target_fit_computed_at": meta.get("target_fit_computed_at"),
        "razao_social": meta.get("razao_social") or job.razao_social,
        "nome_fantasia": meta.get("nome_fantasia"),
        "registry_source": meta.get("registry_source"),
        "registry_source_version": meta.get("registry_source_version"),
        "registry_source_date": meta.get("registry_source_date"),
    }


def priority_for_job(job: CompanyJob) -> int:
    """Map commercial tier to queue priority while preserving stable rank."""
    base = _TIER_PRIORITY.get(job.priority_tier, 0)
    return base - min(max(int(job.priority_rank), 0), 999_999)


def build_discovery_population(
    jobs: list[CompanyJob],
    *,
    population: str,
) -> DiscoveryPopulation:
    if population != TARGET_CONFIRMED_POPULATION:
        raise ValueError(f"unsupported contact-discovery population: {population}")

    selected = [
        job
        for job in jobs
        if str((job.meta or {}).get("target_fit_class") or "") == TARGET_CONFIRMED
    ]
    if not selected:
        raise ValueError("target-confirmed population is empty; refusing a zero-denominator full-scale claim")
    invalid = [
        job
        for job in selected
        if not bool((job.meta or {}).get("representative_establishment_observed"))
        or len(str(job.cnpj14 or "")) != 14
        or not str(job.cnpj14 or "").isdigit()
    ]
    if invalid:
        roots = [str((job.meta or {}).get("cnpj_raiz") or job.cnpj14) for job in invalid[:10]]
        raise ValueError(
            "target-confirmed population contains accounts without an observed CNPJ14; "
            f"count={len(invalid)} sample_roots={roots}. Refusing to synthesize establishments."
        )
    missing_evidence = [
        job
        for job in selected
        if any(
            not (job.meta or {}).get(field)
            for field in (
                "target_fit_version",
                "target_fit_input_fingerprint",
                "target_fit_source_watermark",
                "target_fit_computed_at",
            )
        )
    ]
    if missing_evidence:
        roots = [str((job.meta or {}).get("cnpj_raiz") or job.cnpj14) for job in missing_evidence[:10]]
        raise ValueError(
            "target-confirmed population lacks authoritative target-fit evidence metadata; "
            f"count={len(missing_evidence)} sample_roots={roots}"
        )

    selected.sort(key=lambda item: (-priority_for_job(item), item.cnpj14))
    account_ids = [job.cnpj14 for job in selected]
    duplicates = sorted(item for item, count in Counter(account_ids).items() if count > 1)
    if duplicates:
        raise ValueError(
            "target-confirmed population is not one-account-per-CNPJ; "
            f"duplicate_count={len(duplicates)} sample={duplicates[:10]}"
        )

    rows = [_stable_selection_row(job) for job in selected]
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    watermarks = sorted(
        {
            str((job.meta or {}).get("target_fit_source_watermark"))
            for job in selected
            if (job.meta or {}).get("target_fit_source_watermark")
        }
    )
    versions = sorted(
        {
            str((job.meta or {}).get("target_fit_version"))
            for job in selected
            if (job.meta or {}).get("target_fit_version")
        }
    )
    computed = sorted(
        str((job.meta or {}).get("target_fit_computed_at"))
        for job in selected
        if (job.meta or {}).get("target_fit_computed_at")
    )
    metadata = {
        "population": population,
        "population_total": len(selected),
        "runnable_total": len(selected),
        "selection_hash": digest,
        "selection_complete": True,
        "sampled": False,
        "target_fit_versions": versions,
        "source_watermarks": watermarks,
        "target_fit_computed_at_min": computed[0] if computed else None,
        "target_fit_computed_at_max": computed[-1] if computed else None,
    }
    return DiscoveryPopulation(
        name=population,
        jobs=tuple(selected),
        selection_hash=digest,
        input_evidence_version=f"target-fit.{digest[:16]}",
        metadata=metadata,
    )


def load_discovery_population(dsn: str, *, population: str) -> DiscoveryPopulation:
    return build_discovery_population(
        load_construction_jobs_from_dsn(dsn),
        population=population,
    )
