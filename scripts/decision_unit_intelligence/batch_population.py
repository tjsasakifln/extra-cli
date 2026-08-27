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
from scripts.confenge_target_fit.company_key import canonical_target_membership
from scripts.confenge_target_fit.coverage import publication_ready

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
        "sector_version": meta.get("sector_version"),
        "sector_classifier_sha256": meta.get("sector_classifier_sha256"),
        "sector_input_fingerprint": meta.get("sector_input_fingerprint"),
        "sector_source_watermark": meta.get("sector_source_watermark"),
        "sector_computed_at": meta.get("sector_computed_at"),
        "target_fit_class": meta.get("target_fit_class"),
        "target_fit_version": meta.get("target_fit_version"),
        "target_fit_classifier_sha": meta.get("target_fit_classifier_sha"),
        "target_fit_mode": meta.get("target_fit_mode"),
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


def _population_freshness(
    computed: list[str],
    coverage_attestation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve how recently this population was *proven* current.

    ``target_fit_computed_at`` only moves when a row's classification actually
    changes. Target-fit is content-addressed, so an unchanged national
    population keeps an ageing max(computed_at) even while a full reconcile
    proves, today, that every canonical root is materialized. Using that maximum
    as the freshness signal makes a correct population expire on the clock and
    deadlocks publication until some row happens to be reclassified.

    The honest freshness signal is the completion time of the full reconcile
    that proved the population complete. It is only trusted when that
    attestation is PUBLICATION_READY; anything weaker falls back to
    max(computed_at), which keeps the downstream staleness gate fail-closed.
    """
    computed_max = computed[-1] if computed else None
    attestation = coverage_attestation or {}
    verified_at = str(
        attestation.get("last_full_reconcile_completed_at")
        or attestation.get("as_of")
        or ""
    ).strip()
    if not verified_at or not publication_ready(attestation):
        return {
            "population_as_of": computed_max,
            "population_as_of_source": "target_fit_computed_at_max",
            "population_verified_at": None,
            "population_coverage_ratio": attestation.get("coverage_ratio"),
            "population_publication_ready": bool(attestation) and publication_ready(attestation),
        }
    # Never let the attestation move freshness backwards past observed evidence.
    resolved = verified_at if not computed_max or verified_at >= computed_max else computed_max
    return {
        "population_as_of": resolved,
        "population_as_of_source": (
            "target_fit_full_reconcile" if resolved == verified_at else "target_fit_computed_at_max"
        ),
        "population_verified_at": verified_at,
        "population_coverage_ratio": attestation.get("coverage_ratio"),
        "population_publication_ready": True,
    }


def build_discovery_population(
    jobs: list[CompanyJob],
    *,
    population: str,
    coverage_attestation: dict[str, Any] | None = None,
) -> DiscoveryPopulation:
    if population != TARGET_CONFIRMED_POPULATION:
        raise ValueError(f"unsupported contact-discovery population: {population}")

    selected = [job for job in jobs if str((job.meta or {}).get("target_fit_class") or "") == TARGET_CONFIRMED]
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
                "target_fit_classifier_sha",
                "target_fit_mode",
                "target_fit_input_fingerprint",
                "target_fit_source_watermark",
                "target_fit_computed_at",
                "sector_version",
                "sector_classifier_sha256",
                "sector_input_fingerprint",
                "sector_source_watermark",
                "sector_computed_at",
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

    membership = canonical_target_membership(account_ids)

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
    sector_computed = sorted(
        str((job.meta or {}).get("sector_computed_at"))
        for job in selected
        if (job.meta or {}).get("sector_computed_at")
    )
    target_fit_classifier_shas = sorted(
        {
            str((job.meta or {}).get("target_fit_classifier_sha"))
            for job in selected
            if (job.meta or {}).get("target_fit_classifier_sha")
        }
    )
    sector_classifier_shas = sorted(
        {
            str((job.meta or {}).get("sector_classifier_sha256"))
            for job in selected
            if (job.meta or {}).get("sector_classifier_sha256")
        }
    )
    target_fit_modes = sorted(
        {str((job.meta or {}).get("target_fit_mode")) for job in selected if (job.meta or {}).get("target_fit_mode")}
    )
    sector_versions = sorted(
        {str((job.meta or {}).get("sector_version")) for job in selected if (job.meta or {}).get("sector_version")}
    )
    sector_watermarks = sorted(
        {
            str((job.meta or {}).get("sector_source_watermark"))
            for job in selected
            if (job.meta or {}).get("sector_source_watermark")
        }
    )
    metadata = {
        "population": population,
        "sector_scope": "RECORDED_NOT_FILTERED",
        "population_total": len(selected),
        "population_count": len(selected),
        "population_hash": digest,
        "membership_schema_version": membership["schema_version"],
        "membership_identity_key": membership["identity_key"],
        "membership_hash_algorithm": membership["hash_algorithm"],
        "membership_count": membership["population_count"],
        "membership_hash": membership["membership_hash"],
        "duplicate_member_count": membership["duplicate_member_count"],
        **_population_freshness(computed, coverage_attestation),
        "runnable_total": len(selected),
        "selection_hash": digest,
        "selection_complete": True,
        "sampled": False,
        "target_fit_versions": versions,
        "target_fit_classifier_shas": target_fit_classifier_shas,
        "target_fit_classifier_sha": (target_fit_classifier_shas[0] if len(target_fit_classifier_shas) == 1 else None),
        "target_fit_modes": target_fit_modes,
        "target_fit_mode": target_fit_modes[0] if len(target_fit_modes) == 1 else "MIXED",
        "source_watermarks": watermarks,
        "target_fit_computed_at_min": computed[0] if computed else None,
        "target_fit_computed_at_max": computed[-1] if computed else None,
        "sector_versions": sector_versions,
        "sector_classifier_shas": sector_classifier_shas,
        "sector_classifier_sha": sector_classifier_shas[0] if len(sector_classifier_shas) == 1 else None,
        "sector_source_watermarks": sector_watermarks,
        "sector_computed_at_min": sector_computed[0] if sector_computed else None,
        "sector_computed_at_max": sector_computed[-1] if sector_computed else None,
    }
    return DiscoveryPopulation(
        name=population,
        jobs=tuple(selected),
        selection_hash=digest,
        input_evidence_version=f"target-fit.{digest[:16]}",
        metadata=metadata,
    )


def load_coverage_attestation(dsn: str) -> dict[str, Any] | None:
    """Read the national target-fit coverage attestation from the datalake."""
    from scripts.confenge_target_fit.coverage import load_coverage_control
    from scripts.confenge_target_fit.db import connect

    conn = connect(dsn, readonly=True)
    try:
        return load_coverage_control(conn) or None
    finally:
        conn.close()


def load_discovery_population(dsn: str, *, population: str) -> DiscoveryPopulation:
    return build_discovery_population(
        load_construction_jobs_from_dsn(dsn, target_confirmed_only=True),
        population=population,
        coverage_attestation=load_coverage_attestation(dsn),
    )
