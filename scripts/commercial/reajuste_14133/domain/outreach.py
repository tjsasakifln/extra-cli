"""Commercial outreach gates — distinct from legal eligibility status.

OUTREACH_READY requires documentary proof + human review + non-misleading argument.
LEGAL_REGIME_UNKNOWN can never be ready for operational contact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    DOCUMENT_REQUEST_CANDIDATE,
    NOT_READY_FOR_OUTREACH,
    OUTREACH_READY,
    OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
    PRIOR_ADJUSTMENT_CONFIRMED,
    REGIME_14133,
    STATUS_ALREADY_ADJUSTED,
    STATUS_CLOSED,
    STATUS_HOT_VERIFIED,
    STATUS_LEGAL_REGIME_CONFLICT,
    STATUS_LEGAL_REGIME_UNKNOWN,
    STATUS_NOT_ELIGIBLE,
    TECHNICALLY_VERIFIED_PENDING_TIAGO,
    VALUE_CONFIRMED,
    VALUE_CONFLICT,
    VALUE_OUTLIER_REQUIRES_REVIEW,
    VALUE_PLAUSIBLE,
    VALUE_UNUSABLE,
)

# Technical gates (no human accept) required for TECHNICALLY_VERIFIED_PENDING_TIAGO
TECHNICAL_GATES = (
    "empresa_privada_confirmada",
    "objeto_construcao_confirmado",
    "documento_vinculo_validado",
    "regime_14133_confirmado",
    "clausula_reajuste_localizada",
    "data_base_exata_localizada",
    "indice_ou_formula_localizada",
    "interregno_completo",
    "obrigacao_financeira_potencialmente_aberta",
    "ausencia_prova_concessao_integral",
    "valor_contratual_plausivel",
    "contato_empresarial_verificavel",
    "argumento_comercial_nao_enganoso",
)

EXPLORATORY_LANGUAGE = (
    "Estamos analisando contratos públicos de obras com interregno anual já "
    "transcorrido e identificamos que este instrumento merece conferência da "
    "cláusula de reajuste. Para confirmar eventual valor, seria necessário "
    "examinar contrato, orçamento, medições e apostilas."
)

OUTREACH_GATES = (
    "empresa_privada_confirmada",
    "objeto_construcao_confirmado",
    "documento_vinculo_validado",
    "regime_14133_confirmado",
    "clausula_reajuste_localizada",
    "data_base_exata_localizada",
    "indice_ou_formula_localizada",
    "interregno_completo",
    "obrigacao_financeira_potencialmente_aberta",
    "ausencia_prova_concessao_integral",
    "valor_contratual_plausivel",
    "contato_empresarial_verificavel",
    "revisao_humana_concluida",
    "argumento_comercial_nao_enganoso",
)


@dataclass
class OutreachResult:
    status: str
    gates: dict[str, bool]
    gates_passed: int
    language_allowed: str
    next_action: str
    reasons: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gate_map(
    *,
    private_supplier: bool,
    is_construction: bool,
    document_link_validated: bool,
    regime_proven_14133: bool,
    clause_located: bool,
    data_base_exact: bool,
    index_or_formula: bool,
    interregno_completo: bool,
    open_obligation: bool,
    no_full_prior_adjustment: bool,
    value_plausible: bool,
    contact_verifiable: bool,
    human_review_done: bool,
    argument_not_misleading: bool,
) -> dict[str, bool]:
    return {
        "empresa_privada_confirmada": private_supplier,
        "objeto_construcao_confirmado": is_construction,
        "documento_vinculo_validado": document_link_validated,
        "regime_14133_confirmado": regime_proven_14133,
        "clausula_reajuste_localizada": clause_located,
        "data_base_exata_localizada": data_base_exact,
        "indice_ou_formula_localizada": index_or_formula,
        "interregno_completo": interregno_completo,
        "obrigacao_financeira_potencialmente_aberta": open_obligation,
        "ausencia_prova_concessao_integral": no_full_prior_adjustment,
        "valor_contratual_plausivel": value_plausible,
        "contato_empresarial_verificavel": contact_verifiable,
        "revisao_humana_concluida": human_review_done,
        "argumento_comercial_nao_enganoso": argument_not_misleading,
    }


def evaluate_outreach(
    *,
    eligibility_status: str,
    regime: str,
    regime_proven: bool,
    is_construction: bool,
    private_supplier: bool,
    clause_located: bool,
    data_base_status: str,
    data_base_exact: bool | None = None,
    index_in_clause: bool,
    interregno_completo: bool,
    open_obligation: bool,
    adjustment_history: str,
    value_quality: str,
    contact_verifiable: bool,
    human_review_done: bool,
    has_valor_potencial: bool,
    argument_cites_unproven_value: bool = False,
    docs_text_extracted: bool = False,
    legal_regime_conflict: bool = False,
    document_link_validated: bool = False,
    document_link_status: str | None = None,
) -> OutreachResult:
    """Classify commercial outreach readiness (fail-closed).

    Never promotes LEGAL_REGIME_UNKNOWN to ready. Absence of apostila alone
    does not satisfy absence-of-prior-adjustment for ready status.

    TECHNICALLY_VERIFIED_PENDING_TIAGO = all technical gates without human accept.
    OUTREACH_READY still requires explicit Tiago decision (human_review_done).
    Never forge human_review_done=True.
    """
    if data_base_exact is None:
        data_base_exact = data_base_status == DATA_BASE_CONFIRMED

    # Full prior adjustment proven → not ready for claim outreach.
    # NO_PRIOR_ADJUSTMENT_LOCATED is weak: absence is not proof reajuste never granted.
    # Ready path still requires human review + documentary clause (below).
    no_full_prior = adjustment_history not in {
        PRIOR_ADJUSTMENT_CONFIRMED,
    }

    value_ok = value_quality in {VALUE_CONFIRMED, VALUE_PLAUSIBLE}
    if value_quality in {VALUE_OUTLIER_REQUIRES_REVIEW, VALUE_UNUSABLE, VALUE_CONFLICT}:
        value_ok = False

    argument_ok = not argument_cites_unproven_value

    # Document link: CONFLICT never validates; VERIFIED or PARTIAL may
    if document_link_status == "DOCUMENT_LINK_CONFLICT":
        document_link_validated = False
    elif document_link_status in {"DOCUMENT_LINK_VERIFIED", "DOCUMENT_LINK_PARTIAL"}:
        document_link_validated = True
    # else keep explicit flag

    gates = _gate_map(
        private_supplier=private_supplier,
        is_construction=is_construction,
        document_link_validated=bool(document_link_validated),
        regime_proven_14133=bool(regime == REGIME_14133 and regime_proven),
        clause_located=clause_located and docs_text_extracted,
        data_base_exact=bool(data_base_exact),
        index_or_formula=index_in_clause,
        interregno_completo=interregno_completo,
        open_obligation=open_obligation,
        no_full_prior_adjustment=no_full_prior and adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED,
        value_plausible=value_ok,
        contact_verifiable=contact_verifiable,
        human_review_done=human_review_done,
        argument_not_misleading=argument_ok,
    )

    passed = sum(1 for v in gates.values() if v)
    blocked = [k for k, v in gates.items() if not v]

    # Hard blocks
    if legal_regime_conflict or eligibility_status == STATUS_LEGAL_REGIME_CONFLICT:
        return OutreachResult(
            status=NOT_READY_FOR_OUTREACH,
            gates=gates,
            gates_passed=passed,
            language_allowed="none",
            next_action="Resolver conflito de regime jurídico em documentos oficiais.",
            reasons=["legal_regime_conflict"],
            blocked_by=blocked + ["legal_regime_conflict"],
        )

    if eligibility_status in {
        STATUS_LEGAL_REGIME_UNKNOWN,
        STATUS_NOT_ELIGIBLE,
        STATUS_CLOSED,
        STATUS_ALREADY_ADJUSTED,
    }:
        return OutreachResult(
            status=NOT_READY_FOR_OUTREACH,
            gates=gates,
            gates_passed=passed,
            language_allowed="none",
            next_action="Não abordar — status de elegibilidade impede contato operacional.",
            reasons=[f"eligibility_{eligibility_status}"],
            blocked_by=blocked,
        )

    if regime != REGIME_14133 or not regime_proven:
        # Strong commercial signal + construction may still be DOCUMENT_REQUEST
        strong_signal = (
            is_construction
            and private_supplier
            and interregno_completo
            and value_ok
            and open_obligation
        )
        if strong_signal and not legal_regime_conflict:
            return OutreachResult(
                status=DOCUMENT_REQUEST_CANDIDATE,
                gates=gates,
                gates_passed=passed,
                language_allowed="exploratory_document_request",
                next_action="Solicitar contrato/edital/apostilas com linguagem exploratória.",
                reasons=["regime_nao_comprovado_mas_forte_sinal_comercial"],
                blocked_by=blocked,
            )
        return OutreachResult(
            status=NOT_READY_FOR_OUTREACH,
            gates=gates,
            gates_passed=passed,
            language_allowed="none",
            next_action="Comprovar regime 14.133 antes de qualquer abordagem.",
            reasons=["regime_14133_nao_comprovado"],
            blocked_by=blocked,
        )

    technical_ready = all(gates[k] for k in TECHNICAL_GATES)
    core_ready = technical_ready and gates["revisao_humana_concluida"]

    if core_ready and adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED:
        if has_valor_potencial:
            return OutreachResult(
                status=OUTREACH_READY,
                gates=gates,
                gates_passed=passed,
                language_allowed="diagnostic_and_value_discussion_with_caveats",
                next_action="Abordar com dossiê documental e proposta de diagnóstico/cálculo.",
                reasons=["all_outreach_gates_passed"],
                blocked_by=[],
            )
        return OutreachResult(
            status=OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
            gates=gates,
            gates_passed=passed,
            language_allowed="diagnostic_and_calculation_offer_no_figure",
            next_action=(
                "Abordar oferecendo diagnóstico e cálculo sem citar cifra de valor potencial."
            ),
            reasons=["all_gates_except_financial_base"],
            blocked_by=["valor_potencial_sem_saldo_ou_serie"],
        )

    # Pre-human technical pack — never OUTREACH_READY without Tiago
    if technical_ready and adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED:
        return OutreachResult(
            status=TECHNICALLY_VERIFIED_PENDING_TIAGO,
            gates=gates,
            gates_passed=passed,
            language_allowed="exploratory_pending_tiago_decision",
            next_action=(
                "Pacote técnico completo — aguardar decisão explícita de Tiago "
                "(ACCEPT/REJECT/DEFER). Não enviar contato."
            ),
            reasons=["technical_gates_passed_pending_tiago"],
            blocked_by=["revisao_humana_concluida"],
        )

    # Document request: construction + fit + missing docs
    doc_candidate = (
        is_construction
        and private_supplier
        and value_ok
        and open_obligation
        and adjustment_history != PRIOR_ADJUSTMENT_CONFIRMED
        and (
            not clause_located
            or not data_base_exact
            or not index_in_clause
            or not docs_text_extracted
            or not document_link_validated
            or eligibility_status in {STATUS_HOT_VERIFIED, "STRONG_CANDIDATE", "REVIEW_REQUIRED"}
        )
    )
    if doc_candidate:
        return OutreachResult(
            status=DOCUMENT_REQUEST_CANDIDATE,
            gates=gates,
            gates_passed=passed,
            language_allowed="exploratory_document_request",
            next_action="Abordagem exploratória pedindo contrato, orçamento, medições e apostilas.",
            reasons=["forte_sinal_dependente_de_documentos"],
            blocked_by=blocked,
        )

    return OutreachResult(
        status=NOT_READY_FOR_OUTREACH,
        gates=gates,
        gates_passed=passed,
        language_allowed="none",
        next_action="Manter em inteligência; não colocar na fila operacional de contato.",
        reasons=["gates_insuficientes"],
        blocked_by=blocked,
    )


def exploratory_message() -> str:
    return EXPLORATORY_LANGUAGE
