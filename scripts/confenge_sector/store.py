"""Durable materialization for the independent CONFENGE sector dimension."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_sector.classification import (
    SECTOR_CLASSES,
    SECTOR_CLASSIFIER_VERSION,
    classify_company_sector,
)
from scripts.confenge_target_fit.fingerprint import compute_input_fingerprint
from scripts.confenge_target_fit.models import CompanyInput
from scripts.linkage.keys import digits_only, is_valid_cnpj14


@dataclass(frozen=True)
class SectorMaterialization:
    company_key: str
    cnpj_raiz: str
    representative_cnpj14: str | None
    sector_class: str
    sector_confidence: float
    sector_version: str
    sector_classifier_sha256: str
    sector_reason_codes: list[str]
    sector_evidence: list[dict[str, Any]]
    source_sector_fit: str
    activity_class: str
    relevant_contract_count: int
    total_contract_count: int
    input_fingerprint: str
    source_watermark: str
    source_max_updated_at: datetime | None
    computed_at: datetime


def sector_classifier_sha256() -> str:
    try:
        from scripts.commercial_leads import contract_relevance as relevance_module
        from scripts.commercial_leads import sector_fit as sector_fit_module
        from scripts.confenge_sector import classification as classification_module

        source = "\n".join(
            (
                inspect.getsource(classification_module),
                inspect.getsource(sector_fit_module),
                inspect.getsource(relevance_module),
            )
        )
    except (OSError, TypeError):
        source = SECTOR_CLASSIFIER_VERSION
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def materialize_sector(company: CompanyInput, *, now: datetime | None = None) -> SectorMaterialization:
    evidence = dict(company.construction_evidence or {})
    sector_class = str(evidence.get("sector_class") or "")
    if sector_class not in SECTOR_CLASSES:
        classified = classify_company_sector(
            razao_social=company.razao_social,
            nome_fantasia=company.nome_fantasia,
            contracts=company.contracts,
            cnae_principal=company.cnae_principal,
            cnaes_secundarios=company.cnaes_secundarios,
            history_is_full=True,
        )
        evidence.update(classified.as_dict())
        sector_class = classified.sector_class
    observed_branches = sorted(
        {
            digits_only(value)
            for value in company.branch_cnpjs
            if is_valid_cnpj14(value) and digits_only(value)[:8] == company.cnpj_raiz
        },
        key=lambda value: (value[8:12] != "0001", value),
    )
    raw_sector_evidence = list(
        evidence.get("evidence") or evidence.get("provenance") or []
    )
    sector_evidence = [
        item
        for item in raw_sector_evidence
        if not (
            isinstance(item, dict)
            and "target_fit" in str(item.get("source") or "").lower()
        )
    ]
    return SectorMaterialization(
        company_key=company.company_key,
        cnpj_raiz=company.cnpj_raiz,
        representative_cnpj14=observed_branches[0] if observed_branches else None,
        sector_class=sector_class,
        sector_confidence=float(evidence.get("confidence") or 0.0),
        sector_version=str(evidence.get("sector_classifier_version") or SECTOR_CLASSIFIER_VERSION),
        sector_classifier_sha256=sector_classifier_sha256(),
        sector_reason_codes=list(evidence.get("reason_codes") or []),
        sector_evidence=sector_evidence,
        source_sector_fit=str(
            evidence.get("source_sector_fit")
            or evidence.get("sector_fit")
            or company.sector_fit
            or ""
        ),
        activity_class=str(evidence.get("activity_class") or company.activity_class or ""),
        relevant_contract_count=int(evidence.get("relevant_contract_count") or 0),
        total_contract_count=int(evidence.get("total_contract_count") or 0),
        input_fingerprint=compute_input_fingerprint(
            company,
            target_fit_version=SECTOR_CLASSIFIER_VERSION,
        ),
        source_watermark=company.source_watermark,
        source_max_updated_at=company.source_max_updated_at,
        computed_at=now or datetime.now(UTC),
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def publish_sector_materialization(conn: Any, sector: SectorMaterialization) -> bool:
    """Upsert current and append history only when sector inputs changed."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sector_class, input_fingerprint, sector_version
            FROM confenge_company_sector_current
            WHERE company_key = %s
            """,
            (sector.company_key,),
        )
        prior = cur.fetchone()
        if (
            prior
            and prior.get("input_fingerprint") == sector.input_fingerprint
            and prior.get("sector_version") == sector.sector_version
        ):
            return False
        previous_class = prior.get("sector_class") if prior else None
        values = (
            sector.company_key,
            sector.cnpj_raiz,
            sector.representative_cnpj14,
            sector.sector_class,
            sector.sector_confidence,
            sector.sector_version,
            sector.sector_classifier_sha256,
            _json(sector.sector_reason_codes),
            _json(sector.sector_evidence),
            sector.source_sector_fit,
            sector.activity_class,
            sector.relevant_contract_count,
            sector.total_contract_count,
            sector.input_fingerprint,
            sector.source_watermark,
            sector.source_max_updated_at,
            sector.computed_at,
        )
        cur.execute(
            """
            INSERT INTO confenge_company_sector_history (
                company_key, cnpj_raiz, representative_cnpj14,
                sector_class, sector_confidence,
                sector_version, sector_classifier_sha256, sector_reason_codes,
                sector_evidence, source_sector_fit, activity_class,
                relevant_contract_count, total_contract_count, input_fingerprint,
                source_watermark, source_max_updated_at, computed_at,
                previous_sector_class
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s::jsonb,
                %s::jsonb, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s
            )
            """,
            (*values, previous_class),
        )
        cur.execute(
            """
            INSERT INTO confenge_company_sector_current (
                company_key, cnpj_raiz, representative_cnpj14,
                sector_class, sector_confidence,
                sector_version, sector_classifier_sha256, sector_reason_codes,
                sector_evidence, source_sector_fit, activity_class,
                relevant_contract_count, total_contract_count, input_fingerprint,
                source_watermark, source_max_updated_at, computed_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s::jsonb,
                %s::jsonb, %s, %s,
                %s, %s, %s,
                %s, %s, %s, now()
            )
            ON CONFLICT (company_key) DO UPDATE SET
                cnpj_raiz = EXCLUDED.cnpj_raiz,
                representative_cnpj14 = EXCLUDED.representative_cnpj14,
                sector_class = EXCLUDED.sector_class,
                sector_confidence = EXCLUDED.sector_confidence,
                sector_version = EXCLUDED.sector_version,
                sector_classifier_sha256 = EXCLUDED.sector_classifier_sha256,
                sector_reason_codes = EXCLUDED.sector_reason_codes,
                sector_evidence = EXCLUDED.sector_evidence,
                source_sector_fit = EXCLUDED.source_sector_fit,
                activity_class = EXCLUDED.activity_class,
                relevant_contract_count = EXCLUDED.relevant_contract_count,
                total_contract_count = EXCLUDED.total_contract_count,
                input_fingerprint = EXCLUDED.input_fingerprint,
                source_watermark = EXCLUDED.source_watermark,
                source_max_updated_at = EXCLUDED.source_max_updated_at,
                computed_at = EXCLUDED.computed_at,
                updated_at = now()
            """,
            values,
        )
    return True
