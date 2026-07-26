"""Explainable ranking and priority assignment."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from scripts.commercial_leads.profile import CommercialProfile
from scripts.commercial_leads.signals import (
    SIGNAL_STATUS_FIRED,
    SIGNAL_STATUS_NC,
    SignalResult,
    decorrelate_contributions,
)

# Canonical commercial offer score keys (goal §8)
OFFER_SCORE_KEYS: tuple[str, ...] = (
    "diagnostico_b2g_score",
    "licitacoes_propostas_score",
    "auditoria_orcamento_score",
    "acompanhamento_contratual_score",
    "gestao_documental_score",
    "inteligencia_pncp_score",
)

# Map profile offer ids / signal offers → canonical score bucket
_OFFER_BUCKET: dict[str, str] = {
    "diagnostico_b2g": "diagnostico_b2g_score",
    "diagnostico": "diagnostico_b2g_score",
    "apoio_proposta": "licitacoes_propostas_score",
    "licitacoes_propostas": "licitacoes_propostas_score",
    "analise_edital": "licitacoes_propostas_score",
    "auditoria_orcamento": "auditoria_orcamento_score",
    "acompanhamento_admin": "acompanhamento_contratual_score",
    "acompanhamento_contratual": "acompanhamento_contratual_score",
    "gestao_documental": "gestao_documental_score",
    "inteligencia_mercado": "inteligencia_pncp_score",
    "inteligencia_pncp": "inteligencia_pncp_score",
}

SELECTION_RULE_VERSION = "offer-selection-v3-discriminative"


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
    offer_scores: dict[str, float] = field(default_factory=dict)
    selected_offer: str | None = None
    selected_offer_margin: float | None = None
    supporting_signals: list[str] = field(default_factory=list)
    contradicting_signals: list[str] = field(default_factory=list)
    alternative_offer: str | None = None
    selection_rule_version: str = SELECTION_RULE_VERSION

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
            "suggested_offer": self.suggested_offer or self.selected_offer,
            "next_human_step": self.next_human_step,
            "limitations": self.limitations,
            "total_value": self.total_value,
            "contract_count": self.contract_count,
            "last_publication": self.last_publication,
            "offer_scores": {k: round(v, 4) for k, v in self.offer_scores.items()},
            "selected_offer": self.selected_offer or self.suggested_offer,
            "selected_offer_margin": (
                round(self.selected_offer_margin, 4)
                if self.selected_offer_margin is not None
                else None
            ),
            "supporting_signals": self.supporting_signals,
            "contradicting_signals": self.contradicting_signals,
            "alternative_offer": self.alternative_offer,
            "selection_rule_version": self.selection_rule_version,
            "language_note": (
                "Score é prioridade para revisão humana com base em sinais observados; "
                "não representa claim estatístico de conversão comercial "
                "nem desejo ou interesse inferido da empresa."
            ),
        }


def _bucket_for_offer(offer: str | None) -> str | None:
    if not offer:
        return None
    key = str(offer).strip().lower()
    if key in _OFFER_BUCKET:
        return _OFFER_BUCKET[key]
    # already a score key?
    if key.endswith("_score") and key in OFFER_SCORE_KEYS:
        return key
    return None


def compute_offer_scores(
    signal_results: list[SignalResult],
    profile: CommercialProfile,
) -> dict[str, Any]:
    """Score every commercial offer from fired signals + composite mappings.

    Discriminative: different signal mixes yield different offer winners.
    Does not force diversity quotas.
    """
    scores = {k: 0.0 for k in OFFER_SCORE_KEYS}
    support: dict[str, list[str]] = {k: [] for k in OFFER_SCORE_KEYS}
    contradict: list[str] = []

    adjusted = decorrelate_contributions(signal_results)
    fired = [r for r in adjusted if r.status == SIGNAL_STATUS_FIRED]

    # Signal → offer contributions
    for r in fired:
        offer = getattr(r, "offer", None) or (r.as_dict().get("offer") if hasattr(r, "as_dict") else None)
        bucket = _bucket_for_offer(offer)
        contrib = float(r.contribution or 0.0)
        if bucket and contrib > 0:
            scores[bucket] += contrib
            support[bucket].append(r.signal_id)
        elif contrib > 0 and not bucket:
            # unmapped positive contribution: slight generic diagnostic weight
            scores["diagnostico_b2g_score"] += 0.15 * contrib
            support["diagnostico_b2g_score"].append(r.signal_id)

    # Composite offer_mappings from profile
    fired_ids = {r.signal_id for r in fired}
    mappings = list(profile.data.get("offer_mappings") or [])
    for m in mappings:
        needed = set(m.get("when_signals") or [])
        if not needed:
            continue
        if needed.issubset(fired_ids):
            bucket = _bucket_for_offer(m.get("offer"))
            if bucket:
                boost = 1.5 + 0.25 * len(needed)
                scores[bucket] += boost
                support[bucket].append(f"mapping:{m.get('id')}")
        else:
            # partial overlap can contradict pure single-signal dominance
            overlap = needed & fired_ids
            if overlap and len(overlap) < len(needed):
                contradict.append(f"partial_mapping:{m.get('id')}")

    # NC signals slightly reduce confidence of admin-heavy paths when data missing
    nc = [r for r in adjusted if r.status == SIGNAL_STATUS_NC]
    for r in nc:
        if r.signal_id in {"near_expiry", "addendum_recurrence", "concurrent_portfolio"}:
            scores["acompanhamento_contratual_score"] *= 0.85
            contradict.append(f"nc:{r.signal_id}")

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_key, top_val = ranked[0]
    alt_key, alt_val = ranked[1] if len(ranked) > 1 else (None, 0.0)
    margin = round(top_val - float(alt_val or 0.0), 4)

    # Reverse map score key → commercial offer id for queue display
    score_to_offer = {
        "diagnostico_b2g_score": "diagnostico_b2g",
        "licitacoes_propostas_score": "licitacoes_propostas",
        "auditoria_orcamento_score": "auditoria_orcamento",
        "acompanhamento_contratual_score": "acompanhamento_contratual",
        "gestao_documental_score": "gestao_documental",
        "inteligencia_pncp_score": "inteligencia_pncp",
    }
    selected = score_to_offer.get(top_key) if top_val > 0 else None
    alternative = score_to_offer.get(alt_key) if alt_key and alt_val > 0 else None

    return {
        "offer_scores": scores,
        "selected_offer": selected,
        "selected_offer_margin": margin if selected else None,
        "supporting_signals": support.get(top_key, [])[:20],
        "contradicting_signals": contradict[:20],
        "alternative_offer": alternative,
        "selection_rule_version": SELECTION_RULE_VERSION,
    }


def diagnose_offer_distribution(leads: list[dict[str, Any]] | list[LeadScore]) -> dict[str, Any]:
    """Population-level offer discrimination diagnostics."""
    offers: list[str] = []
    margins: list[float] = []
    for item in leads:
        if isinstance(item, LeadScore):
            off = item.selected_offer or item.suggested_offer
            m = item.selected_offer_margin
        else:
            off = item.get("selected_offer") or item.get("suggested_offer")
            m = item.get("selected_offer_margin")
        if off:
            offers.append(str(off))
        if m is not None:
            try:
                margins.append(float(m))
            except (TypeError, ValueError):
                pass
    n = len(offers) or 1
    dist = dict(Counter(offers))
    rates = {k: round(v / n, 4) for k, v in dist.items()}
    dominant_offer = max(dist, key=dist.get) if dist else None  # type: ignore[arg-type]
    dominant_rate = rates.get(dominant_offer or "", 0.0)
    # Shannon entropy of offer distribution
    entropy = 0.0
    for c in dist.values():
        p = c / n
        if p > 0:
            entropy -= p * math.log2(p)
    mean_margin = round(sum(margins) / len(margins), 4) if margins else None
    low_margin = sum(1 for m in margins if m < 0.5)
    robust = bool(
        dominant_rate <= 0.80
        or (mean_margin is not None and mean_margin >= 1.0 and dominant_rate <= 0.95)
    )
    block = None
    if dominant_rate > 0.80 and not robust:
        block = "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE"
    explanation = {
        "dominant_offer": dominant_offer,
        "dominant_offer_rate": dominant_rate,
        "why_uniform": (
            "signal catalog collapsed to one offer bucket"
            if dominant_rate > 0.80
            else "distribution has meaningful variation"
        ),
        "mean_selected_offer_margin": mean_margin,
        "catalog_degenerate": len(dist) <= 1 and n >= 5,
    }
    return {
        "offer_distribution": dist,
        "offer_entropy": round(entropy, 4),
        "dominant_offer_rate": dominant_rate,
        "mean_selected_offer_margin": mean_margin,
        "low_margin_offer_count": low_margin,
        "robust_quantitative_justification": robust,
        "block": block,
        "explanation": explanation,
        "n_leads": len(offers),
        "selection_rule_version": SELECTION_RULE_VERSION,
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

    offer_sel = compute_offer_scores(adjusted, profile)
    offer = offer_sel.get("selected_offer")
    # Fallback: highest contribution fired signal offer (legacy)
    if not offer and fired:
        top = max(adjusted, key=lambda r: r.contribution if r.status == SIGNAL_STATUS_FIRED else -1)
        offer = top.offer
        bucket = _bucket_for_offer(offer)
        if bucket and not offer_sel["offer_scores"].get(bucket):
            offer_sel["offer_scores"][bucket] = float(top.contribution or 0)
            offer_sel["selected_offer"] = offer
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
        offer_scores=dict(offer_sel.get("offer_scores") or {}),
        selected_offer=offer_sel.get("selected_offer") or offer,
        selected_offer_margin=offer_sel.get("selected_offer_margin"),
        supporting_signals=list(offer_sel.get("supporting_signals") or []),
        contradicting_signals=list(offer_sel.get("contradicting_signals") or []),
        alternative_offer=offer_sel.get("alternative_offer"),
        selection_rule_version=str(
            offer_sel.get("selection_rule_version") or SELECTION_RULE_VERSION
        ),
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
