"""Explainable ranking and priority assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.commercial_leads.profile import CommercialProfile
from scripts.commercial_leads.signals import (
    SIGNAL_STATUS_FIRED,
    SIGNAL_STATUS_NC,
    SignalResult,
    decorrelate_contributions,
)


@dataclass
class LeadScore:
    cnpj14: str
    razao_social: str
    score_total: float
    priority: str
    decomposition: dict[str, float]
    signals_fired: list[dict[str, Any]]
    signals_not_computable: list[dict[str, Any]]
    all_signals: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    suggested_offer: str | None
    next_human_step: str
    limitations: list[str] = field(default_factory=list)
    total_value: float = 0.0
    contract_count: int = 0
    last_publication: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cnpj14": self.cnpj14,
            "razao_social": self.razao_social,
            "score_total": round(self.score_total, 4),
            "priority": self.priority,
            "score_decomposition": {k: round(v, 4) for k, v in self.decomposition.items()},
            "signals_fired": self.signals_fired,
            "signals_not_computable": self.signals_not_computable,
            "all_signals": self.all_signals,
            "evidence": self.evidence,
            "suggested_offer": self.suggested_offer,
            "next_human_step": self.next_human_step,
            "limitations": self.limitations,
            "total_value": self.total_value,
            "contract_count": self.contract_count,
            "last_publication": self.last_publication,
            "language_note": (
                "Score é prioridade para revisão humana com base em sinais observados; "
                "não representa claim estatístico de conversão comercial "
                "nem desejo ou interesse inferido da empresa."
            ),
        }


def _priority(score: float, n_fired: int) -> str:
    if score >= 6.0 and n_fired >= 3:
        return "CRITICAL"
    if score >= 4.0 and n_fired >= 2:
        return "HIGH"
    if score >= 2.0 and n_fired >= 1:
        return "MEDIUM"
    if score >= 1.0 and n_fired >= 1:
        return "LOW"
    return "WATCH"


def score_supplier(
    *,
    cnpj14: str,
    razao_social: str,
    signal_results: list[SignalResult],
    profile: CommercialProfile,
    total_value: float = 0.0,
    contract_count: int = 0,
    last_publication: str | None = None,
) -> LeadScore:
    adjusted = decorrelate_contributions(signal_results)
    decomp = {r.signal_id: r.contribution for r in adjusted}
    total = float(sum(decomp.values()))
    fired = [r.as_dict() for r in adjusted if r.status == SIGNAL_STATUS_FIRED]
    nc = [r.as_dict() for r in adjusted if r.status == SIGNAL_STATUS_NC]
    evidence: list[dict[str, Any]] = []
    for r in adjusted:
        if r.status == SIGNAL_STATUS_FIRED:
            for e in r.evidence:
                if isinstance(e, dict):
                    evidence.append({"signal_id": r.signal_id, **e})

    # primary offer: highest contribution fired signal
    offer = None
    if fired:
        top = max(adjusted, key=lambda r: r.contribution if r.status == SIGNAL_STATUS_FIRED else -1)
        offer = top.offer
    prio = _priority(total, len(fired))
    steps = profile.data.get("next_steps_by_priority") or {}
    next_step = str(steps.get(prio) or "Revisar sinais com humano antes de qualquer contato.")

    limitations = []
    for r in adjusted:
        limitations.extend(r.limitations)
    if nc:
        limitations.append(
            f"{len(nc)} sinais NOT_COMPUTABLE por ausência de dados — não interpretados como ausência de dor."
        )

    return LeadScore(
        cnpj14=cnpj14,
        razao_social=razao_social,
        score_total=total,
        priority=prio,
        decomposition=decomp,
        signals_fired=fired,
        signals_not_computable=nc,
        all_signals=[r.as_dict() for r in adjusted],
        evidence=evidence[:50],
        suggested_offer=offer,
        next_human_step=next_step,
        limitations=sorted(set(limitations)),
        total_value=total_value,
        contract_count=contract_count,
        last_publication=last_publication,
    )


def rank_leads(
    leads: list[LeadScore],
    profile: CommercialProfile,
    *,
    suppressed_cnpjs: set[str] | None = None,
    state_by_cnpj: dict[str, str] | None = None,
) -> list[LeadScore]:
    """Rank leads for the commercial queue.

    DO_NOT_CONTACT and other suppressed CNPJs never enter the published queue.
    Human commercial_state overrides are consulted via state_by_cnpj / suppressed_cnpjs.
    """
    min_score = float((profile.data.get("queue") or {}).get("min_score", 1.0))
    min_signals = int((profile.data.get("queue") or {}).get("min_signals_fired", 1))
    suppressed = {s for s in (suppressed_cnpjs or set()) if s}
    states = state_by_cnpj or {}
    # Always suppress DO_NOT_CONTACT from published ranking
    for cnpj, st in states.items():
        if str(st).upper() == "DO_NOT_CONTACT":
            suppressed.add(cnpj)

    drop_dnc = bool((profile.data.get("exclusions") or {}).get("drop_do_not_contact", True))

    eligible: list[LeadScore] = []
    for lead in leads:
        if drop_dnc and lead.cnpj14 in suppressed:
            continue
        if states.get(lead.cnpj14, "").upper() == "DO_NOT_CONTACT":
            continue
        if lead.score_total >= min_score and len(lead.signals_fired) >= min_signals:
            eligible.append(lead)

    def sort_key(lead: LeadScore) -> tuple:
        return (
            -lead.score_total,
            -len(lead.signals_fired),
            -lead.total_value,
            lead.cnpj14,
        )

    eligible.sort(key=sort_key)
    limit = profile.queue_limit
    return eligible[:limit]
