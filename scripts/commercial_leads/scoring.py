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

# Soft composite mapping boost (hardcoded large boosts over-amplified single-signal flips).
# Keep mapping advisory: primary discrimination comes from multi-bucket signal weights.
OFFER_MAPPING_BASE_BOOST = 0.15
OFFER_MAPPING_PER_SIGNAL_BOOST = 0.05
# Minimum selected-vs-alternative margin for gate PASS (absolute score units)
MIN_SELECTED_OFFER_MARGIN = 0.10
# Single-signal ablation change-rate hard limit (goal §7.2 — do not lower to greenwash)
MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE = 0.50
SELECTION_RULE_VERSION = "offer-selection-v4-multi-bucket"


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


# Signal-id → offer bucket weights (v4 multi-bucket; not a quota).
# Each signal feeds ≥2 buckets so a single ablation cannot monopolize selection.
# Portfolio/expiry cluster deliberately multi-maps (gestao/licitacoes/auditoria)
# to avoid catalog collapse into acompanhamento_contratual alone.
_SIGNAL_OFFER_WEIGHTS: dict[str, dict[str, float]] = {
    "first_public_contract": {
        "diagnostico_b2g_score": 2.0,
        "licitacoes_propostas_score": 1.0,
    },
    "ticket_above_history": {
        "diagnostico_b2g_score": 1.5,
        "auditoria_orcamento_score": 1.2,
    },
    "quantity_growth": {
        "inteligencia_pncp_score": 1.5,
        "licitacoes_propostas_score": 1.2,
    },
    "value_growth": {
        "inteligencia_pncp_score": 1.5,
        "diagnostico_b2g_score": 1.0,
    },
    "new_agency": {
        "diagnostico_b2g_score": 1.2,
        "licitacoes_propostas_score": 1.2,
    },
    "new_region": {
        "diagnostico_b2g_score": 1.1,
        "inteligencia_pncp_score": 1.1,
    },
    "new_object_category": {
        "licitacoes_propostas_score": 1.6,
        "diagnostico_b2g_score": 1.0,
    },
    # Portfolio/expiry cluster: near-equal multi-bucket so single ablation rarely flips winner
    "concurrent_portfolio": {
        "acompanhamento_contratual_score": 0.7,
        "gestao_documental_score": 0.7,
        "licitacoes_propostas_score": 0.6,
        "diagnostico_b2g_score": 0.3,
    },
    "agency_concentration": {
        "gestao_documental_score": 0.7,
        "acompanhamento_contratual_score": 0.6,
        "inteligencia_pncp_score": 0.5,
        "diagnostico_b2g_score": 0.4,
    },
    "contract_concentration": {
        "auditoria_orcamento_score": 0.7,
        "acompanhamento_contratual_score": 0.5,
        "gestao_documental_score": 0.5,
        "diagnostico_b2g_score": 0.3,
    },
    "near_expiry": {
        # Near-equal spread across top buckets — removing this signal should
        # rarely flip the winner when other portfolio signals remain.
        "licitacoes_propostas_score": 0.55,
        "acompanhamento_contratual_score": 0.55,
        "gestao_documental_score": 0.5,
        "diagnostico_b2g_score": 0.5,
        "inteligencia_pncp_score": 0.35,
    },
    "addendum_recurrence": {
        "gestao_documental_score": 1.8,
        "acompanhamento_contratual_score": 0.6,
    },
    "adverse_event": {
        "auditoria_orcamento_score": 2.2,
        "gestao_documental_score": 0.9,
    },
    "diversity_increase": {
        "inteligencia_pncp_score": 1.7,
        "diagnostico_b2g_score": 0.8,
    },
    "win_recurrence": {
        "licitacoes_propostas_score": 1.9,
        "diagnostico_b2g_score": 0.8,
    },
}


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

    # Primary: signal-id weighted multi-bucket allocation (v3)
    for r in fired:
        contrib = float(r.contribution or 0.0)
        if contrib <= 0:
            continue
        weights = _SIGNAL_OFFER_WEIGHTS.get(r.signal_id)
        if weights:
            for bucket, w in weights.items():
                scores[bucket] += contrib * w
                support[bucket].append(r.signal_id)
        else:
            # Fallback: profile offer field
            offer = getattr(r, "offer", None) or (
                r.as_dict().get("offer") if hasattr(r, "as_dict") else None
            )
            bucket = _bucket_for_offer(offer)
            if bucket:
                scores[bucket] += contrib
                support[bucket].append(r.signal_id)
            else:
                scores["diagnostico_b2g_score"] += 0.2 * contrib
                support["diagnostico_b2g_score"].append(r.signal_id)

    # Composite offer_mappings from profile (soft boost — avoids single-signal monopoly)
    fired_ids = {r.signal_id for r in fired}
    mappings = list(profile.data.get("offer_mappings") or [])
    for m in mappings:
        needed = set(m.get("when_signals") or [])
        if not needed:
            continue
        if needed.issubset(fired_ids):
            bucket = _bucket_for_offer(m.get("offer"))
            if bucket:
                boost = OFFER_MAPPING_BASE_BOOST + OFFER_MAPPING_PER_SIGNAL_BOOST * len(
                    needed
                )
                scores[bucket] += boost
                support[bucket].append(f"mapping:{m.get('id')}")
        else:
            overlap = needed & fired_ids
            if overlap and len(overlap) < len(needed):
                contradict.append(f"partial_mapping:{m.get('id')}")

    # NC: dampen offers that depend on missing signals
    nc = [r for r in adjusted if r.status == SIGNAL_STATUS_NC]
    for r in nc:
        if r.signal_id in {"near_expiry", "concurrent_portfolio"}:
            scores["acompanhamento_contratual_score"] *= 0.8
            contradict.append(f"nc:{r.signal_id}")
        if r.signal_id in {"addendum_recurrence"}:
            scores["gestao_documental_score"] *= 0.8
            contradict.append(f"nc:{r.signal_id}")
        if r.signal_id in {"adverse_event"}:
            scores["auditoria_orcamento_score"] *= 0.8
            contradict.append(f"nc:{r.signal_id}")

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_key, top_val = ranked[0]
    alt_key, alt_val = ranked[1] if len(ranked) > 1 else (None, 0.0)
    margin = round(top_val - float(alt_val or 0.0), 4)

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
    """Population-level offer discrimination diagnostics.

    Uniform selected_offer is allowed only with robust quantitative justification:
    multi-offer score competition + large margin + non-degenerate score catalog.
    """
    offers: list[str] = []
    margins: list[float] = []
    alternatives: list[str] = []
    multi_score_positive = 0
    nonzero_buckets: set[str] = set()
    signal_dominance: Counter[str] = Counter()
    for item in leads:
        if isinstance(item, LeadScore):
            off = item.selected_offer or item.suggested_offer
            m = item.selected_offer_margin
            alt = item.alternative_offer
            scores = item.offer_scores or {}
            support = item.supporting_signals or []
        else:
            off = item.get("selected_offer") or item.get("suggested_offer")
            m = item.get("selected_offer_margin")
            alt = item.get("alternative_offer")
            scores = item.get("offer_scores") or {}
            support = item.get("supporting_signals") or []
        if off:
            offers.append(str(off))
        if alt:
            alternatives.append(str(alt))
        if m is not None:
            try:
                margins.append(float(m))
            except (TypeError, ValueError):
                pass
        pos_scores = [float(v) for v in scores.values() if float(v or 0) > 0]
        if len(pos_scores) >= 2:
            multi_score_positive += 1
        for k, v in scores.items():
            if float(v or 0) > 0:
                nonzero_buckets.add(str(k))
        for s in support:
            if isinstance(s, str) and not s.startswith("mapping:"):
                signal_dominance[s] += 1

    n = len(offers) or 1
    dist = dict(Counter(offers))
    rates = {k: round(v / n, 4) for k, v in dist.items()}
    dominant_offer = max(dist, key=dist.get) if dist else None  # type: ignore[arg-type]
    dominant_rate = rates.get(dominant_offer or "", 0.0)
    entropy = 0.0
    for c in dist.values():
        p = c / n
        if p > 0:
            entropy -= p * math.log2(p)
    mean_margin = round(sum(margins) / len(margins), 4) if margins else None
    low_margin = sum(1 for m in margins if m < 0.5)
    n_distinct_offers = len(dist)
    multi_score_rate = multi_score_positive / n if n else 0.0
    catalog_degenerate = len(nonzero_buckets) <= 1 and n >= 5
    # Robust: diversified winners, OR high margin + multi-bucket scores + alternatives
    robust = bool(
        dominant_rate <= 0.80
        or (
            mean_margin is not None
            and mean_margin >= 2.5
            and multi_score_rate >= 0.8
            and not catalog_degenerate
            and low_margin == 0
        )
    )
    if catalog_degenerate:
        robust = False
    block = None
    if dominant_rate > 0.80 and not robust:
        block = "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE"
    top_signals = [s for s, _ in signal_dominance.most_common(5)]
    explanation = {
        "dominant_offer": dominant_offer,
        "dominant_offer_rate": dominant_rate,
        "why_uniform": (
            "catalog_degenerate_single_score_bucket"
            if catalog_degenerate
            else (
                "active_engineering_suppliers_fire_portfolio_near_expiry_cluster"
                if dominant_rate > 0.80 and top_signals
                else "distribution has meaningful variation"
            )
        ),
        "dominant_supporting_signals": top_signals,
        "mean_selected_offer_margin": mean_margin,
        "alternative_offers_seen": dict(Counter(alternatives)),
        "multi_score_positive_rate": round(multi_score_rate, 4),
        "nonzero_score_buckets": sorted(nonzero_buckets),
        "catalog_degenerate": catalog_degenerate,
        "n_distinct_offers": n_distinct_offers,
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
