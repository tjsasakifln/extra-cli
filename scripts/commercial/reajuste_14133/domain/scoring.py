"""Explainable domain diagnostic scores for reajuste leads.

These are NOT operational activation ranks and NOT calibrated probabilities.

Honest field semantics (v3.1 domain-signals successor of #200):
  - opportunity_score → domain_signal_strength (heuristic commercial-pain signal)
  - verification_score → documentary_confidence (evidence quality)
  - commercial_fit_score → commercial_fit_features (ICP compatibility)
  - priority_score → diagnostic_work_order (local desk ordering only)

Operational who-to-work-now is owned exclusively by scripts/confenge_activation/.
This module must never publish a supplier_priority_queue as an executable hot set.

Missing docs reduce documentary_confidence, not domain_signal_strength.
Missing contact reduces contact readiness, not domain membership.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from scripts.commercial.reajuste_14133 import (
    CALCULABLE_ADJUSTMENT_CLAIM,
    DATA_BASE_CONFIRMED,
    DIAGNOSTIC_OUTREACH_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    RANKING_NACIONAL,
    RANKING_SUL_SC,
    STATUS_ALREADY_ADJUSTED,
    STATUS_CLOSED,
    STATUS_HOT_VERIFIED,
    STATUS_LEGAL_REGIME_UNKNOWN,
    STATUS_NOT_ELIGIBLE,
    STATUS_RESEARCH_REQUIRED,
    STATUS_REVIEW_REQUIRED,
    STATUS_STRONG_CANDIDATE,
    SUL_UFS,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)
from scripts.commercial.reajuste_14133.domain.dates import DateBundle
from scripts.commercial.reajuste_14133.domain.eligibility import EligibilityResult
from scripts.commercial.reajuste_14133.domain.finance import FinanceEstimate
from scripts.commercial.reajuste_14133.domain.obra_classifier import ConstructionClassification
from scripts.commercial.reajuste_14133.domain.regime import RegimeResult

WEIGHTS = {
    "confianca_juridica_documental": 0.25,
    "atratividade_financeira": 0.20,
    "urgencia_temporal": 0.15,
    "saldo_reajustavel_provavel": 0.15,
    "aderencia_icp_confenge": 0.10,
    "contatabilidade": 0.10,
    "qualidade_fontes": 0.05,
}


@dataclass
class ScoreBreakdown:
    # Legacy keys retained for report/test compatibility; not activation authority.
    score_total: float
    components: dict[str, float]
    penalties: dict[str, float]
    ranking_bucket: str
    notes: list[str] = field(default_factory=list)
    opportunity_score: float = 0.0  # alias: domain_signal_strength
    verification_score: float = 0.0  # alias: documentary_confidence
    commercial_fit_score: float = 0.0  # alias: commercial_fit_features
    priority_score: float = 0.0  # alias: diagnostic_work_order (NOT activation_score)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Honest aliases for downstream consumers / confenge_activation bridge.
        d["domain_signal_strength"] = self.opportunity_score
        d["documentary_confidence"] = self.verification_score
        d["commercial_fit_features"] = self.commercial_fit_score
        d["diagnostic_work_order"] = self.priority_score
        d["is_calibrated_probability"] = False
        d["is_operational_activation_rank"] = False
        return d


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _money(v: Decimal | float | None) -> float:
    if v is None:
        return 0.0
    return float(v)


def score_lead(
    *,
    eligibility: EligibilityResult,
    obra: ConstructionClassification,
    regime: RegimeResult,
    dates: DateBundle,
    finance: FinanceEstimate,
    uf: str | None,
    municipio: str | None = None,
    portfolio_hint_brl: float | None = None,
    contact_score: float = 0.0,
    source_freshness: float = 0.5,
    supplier_size_hint: str | None = None,
    is_giant_low_consulting_fit: bool = False,
    is_too_small_for_ticket: bool = False,
    has_personal_only_contact: bool = False,
    material_contradiction: bool = False,
    commercial_stage: str | None = None,
    minimum_interregnum_elapsed: bool | None = None,
    multi_contract_count: int = 1,
    regime_probable: bool = False,
) -> ScoreBreakdown:
    """Return decomposable score in [0, 100] plus v3 split scores."""
    notes: list[str] = []
    penalties: dict[str, float] = {}

    # 1) Legal / documentary (verification-heavy — does not erase opportunity)
    gate_frac = eligibility.hot_gates_passed / max(1, len(eligibility.hot_gates))
    legal = 0.35 * gate_frac
    if regime.proven and regime.regime.startswith("LEI_14133"):
        legal += 0.35
    elif regime.regime == "UNKNOWN" or regime_probable:
        legal += 0.12 if regime_probable else 0.05
    else:
        legal += 0.1
    if dates.data_base_status == DATA_BASE_CONFIRMED:
        legal += 0.15
    if finance.indice_contratual:
        legal += 0.15
    legal = _clamp(legal)

    # 2) Financial attractiveness — only VALUE_CONFIRMED/PLAUSIBLE may drive this
    pot = _money(finance.valor_potencial)
    teto = _money(finance.teto_teorico)
    total_v = _money(finance.valor_atualizado_aditivos)
    if portfolio_hint_brl is not None and portfolio_hint_brl <= 0 and pot <= 0:
        fin = 0.05
        notes.append("Atratividade financeira bloqueada: valor PNCP não validado/outlier.")
        penalties["valor_nao_validado"] = 0.15
    else:
        valor_ref = pot if pot > 0 else (
            teto * 0.25 if teto > 0 else total_v * 0.02
        )
        if valor_ref <= 0:
            fin = 0.15
        else:
            fin = _clamp((valor_ref / 500_000) ** 0.5 * 0.7 + 0.15)
        if finance.base_label == "UPPER_BOUND_NOT_CLAIM_VALUE":
            fin *= 0.55
            notes.append("Atratividade descontada: apenas teto teórico (UPPER_BOUND).")

    # 3) Temporal urgency — conservative minimum interregnum counts for opportunity
    urg = 0.2
    mature = bool(dates.interregno_completo) or bool(minimum_interregnum_elapsed)
    if mature:
        days = dates.dias_desde_reajuste_aplicavel or 0
        if minimum_interregnum_elapsed and not dates.interregno_completo:
            days = max(days, 30)
        urg = _clamp(0.4 + min(0.5, max(0, days) / 730))
        notes.append("Urgência temporal: interregno conservador ou exato completo.")
    if dates.dias_restantes_vigencia is not None:
        if 0 <= dates.dias_restantes_vigencia <= 90:
            urg = _clamp(urg + 0.15)
            notes.append("Urgência: vigência termina em ≤90 dias.")
        elif dates.dias_restantes_vigencia < 0:
            urg *= 0.4
            penalties["vigencia_encerrada"] = 0.1

    # 4) Probable reajustable balance
    saldo = 0.15
    if finance.base_label in {"SALDO_CONTRATUAL", "SALDO_DERIVADO"}:
        saldo = 0.85
    elif finance.base_label == "UPPER_BOUND_NOT_CLAIM_VALUE":
        saldo = 0.4
    elif finance.base_label == "EXHAUSTED_OR_FULLY_MEASURED":
        saldo = 0.0

    # 5) ICP CONFENGE — PME construction, Sul/SC boost, material ticket
    icp = 0.35 * obra.confidence
    u = (uf or "").upper()
    if u == "SC":
        icp += 0.35
    elif u in SUL_UFS:
        icp += 0.25
    else:
        icp += 0.1
    ticket = portfolio_hint_brl or _money(finance.valor_atualizado_aditivos)
    if 1_000_000 <= ticket <= 80_000_000:
        icp += 0.25
    elif ticket > 80_000_000:
        icp += 0.1
        notes.append("Ticket muito alto — avaliar fit de consultoria externa.")
    elif ticket >= 500_000:
        icp += 0.15
    icp = _clamp(icp)

    # 6) Contactability — does NOT zero opportunity
    cont = _clamp(float(contact_score))

    # 7) Source quality
    qual = _clamp(float(source_freshness))
    if eligibility.hot_gates.get("documentos_acessiveis"):
        qual = _clamp(qual + 0.2)

    components = {
        "confianca_juridica_documental": round(legal, 4),
        "atratividade_financeira": round(fin, 4),
        "urgencia_temporal": round(urg, 4),
        "saldo_reajustavel_provavel": round(saldo, 4),
        "aderencia_icp_confenge": round(icp, 4),
        "contatabilidade": round(cont, 4),
        "qualidade_fontes": round(qual, 4),
    }

    raw = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)

    # Penalties — verification-oriented; missing data-base/index do NOT wipe opportunity
    if not regime.proven and not regime_probable:
        penalties["regime_nao_confirmado"] = 0.05
    # Missing data-base/index: tracked in verification_score, light legacy penalty only
    if dates.data_base_status != DATA_BASE_CONFIRMED:
        penalties["data_base_ausente"] = 0.02
        notes.append("Data-base exata ausente: reduz verification_score, não opportunity.")
    if not finance.indice_contratual:
        penalties["indice_ausente"] = 0.02
    if dates.dias_restantes_vigencia is not None and 0 <= dates.dias_restantes_vigencia <= 60:
        if not eligibility.hot_gates.get("documentos_acessiveis"):
            penalties["encerramento_proximo_sem_docs"] = 0.05
    if eligibility.status == STATUS_CLOSED:
        penalties["execucao_concluida"] = 0.25
    if eligibility.status == STATUS_ALREADY_ADJUSTED:
        penalties["reajuste_publicado"] = 0.3
    if material_contradiction:
        penalties["dados_contraditorios"] = 0.12
    if is_giant_low_consulting_fit or supplier_size_hint == "giant":
        penalties["fornecedor_gigante_baixa_prob_consultoria"] = 0.1
    if is_too_small_for_ticket or supplier_size_hint == "micro_vs_ticket":
        penalties["fornecedor_pequeno_vs_complexidade"] = 0.06
    if has_personal_only_contact:
        penalties["contato_apenas_pessoal"] = 0.02

    # Status floors — LEGAL_REGIME_UNKNOWN no longer crushes commercial opportunity
    status_mult = {
        STATUS_HOT_VERIFIED: 1.0,
        STATUS_STRONG_CANDIDATE: 0.95,
        STATUS_REVIEW_REQUIRED: 0.85,
        STATUS_RESEARCH_REQUIRED: 0.75,
        STATUS_LEGAL_REGIME_UNKNOWN: 0.80,
        STATUS_ALREADY_ADJUSTED: 0.15,
        STATUS_CLOSED: 0.1,
        STATUS_NOT_ELIGIBLE: 0.05,
    }.get(eligibility.status, 0.6)

    stage_boost = {
        CALCULABLE_ADJUSTMENT_CLAIM: 1.05,
        VERIFIED_ADJUSTMENT_OPPORTUNITY: 1.0,
        DIAGNOSTIC_OUTREACH_READY: 0.98,
        LIKELY_ADJUSTMENT_OPPORTUNITY: 0.95,
        POTENTIAL_ADJUSTMENT_SIGNAL: 0.75,
    }.get(commercial_stage or "", 1.0)

    penalty_sum = sum(penalties.values())
    final01 = _clamp((raw - penalty_sum) * status_mult * min(1.0, stage_boost))
    score = round(final01 * 100, 2)

    # --- v3 split scores (0–100) ---
    # Opportunity: pain signals independent of documentary completeness
    opp = 0.15
    if obra.is_construction:
        opp += 0.25 * _clamp(obra.confidence)
    if mature:
        opp += 0.25
    if regime.proven or regime_probable:
        opp += 0.15
    elif regime.regime.startswith("LEI_14133"):
        opp += 0.08
    if finance.base_label != "EXHAUSTED_OR_FULLY_MEASURED":
        opp += 0.1
    if ticket >= 1_000_000:
        opp += 0.1
    if multi_contract_count >= 2:
        opp += min(0.1, 0.03 * multi_contract_count)
    if material_contradiction:
        opp -= 0.15
    if is_giant_low_consulting_fit:
        opp -= 0.08
    opportunity_score = round(_clamp(opp) * 100, 2)

    # Verification: evidence quality
    ver = 0.05
    ver += 0.25 * gate_frac
    if dates.data_base_status == DATA_BASE_CONFIRMED:
        ver += 0.2
    if finance.indice_contratual:
        ver += 0.15
    if eligibility.hot_gates.get("documentos_acessiveis"):
        ver += 0.15
    if regime.proven:
        ver += 0.15
    if commercial_stage in {VERIFIED_ADJUSTMENT_OPPORTUNITY, CALCULABLE_ADJUSTMENT_CLAIM}:
        ver += 0.1
    verification_score = round(_clamp(ver) * 100, 2)

    commercial_fit_score = round(icp * 100, 2)

    # Priority: order human work — opportunity + fit + materiality + Sul; contact is bonus
    pri = (
        0.40 * (opportunity_score / 100)
        + 0.25 * (commercial_fit_score / 100)
        + 0.15 * (verification_score / 100)
        + 0.10 * fin
        + 0.10 * cont
    )
    if u in SUL_UFS:
        pri = _clamp(pri + 0.05)
    if u == "SC":
        pri = _clamp(pri + 0.03)
    priority_score = round(_clamp(pri) * 100, 2)

    # Prefer priority_score as operational ranking when commercial stage is set
    if commercial_stage:
        score = priority_score

    ranking = RANKING_NACIONAL
    if u in SUL_UFS:
        ranking = RANKING_SUL_SC

    return ScoreBreakdown(
        score_total=score,
        components=components,
        penalties={k: round(v, 4) for k, v in penalties.items()},
        ranking_bucket=ranking,
        notes=notes,
        opportunity_score=opportunity_score,
        verification_score=verification_score,
        commercial_fit_score=commercial_fit_score,
        priority_score=priority_score,
    )


def rank_leads(leads: list[dict[str, Any]], *, ranking: str | None = None) -> list[dict[str, Any]]:
    """Deterministic rank: priority_score desc, opportunity desc, valor desc, id asc.

    valor_potencial is not used for ranking (only CALCULABLE may carry it).
    """
    filtered = leads
    if ranking == RANKING_SUL_SC:
        filtered = [lead for lead in leads if (lead.get("uf") or "").upper() in SUL_UFS]
    elif ranking == RANKING_NACIONAL:
        filtered = list(leads)

    def key(lead: dict[str, Any]) -> tuple:
        return (
            -float(lead.get("priority_score") or lead.get("score_total") or 0),
            -float(lead.get("opportunity_score") or 0),
            -float(
                lead.get("teto_teorico")
                or lead.get("valor_atualizado")
                or lead.get("valor_original")
                or 0
            ),
            str(lead.get("contrato_id") or ""),
        )

    ordered = sorted(filtered, key=key)
    for i, lead in enumerate(ordered, start=1):
        lead = dict(lead)
        lead["ranking"] = i
        if ranking:
            lead["ranking_scope"] = ranking
        ordered[i - 1] = lead
    return ordered
