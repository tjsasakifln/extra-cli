"""Construction/engineering evidence using existing commercial classifiers.

Does not invent sector membership. Reuses:
- ``scripts.commercial_leads.contract_relevance``
- ``scripts.commercial_leads.sector_fit``
- ``scripts.coverage.sector_engineering`` (secondary corroboration)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial_leads.contract_relevance import (
    RULE_VERSION as CONTRACT_RELEVANCE_VERSION,
)
from scripts.commercial_leads.contract_relevance import classify_contract_relevance
from scripts.commercial_leads.sector_fit import (
    ACTIVITY_CONSTRUCTION,
    ACTIVITY_ENGINEERING_SERVICE,
    ACTIVITY_TECHNICAL_DESIGN,
    CLASS_CONFIRMED,
    CLASS_OUT,
    CLASS_POSSIBLE,
    CLASS_STRONG,
    classify_supplier_sector_fit,
)
from scripts.commercial_leads.sector_fit import (
    RULE_VERSION as SECTOR_FIT_VERSION,
)
from scripts.confenge_universe.target_fit import (
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
    classify_target_fit,
)
from scripts.coverage.sector_engineering import classify_sector

# Activity classes that belong in the construction/engineering B2G universe
UNIVERSE_ACTIVITY_CLASSES = frozenset(
    {
        ACTIVITY_CONSTRUCTION,
        ACTIVITY_ENGINEERING_SERVICE,
        ACTIVITY_TECHNICAL_DESIGN,
    }
)

# Sector fit classes that prove construction evidence strong enough for membership
# POSSIBLE may enter the research universe but never auto-send (see target_fit).
CONSTRUCTION_MEMBER_CLASSES = frozenset(
    {
        CLASS_CONFIRMED,
        CLASS_STRONG,
        CLASS_POSSIBLE,
    }
)


@dataclass
class ConstructionEvidence:
    is_construction: bool
    sector_fit: str
    activity_class: str
    confidence: float
    relevant_contract_count: int
    total_contract_count: int
    relevant_ratio: float
    reason_codes: list[str] = field(default_factory=list)
    object_categories: list[str] = field(default_factory=list)
    rule_versions: dict[str, str] = field(default_factory=dict)
    epistemic_class: str = "EVIDENCE"  # EVIDENCE | INFERENCE | ABSENCE
    provenance: list[dict[str, Any]] = field(default_factory=list)
    target_fit_class: str = TARGET_PROBABLE_RESEARCH
    target_fit_evidence: list[dict[str, Any]] = field(default_factory=list)
    target_fit_reason_codes: list[str] = field(default_factory=list)
    target_fit_confidence: float = 0.0
    target_fit_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _object_categories(contracts: list[dict[str, Any]]) -> list[str]:
    cats: set[str] = set()
    for row in contracts:
        obj = row.get("objeto_contrato") or row.get("objeto")
        rel = classify_contract_relevance(obj)
        if rel.status != "PASS":
            continue
        sm = classify_sector(str(obj or ""))
        if sm.sector_match and sm.sector and sm.sector != "nao_engenharia":
            cats.add(sm.sector)
        elif rel.strong_hits:
            cats.add("obras_engenharia_geral")
    return sorted(cats)


def assess_construction(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    contracts: list[dict[str, Any]],
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
) -> ConstructionEvidence:
    """Decide whether a supplier group has B2G construction/engineering evidence."""
    decision = classify_supplier_sector_fit(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        contracts=contracts,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_secundarios or [],
        history_is_full=True,
    )
    cats = _object_categories(contracts)
    reasons = list(decision.reason_codes)
    is_member = False
    epistemic = "EVIDENCE"

    if decision.classification in (CLASS_CONFIRMED, CLASS_STRONG):
        is_member = True
        epistemic = "EVIDENCE"
        reasons.append("sector_fit_publishable")
    elif decision.classification == CLASS_POSSIBLE and decision.relevant_contract_count >= 1:
        # POSSIBLE with at least one relevant contract stays in universe
        is_member = True
        epistemic = "INFERENCE"
        reasons.append("sector_fit_possible_with_relevant_contract")
    elif decision.activity_class in UNIVERSE_ACTIVITY_CLASSES and decision.relevant_contract_count >= 1:
        is_member = True
        epistemic = "INFERENCE"
        reasons.append("activity_class_engineering_with_relevant")
    elif decision.classification == CLASS_OUT:
        is_member = False
        epistemic = "EVIDENCE"
        reasons.append("sector_fit_out_of_scope")
    else:
        # Corroborate with sector_engineering on any PASS object
        pass_hits = 0
        for row in contracts:
            obj = row.get("objeto_contrato") or row.get("objeto")
            if classify_contract_relevance(obj).status == "PASS":
                sm = classify_sector(str(obj or ""))
                if sm.sector_match:
                    pass_hits += 1
        if pass_hits >= 1:
            is_member = True
            epistemic = "INFERENCE"
            reasons.append("sector_engineering_corroboration")
        else:
            is_member = False
            epistemic = "ABSENCE"
            reasons.append("no_construction_evidence")

    # Explicit ICP target-fit (stricter than universe membership).
    # POSSIBLE/adjacency can stay in universe for research but not auto-send.
    tf = classify_target_fit(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        contracts=contracts,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_secundarios or [],
        sector_fit=decision.classification,
        activity_class=decision.activity_class,
        construction_evidence={
            "sector_fit": decision.classification,
            "activity_class": decision.activity_class,
            "relevant_contract_count": int(decision.relevant_contract_count),
            "relevant_ratio": float(decision.relevant_contract_ratio),
        },
    )
    # Hard out-of-scope with zero execution: do not keep as universe construction member.
    if tf.target_fit_class == TARGET_OUT_OF_SCOPE and tf.relevant_execution_contract_count == 0:
        is_member = False
        epistemic = "EVIDENCE"
        reasons.append("target_fit_out_of_scope")
        reasons.extend(tf.target_fit_reason_codes[:3])

    return ConstructionEvidence(
        is_construction=is_member,
        sector_fit=decision.classification,
        activity_class=decision.activity_class,
        confidence=float(decision.confidence),
        relevant_contract_count=int(decision.relevant_contract_count),
        total_contract_count=int(decision.total_contract_count),
        relevant_ratio=float(decision.relevant_contract_ratio),
        reason_codes=reasons,
        object_categories=cats,
        rule_versions={
            "sector_fit": SECTOR_FIT_VERSION,
            "contract_relevance": CONTRACT_RELEVANCE_VERSION,
            "construction_bridge": "confenge-universe-construction-v2",
            "target_fit": tf.target_fit_version,
        },
        epistemic_class=epistemic,
        provenance=[
            {
                "source": "commercial_leads.sector_fit",
                "classification": decision.classification,
                "activity_class": decision.activity_class,
                "confidence": decision.confidence,
            },
            {
                "source": "confenge_universe.target_fit",
                "target_fit_class": tf.target_fit_class,
                "confidence": tf.target_fit_confidence,
            },
        ],
        target_fit_class=tf.target_fit_class,
        target_fit_evidence=list(tf.target_fit_evidence),
        target_fit_reason_codes=list(tf.target_fit_reason_codes),
        target_fit_confidence=float(tf.target_fit_confidence),
        target_fit_version=tf.target_fit_version,
    )
