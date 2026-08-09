"""Financial estimation for reajuste em sentido estrito.

Never invents index series. Without contractual index + official series,
only UPPER_BOUND_NOT_CLAIM_VALUE may be shown on total value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from scripts.commercial.reajuste_14133 import UPPER_BOUND_LABEL

RULE_VERSION = "finance-v1"


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class FinanceEstimate:
    valor_original: Decimal | None
    valor_atualizado_aditivos: Decimal | None
    valor_medido: Decimal | None
    valor_pago: Decimal | None
    saldo_contratual: Decimal | None
    base_reajustavel: Decimal | None
    base_label: str
    indice_contratual: str | None
    indice_base_value: Decimal | None
    indice_final_value: Decimal | None
    fator_reajuste: Decimal | None
    percentual_acumulado: Decimal | None
    valor_potencial: Decimal | None
    valor_retroativo_potencial: Decimal | None
    teto_teorico: Decimal | None
    teto_label: str | None
    formula: str
    serie_fonte: str | None
    competencia_inicial: str | None
    competencia_final: str | None
    limitations: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)

        def ser(x: Any) -> Any:
            if isinstance(x, Decimal):
                return float(x)
            return x

        return {k: ser(v) for k, v in d.items()}


def estimate_reajuste(
    *,
    valor_original: Any = None,
    valor_atualizado: Any = None,
    valor_medido: Any = None,
    valor_pago: Any = None,
    saldo_contratual: Any = None,
    indice_contratual: str | None = None,
    indice_base_value: Any = None,
    indice_final_value: Any = None,
    serie_fonte: str | None = None,
    competencia_inicial: str | None = None,
    competencia_final: str | None = None,
    allow_default_index: bool = False,
) -> FinanceEstimate:
    """Compute reajuste factor only when contractual index + series values exist.

    ``allow_default_index`` is always ignored (hard fail-closed) — kept for API
    clarity so callers cannot silently inject IPCA/INCC/etc.
    """
    del allow_default_index  # never used — inventing index is forbidden
    limitations: list[str] = []
    v_orig = _dec(valor_original)
    v_upd = _dec(valor_atualizado) or v_orig
    v_med = _dec(valor_medido)
    v_pago = _dec(valor_pago)
    saldo = _dec(saldo_contratual)

    if saldo is None and v_upd is not None and v_med is not None:
        saldo = v_upd - v_med
        limitations.append("saldo_derivado_valor_atualizado_menos_medido")

    base: Decimal | None = None
    base_label = "UNKNOWN"
    if saldo is not None and saldo > 0:
        base = saldo
        base_label = "SALDO_CONTRATUAL"
    elif v_med is not None and v_med > 0 and v_upd is not None:
        # remaining after measurement
        rem = v_upd - v_med
        if rem > 0:
            base = rem
            base_label = "SALDO_DERIVADO"
        else:
            base = None
            base_label = "EXHAUSTED_OR_FULLY_MEASURED"
    elif v_upd is not None and v_upd > 0:
        base = v_upd
        base_label = UPPER_BOUND_LABEL
        limitations.append(
            "Saldo/medições indisponíveis — valor sobre total é teto teórico, não valor devido."
        )

    idx_name = (indice_contratual or "").strip() or None
    i_base = _dec(indice_base_value)
    i_final = _dec(indice_final_value)

    fator: Decimal | None = None
    pct: Decimal | None = None
    valor_pot: Decimal | None = None
    valor_retro: Decimal | None = None
    teto: Decimal | None = None
    teto_label: str | None = None
    formula = "fator = indice_final / indice_base; percentual = fator - 1"

    if not idx_name:
        limitations.append("indice_contratual_ausente — não aplicar IPCA/INCC/SINAPI por plausibilidade")
    if i_base is None or i_final is None or not idx_name:
        limitations.append("serie_oficial_incompleta — percentual não calculado")
        if base is not None and base_label == UPPER_BOUND_LABEL:
            # Without % we still expose theoretical envelope only as unknown
            teto = None
            teto_label = UPPER_BOUND_LABEL
            limitations.append("teto_percentual_desconhecido_sem_indice")
    else:
        if i_base <= 0:
            limitations.append("indice_base_invalido")
        else:
            fator = (i_final / i_base).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            pct = fator - Decimal("1")
            if pct < 0:
                limitations.append("deflacao_ou_percentual_negativo — não apresentar como valor a recuperar")
            if base is not None and pct is not None and pct > 0:
                raw = _q2(base * pct)
                if base_label == UPPER_BOUND_LABEL:
                    teto = raw
                    teto_label = UPPER_BOUND_LABEL
                    valor_pot = None
                    limitations.append("valor_calculado_e_teto_teorico_nao_claim")
                else:
                    valor_pot = raw
                    valor_retro = raw  # same without finer competency split
                    if v_upd is not None:
                        teto = _q2(v_upd * pct)
                        teto_label = UPPER_BOUND_LABEL
            elif base is not None and pct is not None and pct <= 0:
                valor_pot = _q2(base * pct)
                limitations.append("percentual_nao_positivo")

    return FinanceEstimate(
        valor_original=v_orig,
        valor_atualizado_aditivos=v_upd,
        valor_medido=v_med,
        valor_pago=v_pago,
        saldo_contratual=saldo,
        base_reajustavel=base,
        base_label=base_label,
        indice_contratual=idx_name,
        indice_base_value=i_base,
        indice_final_value=i_final,
        fator_reajuste=fator,
        percentual_acumulado=pct,
        valor_potencial=valor_pot,
        valor_retroativo_potencial=valor_retro,
        teto_teorico=teto,
        teto_label=teto_label,
        formula=formula,
        serie_fonte=serie_fonte,
        competencia_inicial=competencia_inicial,
        competencia_final=competencia_final,
        limitations=limitations,
    )
