"""Explainable multi-dimension scoring for public-agency leads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.public_agency.signals import SignalHit, material_need_signals

DEFAULT_WEIGHTS = {
    "need_score": 0.30,
    "service_fit_score": 0.25,
    "timing_score": 0.20,
    "evidence_quality_score": 0.15,
    "institutional_accessibility_score": 0.10,
}


@dataclass
class AgencyScore:
    agency_id: str
    priority_score: float
    need_score: float
    service_fit_score: float
    timing_score: float
    evidence_quality_score: float
    institutional_accessibility_score: float
    commercial_readiness_score: float
    compliance_risk_score: float
    conflict_risk_score: float
    decomposition: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    supporting_signals: list[str] = field(default_factory=list)
    explanation: str = ""
    selected_service_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_agency(
    *,
    agency_id: str,
    signals: list[SignalHit],
    service_fit: float,
    selected_service_id: str | None,
    has_institutional_contact: bool,
    evidence_count: int,
    mode: str,
    conflict_state: str,
    compliance_blocks: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> AgencyScore:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    fired = [s for s in signals if s.status == "FIRED"]
    material = material_need_signals(signals)

    # need: material signals dominate; small_municipality alone is weak
    need = 0.0
    if material:
        need = _clamp(0.35 + 0.15 * len(material))
    small = next((s for s in fired if s.signal_id == "small_municipality"), None)
    if small and not material:
        need = 0.15  # contextual only — not publishable alone
    elif small and material:
        need = _clamp(need + 0.1)

    # timing from recent / distress / seasonal
    timing = 0.2
    for sid, boost in (
        ("recent_publication_of_engineering_demand", 0.35),
        ("contract_execution_distress", 0.25),
        ("active_direct_contracting_notice", 0.4),
        ("seasonal_procurement_window", 0.15),
    ):
        if any(s.signal_id == sid and s.status == "FIRED" for s in signals):
            timing += boost
    timing = _clamp(timing)

    # evidence quality
    if evidence_count <= 0:
        evidence_q = 0.0
    elif evidence_count < 3:
        evidence_q = 0.4
    elif evidence_count < 10:
        evidence_q = 0.7
    else:
        evidence_q = 0.9
    if any(s.signal_id == "stale_data" and s.status == "FIRED" for s in signals):
        evidence_q = _clamp(evidence_q - 0.25)
    if any(s.signal_id == "insufficient_public_evidence" and s.status == "FIRED" for s in signals):
        evidence_q = 0.0

    access = 0.7 if has_institutional_contact else 0.25
    fit = _clamp(float(service_fit))

    compliance_blocks = compliance_blocks or []
    compliance_risk = _clamp(0.1 * len(compliance_blocks) + (
        0.3 if any(s.signal_id == "possible_expense_fragmentation" and s.status == "FIRED" for s in signals) else 0.0
    ) + (
        0.3 if any(s.signal_id == "legal_classification_ambiguous" and s.status == "FIRED" for s in signals) else 0.0
    ))

    conflict_risk = {
        "CONFLICT_BLOCKED": 1.0,
        "CONFLICT_REVIEW_REQUIRED": 0.5,
        "CONFLICT_CHECK_PENDING": 0.3,
        "CONFLICT_CLEARED_BY_HUMAN_REVIEW": 0.0,
    }.get(conflict_state, 0.3)

    raw = (
        w["need_score"] * need
        + w["service_fit_score"] * fit
        + w["timing_score"] * timing
        + w["evidence_quality_score"] * evidence_q
        + w["institutional_accessibility_score"] * access
    )
    penalties = {
        "compliance_penalty": compliance_risk * 0.25,
        "conflict_penalty": conflict_risk * 0.35,
    }
    priority = _clamp(raw - penalties["compliance_penalty"] - penalties["conflict_penalty"])

    commercial_readiness = _clamp(
        0.4 * fit + 0.3 * evidence_q + 0.2 * access + 0.1 * need - conflict_risk * 0.3
    )

    mode_note = (
        "Oportunidade reativa com publicação/contrato observável."
        if mode == "REACTIVE_OPPORTUNITY"
        else "Prospect proativo: sinais de possível necessidade técnica (sem oportunidade formal isolada)."
    )
    explanation = (
        f"priority={priority:.3f} need={need:.2f} fit={fit:.2f} timing={timing:.2f} "
        f"evidence={evidence_q:.2f} access={access:.2f}; "
        f"material_signals={len(material)}; {mode_note}"
    )

    return AgencyScore(
        agency_id=agency_id,
        priority_score=round(priority, 4),
        need_score=round(need, 4),
        service_fit_score=round(fit, 4),
        timing_score=round(timing, 4),
        evidence_quality_score=round(evidence_q, 4),
        institutional_accessibility_score=round(access, 4),
        commercial_readiness_score=round(commercial_readiness, 4),
        compliance_risk_score=round(compliance_risk, 4),
        conflict_risk_score=round(conflict_risk, 4),
        decomposition={
            "need": round(need * w["need_score"], 4),
            "service_fit": round(fit * w["service_fit_score"], 4),
            "timing": round(timing * w["timing_score"], 4),
            "evidence_quality": round(evidence_q * w["evidence_quality_score"], 4),
            "institutional_accessibility": round(access * w["institutional_accessibility_score"], 4),
        },
        penalties=penalties,
        supporting_signals=[s.signal_id for s in material],
        explanation=explanation,
        selected_service_id=selected_service_id,
    )


def service_fit_for_agency(
    *,
    eng_contract_count: int,
    distress: bool,
    recent_eng: bool,
    object_class: str,
    catalog_services: list[dict[str, Any]],
) -> tuple[float, str | None]:
    """Pick best catalog service and fit score."""
    if not catalog_services:
        return 0.0, None
    # Simple rule-based fit
    if distress:
        sid = "DIAGNOSTICO_DE_CONTRATO_OU_OBRA_CRITICA"
    elif recent_eng and eng_contract_count >= 1:
        sid = "REVISAO_PRE_PUBLICACAO" if eng_contract_count < 3 else "PLANEJAMENTO_TECNICO_DA_CONTRATACAO"
    elif eng_contract_count >= 3:
        sid = "APOIO_TECNICO_A_FISCALIZACAO"
    elif eng_contract_count >= 1:
        sid = "ORCAMENTO_E_PLANEJAMENTO_DE_OBRAS"
    elif object_class == "OTHER_SERVICE":
        sid = "CAPACITACAO_APLICADA"
    else:
        sid = "PLANEJAMENTO_TECNICO_DA_CONTRATACAO"

    ids = {str(s.get("service_id")) for s in catalog_services}
    if sid not in ids:
        sid = next(iter(ids))

    fit = 0.35
    if eng_contract_count:
        fit += min(0.4, 0.1 * eng_contract_count)
    if distress:
        fit += 0.15
    if recent_eng:
        fit += 0.1
    if object_class == "REQUIRES_HUMAN_LEGAL_CLASSIFICATION":
        fit = min(fit, 0.45)
    return _clamp(fit), sid
