"""Contract execution / balance status (not only is_active flag)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from scripts.commercial.reajuste_14133 import (
    CONTRACT_ACTIVE,
    CONTRACT_CLOSED,
    CONTRACT_EXPIRED_WITH_OPEN_FINANCIAL_OBLIGATIONS,
    CONTRACT_FULLY_MEASURED,
    EXECUTION_STATUS_UNKNOWN,
)


@dataclass
class ExecutionStatusResult:
    status: str
    open_obligation_possible: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_execution_status(
    *,
    as_of: date,
    is_active: bool | None = None,
    data_fim: date | str | None = None,
    valor_total: float | None = None,
    valor_medido: float | None = None,
    valor_pago: float | None = None,
    recebimento_definitivo: bool = False,
    has_future_parcel_signal: bool = False,
) -> ExecutionStatusResult:
    """Classify execution without treating is_active alone as balance proof."""
    fim: date | None = None
    if isinstance(data_fim, date):
        fim = data_fim
    elif data_fim:
        try:
            fim = date.fromisoformat(str(data_fim)[:10])
        except ValueError:
            fim = None

    if recebimento_definitivo:
        return ExecutionStatusResult(
            status=CONTRACT_CLOSED,
            open_obligation_possible=False,
            reasons=["recebimento_definitivo"],
        )

    if valor_total is not None and valor_medido is not None:
        try:
            if float(valor_medido) >= float(valor_total) * 0.995:
                return ExecutionStatusResult(
                    status=CONTRACT_FULLY_MEASURED,
                    open_obligation_possible=False,
                    reasons=["medicao_cobertura_quase_integral"],
                )
        except (TypeError, ValueError):
            pass

    expired = fim is not None and fim < as_of
    residual = False
    if valor_total is not None and valor_medido is not None:
        try:
            residual = float(valor_total) - float(valor_medido) > 0
        except (TypeError, ValueError):
            residual = False
    if valor_total is not None and valor_pago is not None:
        try:
            residual = residual or (float(valor_total) - float(valor_pago) > 0)
        except (TypeError, ValueError):
            pass

    if expired and (residual or has_future_parcel_signal):
        return ExecutionStatusResult(
            status=CONTRACT_EXPIRED_WITH_OPEN_FINANCIAL_OBLIGATIONS,
            open_obligation_possible=True,
            reasons=["vigencia_encerrada_com_indicio_saldo"],
        )

    if expired and is_active is False and not residual:
        return ExecutionStatusResult(
            status=CONTRACT_CLOSED,
            open_obligation_possible=False,
            reasons=["inativo_e_vigencia_encerrada"],
        )

    if is_active is True or (fim is None or fim >= as_of):
        return ExecutionStatusResult(
            status=CONTRACT_ACTIVE if (is_active is not False) else EXECUTION_STATUS_UNKNOWN,
            open_obligation_possible=True,
            reasons=["vigente_ou_sem_fim_conhecido"]
            if is_active is not False
            else ["status_execucao_incerto"],
        )

    if is_active is None and fim is None:
        return ExecutionStatusResult(
            status=EXECUTION_STATUS_UNKNOWN,
            open_obligation_possible=True,  # fail-open for investigation, not for ready claim
            reasons=["sem_is_active_nem_data_fim"],
        )

    return ExecutionStatusResult(
        status=EXECUTION_STATUS_UNKNOWN,
        open_obligation_possible=True,
        reasons=["indeterminado"],
    )
