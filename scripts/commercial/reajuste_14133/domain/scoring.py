"""Explainable commercial scoring for reajuste leads.

Weights (objective §8):
  25% legal/documentary confidence
  20% financial attractiveness
  15% temporal urgency
  15% probable reajustable balance
  10% CONFENGE ICP fit
  10% business contactability
   5% source quality/freshness
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
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
    score_total: float
    components: dict[str, float]
    penalties: dict[str, float]
    ranking_bucket: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
) -> ScoreBreakdown:
    """Return decomposable score in [0, 100]."""
    notes: list[str] = []
    penalties: dict[str, float] = {}

    # 1) Legal / documentary
    gate_frac = eligibility.hot_gates_passed / max(1, len(eligibility.hot_gates))
    legal = 0.35 * gate_frac
    if regime.proven and regime.regime.startswith("LEI_14133"):
        legal += 0.35
    elif regime.regime == "UNKNOWN":
        legal += 0.05
    else:
        legal += 0.1
    if dates.data_base_status == DATA_BASE_CONFIRMED:
        legal += 0.15
    if finance.indice_contratual:
        legal += 0.15
    legal = _clamp(legal)

    # 2) Financial attractiveness — only VALUE_CONFIRMED/PLAUSIBLE may drive this
    # Callers pass portfolio_hint_brl=0 when value quality blocks financial use.
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
        # scale: R$50k → ~0.3, R$500k → ~0.7, R$2M+ → ~1.0
        if valor_ref <= 0:
            fin = 0.15
        else:
            fin = _clamp((valor_ref / 500_000) ** 0.5 * 0.7 + 0.15)
        if finance.base_label == "UPPER_BOUND_NOT_CLAIM_VALUE":
            fin *= 0.55
            notes.append("Atratividade descontada: apenas teto teórico (UPPER_BOUND).")

    # 3) Temporal urgency
    urg = 0.2
    if dates.interregno_completo:
        days = dates.dias_desde_reajuste_aplicavel or 0
        urg = _clamp(0.4 + min(0.5, max(0, days) / 730))
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

    # 6) Contactability
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

    # Penalties (absolute score points on 0-1 scale before *100)
    if not regime.proven:
        penalties["regime_nao_confirmado"] = 0.08
    if dates.data_base_status != DATA_BASE_CONFIRMED:
        penalties["data_base_ausente"] = 0.07
    if not finance.indice_contratual:
        penalties["indice_ausente"] = 0.07
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
        penalties["contato_apenas_pessoal"] = 0.04

    # Status floors / ceilings
    status_mult = {
        STATUS_HOT_VERIFIED: 1.0,
        STATUS_STRONG_CANDIDATE: 0.92,
        STATUS_REVIEW_REQUIRED: 0.75,
        STATUS_RESEARCH_REQUIRED: 0.55,
        STATUS_LEGAL_REGIME_UNKNOWN: 0.65,
        STATUS_ALREADY_ADJUSTED: 0.15,
        STATUS_CLOSED: 0.1,
        STATUS_NOT_ELIGIBLE: 0.05,
    }.get(eligibility.status, 0.5)

    penalty_sum = sum(penalties.values())
    final01 = _clamp((raw - penalty_sum) * status_mult)
    score = round(final01 * 100, 2)

    ranking = RANKING_NACIONAL
    if u in SUL_UFS:
        ranking = RANKING_SUL_SC

    return ScoreBreakdown(
        score_total=score,
        components=components,
        penalties={k: round(v, 4) for k, v in penalties.items()},
        ranking_bucket=ranking,
        notes=notes,
    )


def rank_leads(leads: list[dict[str, Any]], *, ranking: str | None = None) -> list[dict[str, Any]]:
    """Deterministic rank: score desc, valor desc, contrato_id asc."""
    filtered = leads
    if ranking == RANKING_SUL_SC:
        filtered = [lead for lead in leads if (lead.get("uf") or "").upper() in SUL_UFS]
    elif ranking == RANKING_NACIONAL:
        filtered = list(leads)

    def key(lead: dict[str, Any]) -> tuple:
        return (
            -float(lead.get("score_total") or 0),
            -float(lead.get("valor_potencial") or lead.get("teto_teorico") or lead.get("valor_atualizado") or 0),
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
