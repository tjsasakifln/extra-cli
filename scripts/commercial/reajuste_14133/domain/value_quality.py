"""PNCP contract value quality validation.

Outliers and unconfirmed values must not drive commercial priority or fee estimates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.commercial.reajuste_14133 import (
    VALUE_CONFIRMED,
    VALUE_CONFLICT,
    VALUE_OUTLIER_REQUIRES_REVIEW,
    VALUE_PLAUSIBLE,
    VALUE_UNUSABLE,
)

# Hard ceiling for single conventional construction contract without confirmation
_BILLION = Decimal("1000000000")
_DEFAULT_OUTLIER_THRESHOLD = Decimal("500000000")  # R$ 500M
_MIN_PLAUSIBLE = Decimal("1000")


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return d


@dataclass
class ValueQualityResult:
    status: str
    valor_usado: Decimal | None
    reasons: list[str] = field(default_factory=list)
    may_drive_financial_score: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("valor_usado"), Decimal):
            d["valor_usado"] = float(d["valor_usado"])
        return d


def validate_contract_value(
    *,
    valor_total: Any = None,
    valor_inicial: Any = None,
    valor_atualizado: Any = None,
    objeto: str | None = None,
    document_value: Any = None,
    confirmed_by_document: bool = False,
    is_duplicate_republication: bool = False,
    is_portfolio_or_lote_aggregate: bool = False,
    scale_anomaly: bool = False,
    peer_median: Any = None,
    outlier_threshold: Any = None,
) -> ValueQualityResult:
    """Assess whether PNCP value is usable for commercial ranking/fees."""
    reasons: list[str] = []
    notes: list[str] = []
    v = _dec(valor_atualizado) or _dec(valor_total) or _dec(valor_inicial)
    v_init = _dec(valor_inicial)
    v_upd = _dec(valor_atualizado) or _dec(valor_total)
    v_doc = _dec(document_value)
    thr = _dec(outlier_threshold) or _DEFAULT_OUTLIER_THRESHOLD

    if v is None:
        return ValueQualityResult(
            status=VALUE_UNUSABLE,
            valor_usado=None,
            reasons=["valor_ausente"],
            may_drive_financial_score=False,
        )

    if v <= 0:
        return ValueQualityResult(
            status=VALUE_UNUSABLE,
            valor_usado=v,
            reasons=["valor_nao_positivo"],
            may_drive_financial_score=False,
        )

    if is_duplicate_republication:
        return ValueQualityResult(
            status=VALUE_CONFLICT,
            valor_usado=v,
            reasons=["republicacao_ou_duplicata_economica"],
            may_drive_financial_score=False,
        )

    if is_portfolio_or_lote_aggregate:
        reasons.append("valor_pode_representar_portfolio_ou_lote")
        return ValueQualityResult(
            status=VALUE_OUTLIER_REQUIRES_REVIEW,
            valor_usado=v,
            reasons=reasons,
            may_drive_financial_score=False,
            notes=["Não usar para honorários até confirmação de escopo unitário."],
        )

    if scale_anomaly:
        return ValueQualityResult(
            status=VALUE_OUTLIER_REQUIRES_REVIEW,
            valor_usado=v,
            reasons=["anomalia_de_escala_ou_casas_decimais"],
            may_drive_financial_score=False,
        )

    # Initial vs updated conflict (>10x drift without explanation)
    if v_init is not None and v_upd is not None and v_init > 0:
        ratio = float(v_upd / v_init)
        if ratio > 10 or ratio < 0.1:
            return ValueQualityResult(
                status=VALUE_CONFLICT,
                valor_usado=v_upd,
                reasons=["divergencia_valor_inicial_atualizado"],
                may_drive_financial_score=False,
                notes=[f"ratio_atualizado_inicial={ratio:.3f}"],
            )

    if v_doc is not None and v is not None:
        if v_doc > 0 and abs(float(v - v_doc) / float(v_doc)) > 0.15:
            return ValueQualityResult(
                status=VALUE_CONFLICT,
                valor_usado=v,
                reasons=["divergencia_valor_documento_vs_pncp"],
                may_drive_financial_score=False,
            )

    # Billion-scale road works without document confirmation → outlier
    obj = (objeto or "").lower()
    roadish = any(k in obj for k in ("rodov", "paviment", "estrada", "asfalt"))
    if v >= thr:
        reasons.append("valor_acima_limiar_estatistico")
        if v >= _BILLION and roadish and not confirmed_by_document:
            return ValueQualityResult(
                status=VALUE_OUTLIER_REQUIRES_REVIEW,
                valor_usado=v,
                reasons=reasons + ["valor_bilionario_rodoviario_sem_confirmacao_documental"],
                may_drive_financial_score=False,
                notes=[
                    "Valores bilionários incompatíveis com objeto isolado foram observados "
                    "em revisões anteriores — bloquear prioridade financeira."
                ],
            )
        if not confirmed_by_document:
            return ValueQualityResult(
                status=VALUE_OUTLIER_REQUIRES_REVIEW,
                valor_usado=v,
                reasons=reasons,
                may_drive_financial_score=False,
            )

    peer = _dec(peer_median)
    if peer is not None and peer > 0 and v > peer * 20:
        return ValueQualityResult(
            status=VALUE_OUTLIER_REQUIRES_REVIEW,
            valor_usado=v,
            reasons=["outlier_vs_mediana_pares"],
            may_drive_financial_score=False,
        )

    if confirmed_by_document and v >= _MIN_PLAUSIBLE:
        return ValueQualityResult(
            status=VALUE_CONFIRMED,
            valor_usado=v,
            reasons=["confirmado_por_documento"],
            may_drive_financial_score=True,
        )

    if v >= _MIN_PLAUSIBLE and v < thr:
        return ValueQualityResult(
            status=VALUE_PLAUSIBLE,
            valor_usado=v,
            reasons=["faixa_plausivel_sem_confirmacao_documental"],
            may_drive_financial_score=True,
            notes=["Plausível para ranking; não usar como valor de honorário sem conferência."],
        )

    return ValueQualityResult(
        status=VALUE_PLAUSIBLE if v < thr else VALUE_OUTLIER_REQUIRES_REVIEW,
        valor_usado=v,
        reasons=reasons or ["avaliacao_padrao"],
        may_drive_financial_score=v < thr,
        notes=notes,
    )


def may_use_for_financial_attractiveness(status: str) -> bool:
    return status in {VALUE_CONFIRMED, VALUE_PLAUSIBLE}
