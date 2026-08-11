"""Pure sector membership classification for the CONFENGE construction universe.

This dimension answers only whether a supplier belongs to construction,
engineering, infrastructure, or related technical services. It never uses a
commercial target-fit result to decide sector membership.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.commercial_leads.sector_fit import (
    CLASS_CONFIRMED,
    CLASS_CONFLICTING,
    CLASS_OUT,
    CLASS_POSSIBLE,
    CLASS_STRONG,
    CLASS_UNKNOWN,
    SectorFitDecision,
    classify_supplier_sector_fit,
)

CONSTRUCTION_CONFIRMED = "CONSTRUCTION_CONFIRMED"
CONSTRUCTION_PROBABLE = "CONSTRUCTION_PROBABLE"
NON_CONSTRUCTION = "NON_CONSTRUCTION"
SECTOR_INSUFFICIENT_EVIDENCE = "SECTOR_INSUFFICIENT_EVIDENCE"
SECTOR_CLASSES = frozenset(
    {
        CONSTRUCTION_CONFIRMED,
        CONSTRUCTION_PROBABLE,
        NON_CONSTRUCTION,
        SECTOR_INSUFFICIENT_EVIDENCE,
    }
)
CONSTRUCTION_SECTOR_CLASSES = frozenset({CONSTRUCTION_CONFIRMED, CONSTRUCTION_PROBABLE})
SECTOR_CLASSIFIER_VERSION = "confenge-sector-classifier-v1"


@dataclass(frozen=True)
class SectorClassification:
    sector_class: str
    confidence: float
    reason_codes: list[str]
    evidence: list[dict[str, Any]]
    source_sector_fit: str
    activity_class: str
    relevant_contract_count: int
    total_contract_count: int
    relevant_ratio: float
    classifier_version: str = SECTOR_CLASSIFIER_VERSION

    @property
    def is_construction(self) -> bool:
        return self.sector_class in CONSTRUCTION_SECTOR_CLASSES

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sector_class_from_fit(decision: SectorFitDecision) -> str:
    """Map existing sector evidence to the canonical sector dimension."""
    if decision.classification in {CLASS_CONFIRMED, CLASS_STRONG}:
        return CONSTRUCTION_CONFIRMED
    if decision.classification == CLASS_POSSIBLE:
        return CONSTRUCTION_PROBABLE
    if decision.classification == CLASS_OUT:
        return NON_CONSTRUCTION
    if decision.classification in {CLASS_UNKNOWN, CLASS_CONFLICTING}:
        return SECTOR_INSUFFICIENT_EVIDENCE
    raise ValueError(f"unknown sector-fit class: {decision.classification!r}")


def classify_company_sector(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
    history_is_full: bool = True,
    history_stats: dict[str, Any] | None = None,
) -> SectorClassification:
    """Classify sector membership without consulting target-fit."""
    fit = classify_supplier_sector_fit(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        contracts=contracts or [],
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_secundarios or [],
        history_is_full=history_is_full,
        history_stats=history_stats,
    )
    sector_class = sector_class_from_fit(fit)
    reasons = [f"source_sector_fit:{fit.classification}", *fit.reason_codes]
    return SectorClassification(
        sector_class=sector_class,
        confidence=float(fit.confidence),
        reason_codes=reasons,
        evidence=list(fit.evidence),
        source_sector_fit=fit.classification,
        activity_class=fit.activity_class,
        relevant_contract_count=int(fit.relevant_contract_count),
        total_contract_count=int(fit.total_contract_count_full_history),
        relevant_ratio=float(fit.relevant_contract_ratio_full_history),
    )
