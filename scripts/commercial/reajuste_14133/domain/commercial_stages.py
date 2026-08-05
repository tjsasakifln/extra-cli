"""Commercial funnel stages and independent confidence dimensions.

Separates three questions that must not collapse into one binary:

1. Is there a commercial signal of possible unanalysed annual reajuste?
2. Is it safe enough to offer a *diagnostic* conversation?
3. Is documentary proof sufficient to assert a due claim and a value?

Fail-closed applies only to conclusive claims, potential values and protocol
recommendations — never to erase genuine commercial leads.

Legal regime: year/PNCP never elevates legal_confidence or LIKELY_14133.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from scripts.commercial.reajuste_14133 import (
    ADJUSTMENT_HISTORY_CONFLICT,
    CALCULABLE_ADJUSTMENT_CLAIM,
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_READY,
    LEGAL_CONF_CONFLICT,
    LEGAL_CONF_HIGH,
    LEGAL_CONF_MEDIUM,
    LEGAL_CONF_NONE,
    LEGAL_CONF_UNRESOLVED,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    NO_PRIOR_ADJUSTMENT_LOCATED,
    PARTIAL_ADJUSTMENT_CONFIRMED,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    PRIOR_ADJUSTMENT_CONFIRMED,
    REGIME_10520,
    REGIME_14133,
    REGIME_8666,
    REGIME_CONFLICT,
    REGIME_LIKELY_14133,
    REGIME_RDC,
    REGIME_TRANSITIONAL_UNRESOLVED,
    REGIME_UNKNOWN,
    TEMPORAL_LEVEL_A,
    TEMPORAL_LEVEL_B,
    TEMPORAL_LEVEL_C,
    TEMPORAL_LEVEL_D,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)

_LEGACY_REGIMES = frozenset({REGIME_8666, REGIME_RDC, REGIME_10520})

# Confidence labels
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"
CONF_NONE = "none"
CONF_CONSERVATIVE = "conservative_confirmed"
CONF_PROXY = "proxy_probable"
CONF_INSUFFICIENT = "insufficient"
CONF_UNRESOLVED = "unresolved"
CONF_CONFLICT = "conflict"

HUMAN_REVIEW_PENDING = "human_review_pending"
HUMAN_REVIEW_COMPLETED = "human_review_completed"
HUMAN_REVIEW_INCOMPLETE = "human_review_incomplete"
HUMAN_REVIEW_NONE = "human_review_none"

CLAIM_BLOCKED = "claim_blocked"
CLAIM_READY = "claim_ready"
CLAIM_CALCULABLE = "claim_calculable"

ACTION_ENRICH_CONTACT = "enrich_contact"
ACTION_REQUEST_DOCS = "request_documents"
ACTION_REQUEST_LEGAL_REGIME_DOCS = "request_legal_regime_documents"
ACTION_DIAGNOSTIC_OUTREACH = "diagnostic_outreach"
ACTION_HUMAN_REVIEW = "human_documentary_review"
ACTION_STRUCTURE_CLAIM = "structure_claim"
ACTION_INTEL_ONLY = "intelligence_only"
ACTION_EXCLUDE = "exclude"

# --- Message templates by regime confidence (section 5) ---

MSG_REGIME_PROVEN = (
    "Identificamos contrato de obra regido pela Lei 14.133 com interregno anual "
    "potencialmente transcorrido. Isso não significa, por si só, existência de "
    "valor pendente, mas justifica conferir cláusula, data-base, medições e "
    "reajustes aplicados."
)

MSG_REGIME_LIKELY = (
    "Os documentos disponíveis indicam possível enquadramento na Lei 14.133 e "
    "maturidade anual do contrato. Recomendamos confirmar o regime, a cláusula, "
    "a data-base e o histórico de reajustes antes de qualquer conclusão."
)

MSG_REGIME_UNRESOLVED = (
    "Identificamos contrato de obra com possível maturidade anual. Para avaliar "
    "eventual reajuste, é necessário confirmar o regime jurídico da contratação, "
    "a cláusula aplicável, a data-base e os reajustes já processados."
)

# Back-compat alias used by tests
DIAGNOSTIC_LANGUAGE = MSG_REGIME_PROVEN

PROHIBITED_CLAIM_LANGUAGE = (
    "Não afirmar valor devido, inadimplemento, crédito constituído ou "
    "reajuste definitivamente não pago sem verificação documental completa "
    "e revisão humana registrada."
)

DOCUMENT_REQUEST_LANGUAGE = (
    "Solicitamos cópia do edital, aviso de licitação, termo de referência/"
    "projeto básico, contrato, ato de autorização, parecer jurídico e "
    "fundamento legal do processo, bem como medições, apostilas e memória "
    "de reajuste, para identificar o regime jurídico aplicável, a cláusula, "
    "a data-base, o índice e reajustes anteriores. Não há, neste momento, "
    "afirmação de crédito pendente ou de legislação aplicável."
)

PRIORITY_REGIME_DOCUMENTS = (
    "edital",
    "aviso_de_licitacao",
    "termo_de_referencia",
    "projeto_basico",
    "contrato",
    "ato_de_autorizacao",
    "parecer_juridico",
    "fundamento_legal_no_processo",
    "numero_e_ano_contratacao_originaria",
    "clausula_reajuste",
    "data_base_orcamento_estimado",
    "indice_ou_formula",
    "medicoes",
    "apostilas",
    "memoria_reajuste",
)


@dataclass
class TemporalEvidence:
    """Hierarchy A–D of temporal evidence (never confuses proxy with legal data-base)."""

    level: str
    exact_budget_date: date | None
    proxy_date: date | None
    proxy_type: str | None
    minimum_elapsed_confirmed: bool
    temporal_confidence: str
    calculation_blocked: bool
    diagnostic_outreach_allowed: bool
    interregno_complete_exact: bool
    temporal_reasoning: str
    days_since_signature: int | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.exact_budget_date:
            d["exact_budget_date"] = self.exact_budget_date.isoformat()
        if self.proxy_date:
            d["proxy_date"] = self.proxy_date.isoformat()
        return d


@dataclass
class CommercialDimensions:
    signal_status: str
    legal_confidence: str
    temporal_confidence: str
    documentary_confidence: str
    execution_confidence: str
    adjustment_history_confidence: str
    contact_readiness: str
    human_review_status: str
    commercial_action: str
    claim_readiness: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommercialStageResult:
    commercial_stage: str
    dimensions: CommercialDimensions
    temporal: TemporalEvidence
    regime_probable_14133: bool
    language_allowed: str
    prohibited_language: str
    next_action: str
    missing_documents: list[str] = field(default_factory=list)
    favorable_signals: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    valor_potencial_allowed: bool = False
    diagnostic_outreach_allowed: bool = False
    reasons: list[str] = field(default_factory=list)
    # Legacy outreach mapping (for gradual migration)
    outreach_status_legacy: str = "NOT_READY_FOR_OUTREACH"
    message_template: str = "unresolved"

    def as_dict(self) -> dict[str, Any]:
        return {
            "commercial_stage": self.commercial_stage,
            "dimensions": self.dimensions.as_dict(),
            "temporal": self.temporal.as_dict(),
            "regime_probable_14133": self.regime_probable_14133,
            "language_allowed": self.language_allowed,
            "prohibited_language": self.prohibited_language,
            "next_action": self.next_action,
            "missing_documents": self.missing_documents,
            "favorable_signals": self.favorable_signals,
            "uncertainties": self.uncertainties,
            "valor_potencial_allowed": self.valor_potencial_allowed,
            "diagnostic_outreach_allowed": self.diagnostic_outreach_allowed,
            "reasons": self.reasons,
            "outreach_status_legacy": self.outreach_status_legacy,
            "message_template": self.message_template,
        }


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def evaluate_temporal_hierarchy(
    *,
    as_of: date,
    exact_budget_date: date | None = None,
    data_assinatura: date | None = None,
    data_publicacao: date | None = None,
    inicio_vigencia: date | None = None,
    ultimo_reajuste: date | None = None,
) -> TemporalEvidence:
    """Explicit temporal levels A–D.

    Level B (signature > 12 months): budget date cannot post-date signature
    (unless documentary inconsistency). Therefore the first annual interregnum
    has elapsed conservatively even without exact orçamento date. Calculation
    remains blocked; diagnostic outreach is allowed only when regime permits.
    """
    if exact_budget_date is not None:
        ref = ultimo_reajuste or exact_budget_date
        first_due = add_years(ref, 1)
        elapsed = as_of >= first_due
        return TemporalEvidence(
            level=TEMPORAL_LEVEL_A,
            exact_budget_date=exact_budget_date,
            proxy_date=data_assinatura or inicio_vigencia or data_publicacao,
            proxy_type=(
                "data_assinatura"
                if data_assinatura
                else (
                    "inicio_vigencia"
                    if inicio_vigencia
                    else ("data_publicacao" if data_publicacao else None)
                )
            ),
            minimum_elapsed_confirmed=elapsed,
            temporal_confidence=CONF_HIGH if elapsed else CONF_MEDIUM,
            calculation_blocked=not elapsed,
            diagnostic_outreach_allowed=elapsed,
            interregno_complete_exact=elapsed,
            temporal_reasoning=(
                "Data-base exata do orçamento estimado localizada; "
                + (
                    "interregno anual confirmado com precisão."
                    if elapsed
                    else "interregno anual ainda incompleto na data-base exata."
                )
            ),
            days_since_signature=(
                (as_of - data_assinatura).days if data_assinatura else None
            ),
        )

    if data_assinatura is not None:
        days_sig = (as_of - data_assinatura).days
        if days_sig >= 365:
            return TemporalEvidence(
                level=TEMPORAL_LEVEL_B,
                exact_budget_date=None,
                proxy_date=data_assinatura,
                proxy_type="data_assinatura",
                minimum_elapsed_confirmed=True,
                temporal_confidence=CONF_CONSERVATIVE,
                calculation_blocked=True,
                diagnostic_outreach_allowed=True,
                interregno_complete_exact=False,
                temporal_reasoning=(
                    f"Assinatura em {data_assinatura.isoformat()} há {days_sig} dias "
                    f"(≥365). O orçamento estimado necessariamente antecede a "
                    f"contratação; portanto o primeiro interregno anual já "
                    f"transcorreu de forma conservadora. Data-base exata ausente — "
                    f"cálculo bloqueado; diagnóstico comercial condicionado ao regime."
                ),
                days_since_signature=days_sig,
            )
        return TemporalEvidence(
            level=TEMPORAL_LEVEL_D,
            exact_budget_date=None,
            proxy_date=data_assinatura,
            proxy_type="data_assinatura",
            minimum_elapsed_confirmed=False,
            temporal_confidence=CONF_INSUFFICIENT,
            calculation_blocked=True,
            diagnostic_outreach_allowed=False,
            interregno_complete_exact=False,
            temporal_reasoning=(
                f"Assinatura em {data_assinatura.isoformat()} há apenas {days_sig} dias "
                f"(<365). Sem data-base exata, não há evidência conservadora de "
                f"interregno anual completo."
            ),
            days_since_signature=days_sig,
        )

    for val, ptype in (
        (inicio_vigencia, "inicio_vigencia"),
        (data_publicacao, "data_publicacao"),
    ):
        if val is None:
            continue
        days = (as_of - val).days
        if days >= 365:
            return TemporalEvidence(
                level=TEMPORAL_LEVEL_C,
                exact_budget_date=None,
                proxy_date=val,
                proxy_type=ptype,
                minimum_elapsed_confirmed=False,
                temporal_confidence=CONF_PROXY,
                calculation_blocked=True,
                diagnostic_outreach_allowed=False,
                interregno_complete_exact=False,
                temporal_reasoning=(
                    f"Marco {ptype}={val.isoformat()} há {days} dias sem assinatura "
                    f"confiável. Oportunidade de menor confiança temporal; não "
                    f"apresentar o proxy como data-base legal."
                ),
                days_since_signature=None,
            )

    return TemporalEvidence(
        level=TEMPORAL_LEVEL_D,
        exact_budget_date=None,
        proxy_date=None,
        proxy_type=None,
        minimum_elapsed_confirmed=False,
        temporal_confidence=CONF_INSUFFICIENT,
        calculation_blocked=True,
        diagnostic_outreach_allowed=False,
        interregno_complete_exact=False,
        temporal_reasoning=(
            "Nenhum marco temporal permite inferência conservadora de interregno anual."
        ),
    )


def regime_probable_14133(
    *,
    regime: str,
    regime_proven: bool,
    signature_year: int | None = None,  # accepted but NEVER used to elevate
    object_mentions_14133: bool = False,  # never elevates alone
    legal_confidence: str | None = None,
) -> bool:
    """True only for proven LEI_14133 (R-A) or LIKELY_14133 (R-B).

    Signature year and object-only mentions must not return True.
    """
    del signature_year, object_mentions_14133  # explicit: not evidence of regime
    if regime == REGIME_14133 and regime_proven:
        return True
    if regime == REGIME_LIKELY_14133:
        return True
    if legal_confidence == LEGAL_CONF_HIGH and regime == REGIME_14133:
        return True
    if legal_confidence == LEGAL_CONF_MEDIUM and regime == REGIME_LIKELY_14133:
        return True
    return False


# Deprecated name kept for any external imports
_regime_probable_14133 = regime_probable_14133


def select_message_template(
    *,
    regime: str,
    regime_proven: bool,
    regime_probable: bool,
) -> tuple[str, str]:
    """Return (template_key, message body) by regime evidence level."""
    if regime == REGIME_14133 and regime_proven:
        return "proven", MSG_REGIME_PROVEN
    if regime == REGIME_LIKELY_14133 or (regime_probable and not regime_proven):
        return "likely", MSG_REGIME_LIKELY
    return "unresolved", MSG_REGIME_UNRESOLVED


def _legal_confidence_for_regime(
    *,
    regime: str,
    regime_proven: bool,
    legal_confidence_in: str | None = None,
) -> str:
    if legal_confidence_in:
        return legal_confidence_in
    if regime == REGIME_CONFLICT:
        return CONF_CONFLICT
    if regime == REGIME_TRANSITIONAL_UNRESOLVED:
        return CONF_UNRESOLVED
    if regime == REGIME_14133 and regime_proven:
        return CONF_HIGH
    if regime == REGIME_LIKELY_14133:
        return CONF_MEDIUM
    if regime == REGIME_UNKNOWN:
        return CONF_NONE
    if regime == REGIME_14133 and not regime_proven:
        # Object-only or unproven — do not treat as medium/probable
        return CONF_LOW
    # Proven legacy regimes
    if regime_proven:
        return CONF_HIGH
    return CONF_NONE


def evaluate_commercial_stage(
    *,
    as_of: date,
    is_construction: bool,
    obra_confidence: float = 0.0,
    private_supplier: bool,
    regime: str,
    regime_proven: bool,
    signature_year: int | None = None,
    object_mentions_14133: bool = False,
    legal_confidence: str | None = None,
    exact_budget_date: date | None = None,
    data_assinatura: date | None = None,
    data_publicacao: date | None = None,
    inicio_vigencia: date | None = None,
    ultimo_reajuste: date | None = None,
    is_closed: bool = False,
    open_obligation: bool = True,
    fully_liquidated: bool = False,
    adjustment_history: str = NO_PRIOR_ADJUSTMENT_LOCATED,
    clause_located: bool = False,
    index_or_formula: bool = False,
    docs_text_extracted: bool = False,
    document_link_validated: bool = False,
    material_contradiction: bool = False,
    legal_regime_conflict: bool = False,
    contact_verifiable: bool = False,
    contact_confidence: str | None = None,
    human_review_done: bool = False,
    has_calculable_base: bool = False,
    has_index_series: bool = False,
    value_plausible: bool = True,
    icp_compatible: bool = True,
) -> CommercialStageResult:
    """Classify commercial stage + independent dimensions (fail-closed on claims only)."""
    temporal = evaluate_temporal_hierarchy(
        as_of=as_of,
        exact_budget_date=exact_budget_date,
        data_assinatura=data_assinatura,
        data_publicacao=data_publicacao,
        inicio_vigencia=inicio_vigencia,
        ultimo_reajuste=ultimo_reajuste,
    )

    favorable: list[str] = []
    uncertainties: list[str] = []
    missing_docs: list[str] = []
    reasons: list[str] = []

    if not private_supplier:
        dims = CommercialDimensions(
            signal_status="none",
            legal_confidence=CONF_NONE,
            temporal_confidence=temporal.temporal_confidence,
            documentary_confidence=CONF_NONE,
            execution_confidence=CONF_NONE,
            adjustment_history_confidence=CONF_NONE,
            contact_readiness=CONF_NONE,
            human_review_status=HUMAN_REVIEW_NONE,
            commercial_action=ACTION_EXCLUDE,
            claim_readiness=CLAIM_BLOCKED,
        )
        return CommercialStageResult(
            commercial_stage="NOT_COMMERCIAL",
            dimensions=dims,
            temporal=temporal,
            regime_probable_14133=False,
            language_allowed="none",
            prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
            next_action="Excluir — fornecedor privado não identificável.",
            reasons=["fornecedor_nao_privado"],
            outreach_status_legacy="NOT_READY_FOR_OUTREACH",
        )

    if not is_construction or obra_confidence < 0.45:
        dims = CommercialDimensions(
            signal_status="none",
            legal_confidence=CONF_NONE,
            temporal_confidence=temporal.temporal_confidence,
            documentary_confidence=CONF_NONE,
            execution_confidence=CONF_NONE,
            adjustment_history_confidence=CONF_NONE,
            contact_readiness=CONF_NONE,
            human_review_status=HUMAN_REVIEW_NONE,
            commercial_action=ACTION_EXCLUDE,
            claim_readiness=CLAIM_BLOCKED,
        )
        return CommercialStageResult(
            commercial_stage="NOT_COMMERCIAL",
            dimensions=dims,
            temporal=temporal,
            regime_probable_14133=False,
            language_allowed="none",
            prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
            next_action="Excluir — objeto fora do escopo de obra/engenharia.",
            reasons=["objeto_nao_obra"],
            outreach_status_legacy="NOT_READY_FOR_OUTREACH",
        )

    if fully_liquidated or (is_closed and not open_obligation):
        dims = CommercialDimensions(
            signal_status="closed",
            legal_confidence=CONF_LOW,
            temporal_confidence=temporal.temporal_confidence,
            documentary_confidence=CONF_LOW,
            execution_confidence="closed",
            adjustment_history_confidence=CONF_LOW,
            contact_readiness=CONF_LOW,
            human_review_status=HUMAN_REVIEW_NONE,
            commercial_action=ACTION_INTEL_ONLY,
            claim_readiness=CLAIM_BLOCKED,
        )
        return CommercialStageResult(
            commercial_stage="NOT_COMMERCIAL",
            dimensions=dims,
            temporal=temporal,
            regime_probable_14133=False,
            language_allowed="none",
            prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
            next_action="Contrato encerrado/liquidado — inteligência apenas.",
            reasons=["contrato_encerrado_ou_liquidado"],
            outreach_status_legacy="NOT_READY_FOR_OUTREACH",
        )

    if adjustment_history == PRIOR_ADJUSTMENT_CONFIRMED:
        dims = CommercialDimensions(
            signal_status="already_adjusted",
            legal_confidence=CONF_MEDIUM,
            temporal_confidence=temporal.temporal_confidence,
            documentary_confidence=CONF_MEDIUM,
            execution_confidence=CONF_MEDIUM,
            adjustment_history_confidence=CONF_HIGH,
            contact_readiness=CONF_LOW,
            human_review_status=HUMAN_REVIEW_NONE,
            commercial_action=ACTION_INTEL_ONLY,
            claim_readiness=CLAIM_BLOCKED,
        )
        return CommercialStageResult(
            commercial_stage="NOT_COMMERCIAL",
            dimensions=dims,
            temporal=temporal,
            regime_probable_14133=regime_probable_14133(
                regime=regime,
                regime_proven=regime_proven,
                signature_year=signature_year,
                object_mentions_14133=object_mentions_14133,
            ),
            language_allowed="none",
            prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
            next_action="Evidência de reajuste integral do período — não abordar como crédito aberto.",
            reasons=["prior_adjustment_confirmed"],
            uncertainties=["verificar se reajuste foi integral ou parcial"],
            outreach_status_legacy="NOT_READY_FOR_OUTREACH",
        )

    favorable.append(f"obra_classificada_conf={obra_confidence:.2f}")
    if private_supplier:
        favorable.append("fornecedor_privado")
    if open_obligation:
        favorable.append("obrigacao_financeira_potencialmente_aberta")

    probable = regime_probable_14133(
        regime=regime,
        regime_proven=regime_proven,
        signature_year=signature_year,
        object_mentions_14133=object_mentions_14133,
        legal_confidence=legal_confidence,
    )
    legal_conf = _legal_confidence_for_regime(
        regime=regime,
        regime_proven=regime_proven,
        legal_confidence_in=legal_confidence,
    )

    if regime_proven and regime == REGIME_14133:
        favorable.append("regime_14133_comprovado")
    elif regime == REGIME_LIKELY_14133 or (probable and not regime_proven):
        favorable.append("regime_14133_fortemente_indicado_r_b")
        uncertainties.append(
            "Regime LIKELY_14133 por evidências oficiais convergentes — não comprovado"
        )
    elif regime == REGIME_TRANSITIONAL_UNRESOLVED:
        uncertainties.append("transitional_regime_unresolved")
        favorable.append("regime_transicao_requer_documentos")
    elif regime == REGIME_CONFLICT or legal_regime_conflict:
        uncertainties.append("regime_conflito_documental")
    elif regime == REGIME_UNKNOWN:
        uncertainties.append("regime_juridico_desconhecido")
    elif not probable:
        uncertainties.append("regime_juridico_nao_comprovado_14133")

    if temporal.level == TEMPORAL_LEVEL_A and temporal.minimum_elapsed_confirmed:
        favorable.append("interregno_exato_confirmado")
    elif temporal.level == TEMPORAL_LEVEL_B and temporal.minimum_elapsed_confirmed:
        favorable.append("interregno_conservador_por_assinatura_gt_12m")
        uncertainties.append(
            "data-base exata do orçamento ausente — cálculo preciso bloqueado"
        )
    elif temporal.level == TEMPORAL_LEVEL_C:
        favorable.append("marco_temporal_proxy_antigo")
        uncertainties.append("sem assinatura confiável — confiança temporal reduzida")
    else:
        uncertainties.append("maturidade_temporal_insuficiente")

    doc_bits = sum(
        [
            bool(clause_located),
            bool(exact_budget_date),
            bool(index_or_formula),
            bool(docs_text_extracted),
            bool(document_link_validated),
        ]
    )
    if doc_bits >= 4:
        doc_conf = CONF_HIGH
    elif doc_bits >= 2:
        doc_conf = CONF_MEDIUM
    elif doc_bits >= 1:
        doc_conf = CONF_LOW
    else:
        doc_conf = CONF_NONE

    if regime in {REGIME_UNKNOWN, REGIME_TRANSITIONAL_UNRESOLVED, REGIME_CONFLICT}:
        missing_docs.extend(PRIORITY_REGIME_DOCUMENTS)
    if not clause_located:
        missing_docs.append("clausula_reajuste")
    if not exact_budget_date:
        missing_docs.append("data_base_orcamento_estimado")
    if not index_or_formula:
        missing_docs.append("indice_ou_formula")
    if not docs_text_extracted:
        missing_docs.append("texto_oficial_contrato_edital")
    missing_docs.extend(["medicoes", "apostilas", "memoria_reajuste"])
    missing_docs = list(dict.fromkeys(missing_docs))

    if adjustment_history == NO_PRIOR_ADJUSTMENT_LOCATED:
        adj_conf = CONF_LOW
        uncertainties.append(
            "ausencia_de_apostila_nao_prova_inexistencia_nem_existencia_de_reajuste"
        )
    elif adjustment_history == PARTIAL_ADJUSTMENT_CONFIRMED:
        adj_conf = CONF_MEDIUM
        uncertainties.append("reajuste_parcial_localizado")
    elif adjustment_history == ADJUSTMENT_HISTORY_CONFLICT:
        adj_conf = CONF_LOW
        uncertainties.append("historico_reajuste_conflitante")
    else:
        adj_conf = CONF_LOW

    if open_obligation and not is_closed:
        exec_conf = CONF_MEDIUM if value_plausible else CONF_LOW
    else:
        exec_conf = CONF_LOW

    conf_in = (contact_confidence or "").lower()
    if contact_verifiable and conf_in in {"", "high", CONF_HIGH}:
        contact_ready = CONF_HIGH
    elif conf_in in {"low", CONF_LOW} or (
        not contact_verifiable and conf_in in {"low", CONF_LOW}
    ):
        contact_ready = CONF_LOW
        uncertainties.append(
            "contato_freemail_ou_baixa_confianca_exige_revisao_antes_de_abordagem"
        )
    elif contact_verifiable:
        contact_ready = CONF_HIGH
    else:
        contact_ready = CONF_NONE
    contact_ok_for_diagnostic = contact_verifiable and contact_ready == CONF_HIGH

    if human_review_done:
        human_st = HUMAN_REVIEW_COMPLETED
    else:
        human_st = HUMAN_REVIEW_PENDING if doc_bits >= 1 else HUMAN_REVIEW_NONE

    claim_ready = CLAIM_BLOCKED
    valor_ok = False
    # VERIFIED requires proven regime (R-A), not merely LIKELY_14133
    verified_ok = (
        regime_proven
        and regime == REGIME_14133
        and clause_located
        and exact_budget_date is not None
        and index_or_formula
        and temporal.interregno_complete_exact
        and human_review_done
        and adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED
        and open_obligation
        and not material_contradiction
        and not legal_regime_conflict
        and regime != REGIME_CONFLICT
        and docs_text_extracted
        and document_link_validated
    )
    calculable_ok = verified_ok and has_calculable_base and has_index_series
    if calculable_ok:
        claim_ready = CLAIM_CALCULABLE
        valor_ok = True
    elif verified_ok:
        claim_ready = CLAIM_READY

    stage = POTENTIAL_ADJUSTMENT_SIGNAL
    language = "intelligence_only"
    next_act = "Manter em inteligência comercial; enriquecer sinais."
    action = ACTION_INTEL_ONLY
    diagnostic_ok = False
    legacy = "NOT_READY_FOR_OUTREACH"
    msg_key, msg_body = select_message_template(
        regime=regime, regime_proven=regime_proven, regime_probable=probable
    )

    temporal_ok_for_likely = (
        temporal.minimum_elapsed_confirmed
        or (temporal.level == TEMPORAL_LEVEL_A and temporal.interregno_complete_exact)
    )
    temporal_ok_for_signal = temporal_ok_for_likely or temporal.level == TEMPORAL_LEVEL_C

    no_full_prior = adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED
    not_conflict = not legal_regime_conflict and regime != REGIME_CONFLICT
    regime_unresolved = regime in {
        REGIME_UNKNOWN,
        REGIME_TRANSITIONAL_UNRESOLVED,
    }
    legacy_proven = regime in _LEGACY_REGIMES and regime_proven

    # Proven legacy regimes are out of the 14.133 commercial funnel
    if legacy_proven and not probable:
        dims = CommercialDimensions(
            signal_status="none",
            legal_confidence=legal_conf,
            temporal_confidence=temporal.temporal_confidence,
            documentary_confidence=doc_conf,
            execution_confidence=exec_conf,
            adjustment_history_confidence=adj_conf,
            contact_readiness=contact_ready,
            human_review_status=human_st,
            commercial_action=ACTION_INTEL_ONLY,
            claim_readiness=CLAIM_BLOCKED,
        )
        return CommercialStageResult(
            commercial_stage="NOT_COMMERCIAL",
            dimensions=dims,
            temporal=temporal,
            regime_probable_14133=False,
            language_allowed="none",
            prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
            next_action=(
                f"Regime {regime} comprovado — fora do funil de reajuste Lei 14.133; "
                "abordagem específica da Lei 14.133 bloqueada."
            ),
            missing_documents=[],
            favorable_signals=favorable,
            uncertainties=uncertainties + ["regime_legado_comprovado"],
            reasons=["legacy_regime_excludes_14133_funnel"],
            outreach_status_legacy="NOT_READY_FOR_OUTREACH",
            message_template="unresolved",
        )

    strong_doc_request = (
        is_construction
        and private_supplier
        and obra_confidence >= 0.45
        and temporal_ok_for_likely
        and open_obligation
        and no_full_prior
        and not fully_liquidated
        and not material_contradiction
        and icp_compatible
        and not legacy_proven
        and (
            regime_unresolved
            or regime == REGIME_CONFLICT
            or (regime == REGIME_14133 and not regime_proven and not probable)
            or (not probable and regime not in _LEGACY_REGIMES)
        )
    )

    # 1) CALCULABLE
    if calculable_ok:
        stage = CALCULABLE_ADJUSTMENT_CLAIM
        language = "claim_with_reproducible_value_and_limitations"
        next_act = "Estruturar pleito com memória de cálculo e limitações declaradas."
        action = ACTION_STRUCTURE_CLAIM
        diagnostic_ok = True
        legacy = "OUTREACH_READY"
        reasons.append("calculable_claim_gates_passed")
        msg_key, msg_body = "proven", MSG_REGIME_PROVEN

    # 2) VERIFIED
    elif verified_ok:
        stage = VERIFIED_ADJUSTMENT_OPPORTUNITY
        language = "technical_assertive_no_value_without_series"
        next_act = "Conversar tecnicamente; completar série/base para cálculo."
        action = ACTION_HUMAN_REVIEW if not human_review_done else ACTION_STRUCTURE_CLAIM
        diagnostic_ok = True
        legacy = "OUTREACH_READY_WITHOUT_VALUE_ESTIMATE"
        reasons.append("verified_documentary_pack")
        msg_key, msg_body = "proven", MSG_REGIME_PROVEN

    # 3) LIKELY / DIAGNOSTIC — only proven 14.133 or LIKELY_14133 (R-B)
    elif (
        is_construction
        and private_supplier
        and probable
        and temporal_ok_for_likely
        and open_obligation
        and no_full_prior
        and not_conflict
        and not material_contradiction
        and icp_compatible
    ):
        stage = LIKELY_ADJUSTMENT_OPPORTUNITY
        language = "commercial_intelligence"
        next_act = (
            "Priorizar na fila; solicitar documentos e enriquecer contato se necessário."
        )
        action = ACTION_REQUEST_DOCS
        reasons.append("likely_opportunity_regime_proven_or_r_b")
        legacy = "DOCUMENT_REQUEST_CANDIDATE"
        if contact_ok_for_diagnostic:
            stage = DIAGNOSTIC_OUTREACH_READY
            language = "diagnostic_only"
            next_act = (
                "Abordagem diagnóstica prudente oferecendo conferência técnica — "
                "sem afirmar valor devido. Linguagem adequada ao nível de regime."
            )
            action = ACTION_DIAGNOSTIC_OUTREACH
            diagnostic_ok = True
            reasons.append("diagnostic_outreach_with_verifiable_channel")
            legacy = "DOCUMENT_REQUEST_CANDIDATE"
        else:
            if contact_ready == CONF_LOW:
                uncertainties.append(
                    "contato_baixa_confianca_freemail_exige_revisao — permanece LIKELY"
                )
                action = ACTION_ENRICH_CONTACT
                next_act = (
                    "Revisar contato freemail/baixa confiança; enriquecer canal corporativo."
                )
            else:
                uncertainties.append(
                    "contato_empresarial_ausente — lead permanece na fila de enriquecimento"
                )
                action = ACTION_ENRICH_CONTACT
                next_act = (
                    "Enriquecer contato empresarial; manter na fila de leads prioritários."
                )

    # 4) DOCUMENT_REQUEST_READY — primary operational state for unresolved regime
    elif strong_doc_request and (
        regime_unresolved
        or not probable
    ):
        # Prefer DOCUMENT_REQUEST when regime needs resolution and maturity is strong
        if regime in {REGIME_TRANSITIONAL_UNRESOLVED, REGIME_UNKNOWN} or (
            not probable and temporal_ok_for_likely
        ):
            stage = DOCUMENT_REQUEST_READY
            language = "document_request"
            next_act = (
                "Solicitar documentos prioritários para identificar regime, cláusula, "
                "data-base, índice e reajustes anteriores."
            )
            action = (
                ACTION_REQUEST_LEGAL_REGIME_DOCS
                if regime
                in {REGIME_TRANSITIONAL_UNRESOLVED, REGIME_UNKNOWN, REGIME_CONFLICT}
                else ACTION_REQUEST_DOCS
            )
            reasons.append("document_request_regime_unresolved_or_unknown")
            legacy = "DOCUMENT_REQUEST_CANDIDATE"
            msg_key, msg_body = "unresolved", DOCUMENT_REQUEST_LANGUAGE
            diagnostic_ok = False  # no 14.133-specific diagnostic
        else:
            stage = POTENTIAL_ADJUSTMENT_SIGNAL
            reasons.append("potential_adjustment_signal")

    # 5) POTENTIAL signal (weaker temporal, conflict intel, or residual)
    elif (
        is_construction
        and private_supplier
        and temporal_ok_for_signal
        and no_full_prior
        and not fully_liquidated
        and not material_contradiction
    ):
        stage = POTENTIAL_ADJUSTMENT_SIGNAL
        language = "intelligence_only"
        next_act = "Triagem nacional: aprofundar se prioridade comercial alta."
        action = ACTION_INTEL_ONLY
        reasons.append("potential_adjustment_signal")
        if not probable:
            uncertainties.append("regime_nao_provavel_ainda")
        if regime == REGIME_CONFLICT:
            language = "intelligence_only"
            next_act = "Inteligência interna apenas — resolver conflito de regime."
            action = ACTION_HUMAN_REVIEW
            reasons.append("regime_conflict_intelligence_only")
        legacy = "NOT_READY_FOR_OUTREACH"
        msg_key, msg_body = "unresolved", MSG_REGIME_UNRESOLVED

    else:
        stage = (
            "NOT_COMMERCIAL" if not temporal_ok_for_signal else POTENTIAL_ADJUSTMENT_SIGNAL
        )
        if stage == "NOT_COMMERCIAL":
            reasons.append("sinais_insuficientes")
            action = ACTION_INTEL_ONLY
            language = "none"
        else:
            reasons.append("potential_weak_signal")
            msg_key, msg_body = "unresolved", MSG_REGIME_UNRESOLVED

    # Material contradiction blocks diagnostic language
    if material_contradiction and stage in {
        DIAGNOSTIC_OUTREACH_READY,
        VERIFIED_ADJUSTMENT_OPPORTUNITY,
        CALCULABLE_ADJUSTMENT_CLAIM,
    }:
        stage = (
            LIKELY_ADJUSTMENT_OPPORTUNITY
            if probable and temporal_ok_for_likely
            else (
                DOCUMENT_REQUEST_READY
                if temporal_ok_for_likely
                else POTENTIAL_ADJUSTMENT_SIGNAL
            )
        )
        diagnostic_ok = False
        language = "intelligence_only"
        action = ACTION_HUMAN_REVIEW
        next_act = "Resolver contradição material antes de qualquer abordagem."
        reasons.append("material_contradiction_blocks_outreach")
        legacy = "NOT_READY_FOR_OUTREACH"

    if legal_regime_conflict or regime == REGIME_CONFLICT:
        if stage in {
            DIAGNOSTIC_OUTREACH_READY,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
        }:
            stage = (
                POTENTIAL_ADJUSTMENT_SIGNAL
                if temporal_ok_for_signal
                else "NOT_COMMERCIAL"
            )
            diagnostic_ok = False
            language = "intelligence_only"
            action = ACTION_HUMAN_REVIEW
            next_act = "Resolver conflito de regime antes de abordagem jurídica específica."
            legacy = "NOT_READY_FOR_OUTREACH"
            reasons.append("legal_regime_conflict")
            msg_key, msg_body = "unresolved", MSG_REGIME_UNRESOLVED
            legal_conf = CONF_CONFLICT

    # Transitional: never DIAGNOSTIC with 14.133-specific language
    if regime == REGIME_TRANSITIONAL_UNRESOLVED:
        diagnostic_ok = False
        if stage == DIAGNOSTIC_OUTREACH_READY:
            stage = DOCUMENT_REQUEST_READY
            action = ACTION_REQUEST_LEGAL_REGIME_DOCS
            language = "document_request"
            next_act = (
                "Regime de transição não resolvido — solicitar documentos de fundamento "
                "legal antes de qualquer abordagem específica da Lei 14.133."
            )
            reasons.append("transitional_blocks_14133_diagnostic")
            msg_key, msg_body = "unresolved", DOCUMENT_REQUEST_LANGUAGE
            legacy = "DOCUMENT_REQUEST_CANDIDATE"
        claim_ready = CLAIM_BLOCKED
        legal_conf = CONF_UNRESOLVED

    # LIKELY_14133: conditional language only
    if stage == DIAGNOSTIC_OUTREACH_READY:
        if regime_proven and regime == REGIME_14133:
            msg_key, msg_body = "proven", MSG_REGIME_PROVEN
        else:
            msg_key, msg_body = "likely", MSG_REGIME_LIKELY

    if stage == LIKELY_ADJUSTMENT_OPPORTUNITY:
        if regime_proven and regime == REGIME_14133:
            msg_key, msg_body = "proven", MSG_REGIME_PROVEN
        else:
            msg_key, msg_body = "likely", MSG_REGIME_LIKELY

    if stage in {DOCUMENT_REQUEST_READY, POTENTIAL_ADJUSTMENT_SIGNAL}:
        if not probable:
            msg_key, msg_body = (
                "unresolved",
                DOCUMENT_REQUEST_LANGUAGE
                if stage == DOCUMENT_REQUEST_READY
                else MSG_REGIME_UNRESOLVED,
            )

    dims = CommercialDimensions(
        signal_status=(
            "high"
            if stage
            in {
                LIKELY_ADJUSTMENT_OPPORTUNITY,
                DIAGNOSTIC_OUTREACH_READY,
                VERIFIED_ADJUSTMENT_OPPORTUNITY,
                CALCULABLE_ADJUSTMENT_CLAIM,
            }
            else (
                "medium"
                if stage
                in {POTENTIAL_ADJUSTMENT_SIGNAL, DOCUMENT_REQUEST_READY}
                else "none"
            )
        ),
        legal_confidence=legal_conf,
        temporal_confidence=temporal.temporal_confidence,
        documentary_confidence=doc_conf,
        execution_confidence=exec_conf,
        adjustment_history_confidence=adj_conf,
        contact_readiness=contact_ready,
        human_review_status=human_st,
        commercial_action=action,
        claim_readiness=claim_ready,
    )

    lang_body = language
    if stage == DIAGNOSTIC_OUTREACH_READY:
        lang_body = msg_body
    elif stage == DOCUMENT_REQUEST_READY:
        lang_body = DOCUMENT_REQUEST_LANGUAGE
    elif stage == LIKELY_ADJUSTMENT_OPPORTUNITY:
        lang_body = msg_body
    elif stage == POTENTIAL_ADJUSTMENT_SIGNAL:
        lang_body = MSG_REGIME_UNRESOLVED if not probable else msg_body

    return CommercialStageResult(
        commercial_stage=stage,
        dimensions=dims,
        temporal=temporal,
        regime_probable_14133=probable,
        language_allowed=lang_body,
        prohibited_language=PROHIBITED_CLAIM_LANGUAGE,
        next_action=next_act,
        missing_documents=missing_docs if stage != "NOT_COMMERCIAL" else [],
        favorable_signals=favorable,
        uncertainties=uncertainties,
        valor_potencial_allowed=valor_ok,
        diagnostic_outreach_allowed=(
            diagnostic_ok
            and stage == DIAGNOSTIC_OUTREACH_READY
            and probable
        ),
        reasons=reasons,
        outreach_status_legacy=legacy,
        message_template=msg_key,
    )


def co_status_document_request(stage: str, documentary_confidence: str) -> bool:
    """True when DOCUMENT_REQUEST_READY coexists with LIKELY/DIAGNOSTIC."""
    return stage in {
        LIKELY_ADJUSTMENT_OPPORTUNITY,
        DIAGNOSTIC_OUTREACH_READY,
        VERIFIED_ADJUSTMENT_OPPORTUNITY,
        DOCUMENT_REQUEST_READY,
    } and documentary_confidence in {CONF_NONE, CONF_LOW, CONF_MEDIUM}


def diagnostic_message(*, regime_proven: bool = True, regime_probable: bool = False) -> str:
    """Select diagnostic copy; default proven template for back-compat."""
    if regime_proven:
        return MSG_REGIME_PROVEN
    if regime_probable:
        return MSG_REGIME_LIKELY
    return MSG_REGIME_UNRESOLVED
