"""Commercial validity: combine contract relevance, sector fit, and signal fit.

Published ranking eligibility:
  contract_relevance == PASS
  supplier_sector_fit in {CONFIRMED_ENGINEERING, STRONG_ENGINEERING_FIT}
  commercial_signal_fit == PASS
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial_leads.contract_relevance import classify_contract_relevance
from scripts.commercial_leads.geography import GeographyFitResult, supplier_geography_from_contracts
from scripts.commercial_leads.sector_fit import (
    PUBLISHABLE,
    SectorFitDecision,
    classify_supplier_sector_fit,
)

RULE_VERSION = "commercial-validity-v1"


@dataclass
class CommercialValidity:
    contract_relevance: str  # PASS | FAIL | REVIEW
    supplier_sector_fit: str
    commercial_signal_fit: str  # PASS | FAIL
    geography_fit: str
    publishable: bool
    review_queue: bool
    exclusion_checks: dict[str, bool] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def commercial_signal_fit_from_score(
    *,
    signals_fired: list[Any] | None,
    score_total: float | None,
    min_signals: int = 1,
    min_score: float = 1.0,
) -> tuple[str, list[str]]:
    fired = list(signals_fired or [])
    reasons: list[str] = []
    if len(fired) < min_signals:
        reasons.append("insufficient_fired_signals")
        return "FAIL", reasons
    if score_total is None or float(score_total) < float(min_score):
        reasons.append("score_below_min")
        return "FAIL", reasons
    reasons.append("observable_signals_present")
    return "PASS", reasons


def evaluate_supplier_validity(
    *,
    razao_social: str | None,
    contracts: list[dict[str, Any]],
    signals_fired: list[Any] | None,
    score_total: float | None,
    allowed_ufs: list[str],
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
    min_signals: int = 1,
    min_score: float = 1.0,
    exclusion_flags: dict[str, bool] | None = None,
    run_id: str | None = None,
    object_field: str = "objeto_contrato",
) -> tuple[CommercialValidity, SectorFitDecision, GeographyFitResult]:
    """Full validity assessment for one supplier."""
    # Contract relevance at supplier level: PASS if any relevant contract
    any_pass = False
    best_rel: dict[str, Any] | None = None
    for row in contracts:
        r = classify_contract_relevance(row.get(object_field))
        if r.status == "PASS":
            any_pass = True
            best_rel = r.as_dict()
            break
        if best_rel is None:
            best_rel = r.as_dict()
    contract_rel_status = "PASS" if any_pass else "FAIL"

    sector = classify_supplier_sector_fit(
        razao_social=razao_social,
        contracts=contracts,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_secundarios,
        object_field=object_field,
        run_id=run_id,
    )
    geo = supplier_geography_from_contracts(contracts, allowed_ufs)
    sig_status, sig_reasons = commercial_signal_fit_from_score(
        signals_fired=signals_fired,
        score_total=score_total,
        min_signals=min_signals,
        min_score=min_score,
    )

    excl = exclusion_flags or {}
    reasons: list[str] = list(sector.reason_codes) + list(sig_reasons)
    if contract_rel_status != "PASS":
        reasons.append("contract_relevance_fail")
    if sector.classification not in PUBLISHABLE:
        reasons.append(f"sector_not_publishable:{sector.classification}")
    if sig_status != "PASS":
        reasons.append("commercial_signal_fail")
    if geo.status not in ("PASS",):
        reasons.append(f"geography:{geo.status}")
        if geo.reason:
            reasons.append(geo.reason)

    hard_excl = any(
        excl.get(k)
        for k in (
            "do_not_contact",
            "public_organ",
            "natural_person",
            "invalid_cnpj",
            "duplicate",
        )
    )
    if hard_excl:
        reasons.append("hard_exclusion")

    publishable = (
        contract_rel_status == "PASS"
        and sector.classification in PUBLISHABLE
        and sig_status == "PASS"
        and geo.status == "PASS"
        and not hard_excl
    )
    review_queue = (not publishable) and (
        sector.classification in ("POSSIBLE_ENGINEERING_FIT", "UNKNOWN", "CONFLICTING")
        or geo.status in ("GEOGRAPHY_UNKNOWN", "REVIEW_REQUIRED")
        or contract_rel_status == "PASS"
    )

    validity = CommercialValidity(
        contract_relevance=contract_rel_status,
        supplier_sector_fit=sector.classification,
        commercial_signal_fit=sig_status,
        geography_fit=geo.status,
        publishable=publishable,
        review_queue=review_queue and not hard_excl,
        exclusion_checks={
            "valid_cnpj": not excl.get("invalid_cnpj", False),
            "not_do_not_contact": not excl.get("do_not_contact", False),
            "not_public_organ": not excl.get("public_organ", False),
            "not_natural_person": not excl.get("natural_person", False),
            "not_duplicate": not excl.get("duplicate", False),
            "sector_confirmed_or_strong": sector.classification in PUBLISHABLE,
            "contract_relevance_pass": contract_rel_status == "PASS",
            "commercial_signal_pass": sig_status == "PASS",
            "geography_pass": geo.status == "PASS",
        },
        evidence={
            "sector": sector.as_dict(),
            "contract_relevance_sample": best_rel,
            "geography": geo.as_dict(),
            "signal_reasons": sig_reasons,
        },
        reason_codes=reasons,
    )
    return validity, sector, geo


def published_eligible(v: CommercialValidity) -> bool:
    return bool(v.publishable)
