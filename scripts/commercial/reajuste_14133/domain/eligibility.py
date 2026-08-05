"""Eligibility funnel and HOT_VERIFIED documentary gates (fail-closed)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    REGIME_8666,
    REGIME_10520,
    REGIME_14133,
    REGIME_CONFLICT,
    REGIME_RDC,
    REGIME_UNKNOWN,
    STATUS_ALREADY_ADJUSTED,
    STATUS_CLOSED,
    STATUS_HOT_VERIFIED,
    STATUS_LEGAL_REGIME_CONFLICT,
    STATUS_LEGAL_REGIME_UNKNOWN,
    STATUS_NOT_ELIGIBLE,
    STATUS_RESEARCH_REQUIRED,
    STATUS_REVIEW_REQUIRED,
    STATUS_STRONG_CANDIDATE,
)
from scripts.commercial.reajuste_14133.domain.dates import DateBundle
from scripts.commercial.reajuste_14133.domain.finance import FinanceEstimate
from scripts.commercial.reajuste_14133.domain.obra_classifier import ConstructionClassification
from scripts.commercial.reajuste_14133.domain.regime import RegimeResult

# The 10 HOT_VERIFIED gates (objective §4)
HOT_GATES = (
    "obra_construcao",
    "regime_14133_comprovado",
    "vigente_ou_saldo_executavel",
    "data_base_exata",
    "indice_localizado",
    "interregno_12m",
    "parcelas_ou_saldo",
    "sem_concessao_integral_periodo",
    "documentos_acessiveis",
    "sem_contradicao_material",
)


@dataclass
class EligibilityResult:
    status: str
    hot_gates: dict[str, bool]
    hot_gates_passed: int
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_investigative_action: str = ""
    cannot_be_hot_from_table_dates_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hot_gates(
    *,
    obra: ConstructionClassification,
    regime: RegimeResult,
    dates: DateBundle,
    finance: FinanceEstimate,
    is_closed: bool,
    already_adjusted: bool,
    docs_accessible: bool,
    index_found: bool,
    material_contradiction: bool,
    has_executable_balance: bool,
) -> dict[str, bool]:
    data_base_ok = (
        dates.data_base_status == DATA_BASE_CONFIRMED
        and dates.data_base_effective.value is not None
        and dates.data_base_effective.confidence == "high"
        and not str(dates.data_base_effective.source).startswith("proxy")
    )
    return {
        "obra_construcao": bool(obra.is_construction and obra.confidence >= 0.55),
        "regime_14133_comprovado": bool(
            regime.regime == REGIME_14133 and regime.proven
        ),
        "vigente_ou_saldo_executavel": bool(not is_closed and has_executable_balance),
        "data_base_exata": data_base_ok,
        "indice_localizado": bool(index_found and finance.indice_contratual),
        "interregno_12m": bool(dates.interregno_completo),
        "parcelas_ou_saldo": bool(
            finance.base_label in {"SALDO_CONTRATUAL", "SALDO_DERIVADO"}
            and finance.base_reajustavel is not None
            and finance.base_reajustavel > 0
        ),
        "sem_concessao_integral_periodo": not already_adjusted,
        "documentos_acessiveis": docs_accessible,
        "sem_contradicao_material": not material_contradiction,
    }


def evaluate_eligibility(
    *,
    obra: ConstructionClassification,
    regime: RegimeResult,
    dates: DateBundle,
    finance: FinanceEstimate,
    is_closed: bool = False,
    already_adjusted: bool = False,
    docs_accessible: bool = False,
    index_found: bool = False,
    material_contradiction: bool = False,
    has_private_supplier: bool = True,
    only_table_dates: bool = True,
) -> EligibilityResult:
    """Classify contract into campaign eligibility status (fail-closed)."""
    reasons: list[str] = []
    gaps: list[str] = []
    risks: list[str] = []

    if not has_private_supplier:
        return EligibilityResult(
            status=STATUS_NOT_ELIGIBLE,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=["fornecedor_privado_nao_identificavel"],
            next_investigative_action="Validar CNPJ do fornecedor no PNCP.",
        )

    if not obra.is_construction:
        return EligibilityResult(
            status=STATUS_NOT_ELIGIBLE,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=obra.reason_codes or ["objeto_nao_construcao"],
            gaps=["objeto_fora_do_escopo_construcao_civil"],
            next_investigative_action="Descartar ou reclassificar se houver evidência de obra material.",
        )

    if is_closed or finance.base_label == "EXHAUSTED_OR_FULLY_MEASURED":
        return EligibilityResult(
            status=STATUS_CLOSED,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=["contrato_encerrado_ou_sem_saldo"],
            next_investigative_action="Confirmar recebimento definitivo / medições finais antes de reabrir.",
        )

    if already_adjusted:
        return EligibilityResult(
            status=STATUS_ALREADY_ADJUSTED,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=["evidencia_reajuste_periodo"],
            risks=["ausencia_de_apostila_no_pncp_nao_prova_inexistencia"],
            next_investigative_action="Verificar se o reajuste do período foi integral ou parcial.",
        )

    if regime.regime == REGIME_CONFLICT:
        return EligibilityResult(
            status=STATUS_LEGAL_REGIME_CONFLICT,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=["legal_regime_conflict"],
            risks=["referencias_contraditorias_de_regime"],
            next_investigative_action="Revisão humana de edital/contrato antes de qualquer abordagem.",
        )

    if regime.regime in {REGIME_8666, REGIME_10520, REGIME_RDC}:
        return EligibilityResult(
            status=STATUS_NOT_ELIGIBLE,
            hot_gates={g: False for g in HOT_GATES},
            hot_gates_passed=0,
            reasons=[f"regime_{regime.regime}"],
            next_investigative_action="Campanha restrita à Lei 14.133/2021 — excluir regime diverso.",
        )

    has_balance = finance.base_label in {
        "SALDO_CONTRATUAL",
        "SALDO_DERIVADO",
        "UPPER_BOUND_NOT_CLAIM_VALUE",
    } and (finance.base_reajustavel is None or finance.base_reajustavel > 0)

    gates = _hot_gates(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        is_closed=is_closed,
        already_adjusted=already_adjusted,
        docs_accessible=docs_accessible,
        index_found=index_found,
        material_contradiction=material_contradiction,
        has_executable_balance=has_balance and not is_closed,
    )
    passed = sum(1 for v in gates.values() if v)

    # HARD RULE: never HOT from table dates alone
    if only_table_dates:
        gates["data_base_exata"] = False
        gates["documentos_acessiveis"] = False
        gates["indice_localizado"] = gates["indice_localizado"] and index_found and not only_table_dates
        # recompute — table-only means data_base and docs cannot pass
        gates["data_base_exata"] = False
        if not docs_accessible:
            gates["documentos_acessiveis"] = False
        passed = sum(1 for v in gates.values() if v)

    if all(gates.values()) and not only_table_dates:
        return EligibilityResult(
            status=STATUS_HOT_VERIFIED,
            hot_gates=gates,
            hot_gates_passed=passed,
            reasons=["todos_os_10_gates_documentais"],
            next_investigative_action=(
                "Montar memória de cálculo e minuta de pedido administrativo com base nos documentos."
            ),
            cannot_be_hot_from_table_dates_only=True,
        )

    # Regime unknown after construction filter
    if regime.regime == REGIME_UNKNOWN or (regime.regime == REGIME_14133 and not regime.proven):
        reasons.append("regime_14133_nao_comprovado")
        gaps.append("comprovacao_regime_legal_em_edital_ou_contrato")
        if not dates.interregno_completo:
            gaps.append("interregno_incompleto_ou_data_base_incerta")
        # Temporal / financial signal?
        if dates.interregno_completo and obra.is_construction:
            status = STATUS_LEGAL_REGIME_UNKNOWN
            next_act = (
                "Obter contrato/edital e localizar cláusula de regime (Lei 14.133) e de reajuste."
            )
            if dates.data_base_status != DATA_BASE_CONFIRMED:
                gaps.append("data_base_orcamento_estimado")
            if not index_found:
                gaps.append("indice_contratual")
            return EligibilityResult(
                status=status,
                hot_gates=gates,
                hot_gates_passed=passed,
                reasons=reasons,
                gaps=gaps,
                risks=risks,
                next_investigative_action=next_act,
            )

    # Strong candidate: construction + likely mature + missing only point docs
    missing_point = []
    if not gates["data_base_exata"]:
        missing_point.append("data_base")
        gaps.append("data_do_orcamento_estimado_no_edital_ou_contrato")
    if not gates["indice_localizado"]:
        missing_point.append("indice")
        gaps.append("clausula_de_indice_de_reajuste")
    if not gates["parcelas_ou_saldo"]:
        missing_point.append("saldo")
        gaps.append("medições_ou_saldo_financeiro_atualizado")
    if not gates["documentos_acessiveis"]:
        missing_point.append("documentos")
        gaps.append("cópia_integral_do_contrato_e_apostilas")
    if not regime.proven:
        missing_point.append("regime")

    if (
        obra.is_construction
        and dates.interregno_completo
        and not is_closed
        and len(missing_point) <= 3
        and (regime.regime == REGIME_14133 or regime.regime == REGIME_UNKNOWN)
    ):
        # STRONG if mostly complete except 1-2 confirmations
        if len(missing_point) <= 2 and (docs_accessible or index_found or regime.proven):
            return EligibilityResult(
                status=STATUS_STRONG_CANDIDATE,
                hot_gates=gates,
                hot_gates_passed=passed,
                reasons=["forte_probabilidade_faltando_confirmacao_pontual"],
                gaps=gaps,
                risks=[
                    "ausencia_de_apostila_no_pncp_nao_prova_que_reajuste_nao_foi_concedido",
                    *risks,
                ],
                next_investigative_action=(
                    "Baixar contrato e apostilas; confirmar data-base, índice e saldo antes da abordagem."
                ),
            )
        return EligibilityResult(
            status=STATUS_REVIEW_REQUIRED,
            hot_gates=gates,
            hot_gates_passed=passed,
            reasons=["indicio_temporal_financeiro_com_lacunas"],
            gaps=gaps,
            risks=risks,
            next_investigative_action="Revisão documental: regime, data-base, índice e execução.",
        )

    if obra.is_construction and not dates.interregno_completo:
        return EligibilityResult(
            status=STATUS_NOT_ELIGIBLE,
            hot_gates=gates,
            hot_gates_passed=passed,
            reasons=["interregno_anual_nao_completado"],
            gaps=gaps,
            next_investigative_action="Reavaliar após completar 12 meses da data-base aplicável.",
        )

    if obra.is_construction:
        return EligibilityResult(
            status=STATUS_RESEARCH_REQUIRED,
            hot_gates=gates,
            hot_gates_passed=passed,
            reasons=["dados_insuficientes_para_abordagem_responsavel"],
            gaps=gaps or ["enriquecimento_documental_necessario"],
            next_investigative_action="Pesquisar edital, contrato e publicações oficiais do órgão.",
        )

    return EligibilityResult(
        status=STATUS_NOT_ELIGIBLE,
        hot_gates=gates,
        hot_gates_passed=passed,
        reasons=["criterios_materiais_nao_atendidos"],
        next_investigative_action="Excluir da fila comercial desta campanha.",
    )
