#!/usr/bin/env python3
"""
Simulador de cenários de lance (heurística NÃO validada).

ATENÇÃO — honesty policy (EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01):
- Este módulo NÃO produz probabilidade calibrada nem previsão aprovada.
- Saídas são scores de cenário heurístico (method=UNVALIDATED_HEURISTIC).
- prediction_claim_allowed=False sempre.
- NÃO usar como "probabilidade de vitória", "lance ótimo" validado ou claim comercial.
- Para previsão validada: scripts.predictive + claim registry PRODUCTION_AVAILABLE.

Usa:
- Distribuição de descontos históricos do órgão (benchmark)
- Concentração de mercado (HHI) → número esperado de concorrentes
- Margem mínima setorial genérica (não calibrada no perfil Extra)
- Valor estimado do edital

Usage:
    from scripts.lib.bid_simulator import simulate_bid, BidSimulation
    result = simulate_bid(edital, competitive_intel, benchmark)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

METHOD_UNVALIDATED_HEURISTIC = "UNVALIDATED_HEURISTIC"


# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class BidSimulation:
    """Resultado de simulação de cenário heurístico (não-previsão)."""

    # Core scenario outputs (honest names)
    lance_cenario: float  # R$ scenario bid (heuristic EV max — not validated optimal)
    desconto_cenario_pct: float  # % discount from estimated value
    heuristic_scenario_score: float  # 0-100 ordinal scenario score (NOT calibrated probability)
    margem_liquida_pct: float  # Projected net margin under heuristic assumptions
    valor_esperado_cenario: float  # Heuristic EV = score/100 × margem × valor_estimado

    # Range
    lance_agressivo: float
    lance_conservador: float
    desconto_agressivo_pct: float
    desconto_conservador_pct: float

    # Context
    competidores_esperados: int
    historico_contratos: int
    confianca_cenario: str  # ALTA / MEDIA / BAIXA / INSUFICIENTE — reliability of heuristic only

    racional: str

    # Honesty markers (always fixed for this module)
    method: str = METHOD_UNVALIDATED_HEURISTIC
    prediction_claim_allowed: bool = False
    claim_state: str = "NOT_IMPLEMENTED"
    limitations: list[str] = field(
        default_factory=lambda: [
            "UNVALIDATED_HEURISTIC: not trained on labeled corpus",
            "No temporal backtest, calibration, or Brier/ECE gates",
            "Sector margins are generic defaults, not Extra profile",
            "Competitor count derived from HHI with arbitrary factors",
            "Do not publish as probabilidade de vitória or lance ótimo",
        ]
    )

    # --- Backward-compatible aliases (deprecated; still not probabilities) ---
    @property
    def lance_sugerido(self) -> float:
        """Deprecated alias for lance_cenario."""
        return self.lance_cenario

    @property
    def desconto_sugerido_pct(self) -> float:
        """Deprecated alias for desconto_cenario_pct."""
        return self.desconto_cenario_pct

    @property
    def p_vitoria_pct(self) -> float:
        """Deprecated: returns heuristic_scenario_score, NOT a validated probability.

        Kept so legacy scorers that weight this ordinal field do not crash.
        Consumers MUST NOT label this as probability.
        """
        return self.heuristic_scenario_score

    @property
    def valor_esperado(self) -> float:
        """Deprecated alias for valor_esperado_cenario."""
        return self.valor_esperado_cenario

    @property
    def confianca(self) -> str:
        """Deprecated alias for confianca_cenario."""
        return self.confianca_cenario

    @property
    def has_data(self) -> bool:
        return self.historico_contratos >= 3

    def to_export_dict(self) -> dict[str, Any]:
        """Export with honest keys only (for reports/JSON/CLI)."""
        return {
            "lance_cenario": self.lance_cenario,
            "desconto_cenario_pct": self.desconto_cenario_pct,
            "heuristic_scenario_score": self.heuristic_scenario_score,
            "margem_liquida_pct": self.margem_liquida_pct,
            "valor_esperado_cenario": self.valor_esperado_cenario,
            "lance_agressivo": self.lance_agressivo,
            "lance_conservador": self.lance_conservador,
            "desconto_agressivo_pct": self.desconto_agressivo_pct,
            "desconto_conservador_pct": self.desconto_conservador_pct,
            "competidores_esperados": self.competidores_esperados,
            "historico_contratos": self.historico_contratos,
            "confianca_cenario": self.confianca_cenario,
            "racional": self.racional,
            "method": self.method,
            "prediction_claim_allowed": self.prediction_claim_allowed,
            "claim_state": self.claim_state,
            "limitations": list(self.limitations),
            "has_data": self.has_data,
            # Explicit non-claims
            "is_calibrated_probability": False,
            "is_optimal_bid": False,
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        """Legacy keys for internal ranking weights only — still not probability."""
        d = self.to_export_dict()
        d["lance_sugerido"] = self.lance_cenario
        d["desconto_sugerido_pct"] = self.desconto_cenario_pct
        # Intentionally NOT exporting p_vitoria_pct as probability label.
        # Internal scorers may still read heuristic_scenario_score via alias property.
        d["heuristic_scenario_score"] = self.heuristic_scenario_score
        d["valor_esperado"] = self.valor_esperado_cenario
        d["confianca"] = self.confianca_cenario
        return d


# ============================================================
# SECTOR MARGIN PROFILES
# ============================================================

SECTOR_MARGINS: dict[str, dict[str, float]] = {
    "engenharia_obras": {
        "margem_minima": 0.05,
        "margem_alvo": 0.12,
        "bdi_referencia": 0.25,
    },
    "ti_software": {
        "margem_minima": 0.10,
        "margem_alvo": 0.20,
        "bdi_referencia": 0.30,
    },
    "consultoria": {
        "margem_minima": 0.15,
        "margem_alvo": 0.25,
        "bdi_referencia": 0.35,
    },
    "avaliacao": {
        "margem_minima": 0.10,
        "margem_alvo": 0.20,
        "bdi_referencia": 0.30,
    },
    "saude": {
        "margem_minima": 0.08,
        "margem_alvo": 0.15,
        "bdi_referencia": 0.28,
    },
    "default": {
        "margem_minima": 0.08,
        "margem_alvo": 0.15,
        "bdi_referencia": 0.25,
    },
}

CNAE_TO_SECTOR: dict[str, str] = {
    "41": "engenharia_obras",
    "42": "engenharia_obras",
    "43": "engenharia_obras",
    "71": "engenharia_obras",
    "62": "ti_software",
    "63": "ti_software",
    "69": "consultoria",
    "70": "consultoria",
    "86": "saude",
    "87": "saude",
}


def _get_sector(cnae_principal: str | None) -> str:
    if not cnae_principal:
        return "default"
    prefix = str(cnae_principal)[:2]
    return CNAE_TO_SECTOR.get(prefix, "default")


# ============================================================
# COMPETITION ESTIMATION (heuristic)
# ============================================================


def _estimate_competitors(hhi: float | None, concentration: str | None) -> int:
    """Estimate number of active bidders from HHI/concentration (heuristic only)."""
    if hhi is not None and hhi > 0:
        effective_n = 1.0 / hhi
        return max(2, min(20, round(effective_n * 1.5)))

    estimates = {
        "BAIXA": 8,
        "MODERADA": 5,
        "ALTA": 3,
        "MUITO_ALTA": 2,
    }
    return estimates.get((concentration or "").upper(), 5)


# ============================================================
# HEURISTIC SCENARIO SCORE (not calibrated probability)
# ============================================================


def _scenario_score(
    desconto_ofertado: float,
    desconto_mediano_hist: float,
    num_competidores: int,
    std_descontos: float,
) -> float:
    """Heuristic ordinal score in [0.02, 0.95] — NOT a calibrated probability."""
    if std_descontos <= 0:
        std_descontos = 0.05

    z = (desconto_ofertado - desconto_mediano_hist) / std_descontos
    cdf = 1.0 / (1.0 + math.exp(-1.7 * z))
    p = cdf ** max(1, num_competidores - 1)
    return min(0.95, max(0.02, p))


# ============================================================
# MAIN SIMULATOR
# ============================================================


def simulate_bid(
    edital: dict[str, Any],
    competitive_intel: dict[str, Any] | None = None,
    benchmark: dict[str, Any] | None = None,
    cnae_principal: str | None = None,
) -> BidSimulation:
    """
    Build a heuristic bid scenario for an edital.

    Returns BidSimulation with method=UNVALIDATED_HEURISTIC and
    prediction_claim_allowed=False. Never a production claim.
    """
    valor = float(edital.get("valor_estimado") or 0)
    sector = _get_sector(cnae_principal)
    margins = SECTOR_MARGINS.get(sector, SECTOR_MARGINS["default"])

    ci = competitive_intel or {}
    hhi = ci.get("hhi")
    concentration = ci.get("concentration") or ci.get("predicted_competition")
    num_competitors = _estimate_competitors(hhi, concentration)

    bm = benchmark or {}
    desconto_mediano = float(
        bm.get("desconto_mediano_orgao") or bm.get("desconto_mediano") or bm.get("median_discount") or 0
    )
    desconto_p25 = float(bm.get("desconto_p25") or bm.get("p25_discount") or 0)
    desconto_p75 = float(bm.get("desconto_p75") or bm.get("p75_discount") or 0)
    historico_n = int(
        bm.get("contratos_analisados") or bm.get("descontos_encontrados") or bm.get("total_contracts") or 0
    )
    std_descontos = float(bm.get("desconto_std") or bm.get("std_discount") or 0)

    if valor <= 0 or historico_n < 3:
        return BidSimulation(
            lance_cenario=valor,
            desconto_cenario_pct=0.0,
            heuristic_scenario_score=0.0,
            margem_liquida_pct=0.0,
            valor_esperado_cenario=0.0,
            lance_agressivo=valor,
            lance_conservador=valor,
            desconto_agressivo_pct=0.0,
            desconto_conservador_pct=0.0,
            competidores_esperados=num_competitors,
            historico_contratos=historico_n,
            confianca_cenario="INSUFICIENTE",
            racional=(
                f"Dados insuficientes para cenário heurístico ({historico_n} contratos, "
                f"mínimo 3). Lance de cenário igual ao valor estimado. "
                f"NÃO é probabilidade validada (method={METHOD_UNVALIDATED_HEURISTIC})."
            ),
        )

    margem_min = margins["margem_minima"]
    margem_alvo = margins["margem_alvo"]

    desconto_base = desconto_mediano
    desconto_sugerido = desconto_base + (std_descontos * 0.3)
    max_desconto = 1.0 - margem_min
    desconto_sugerido = min(desconto_sugerido, max_desconto)

    desconto_agressivo = min(
        desconto_p75 + (std_descontos * 0.5),
        max_desconto,
    )
    desconto_conservador = max(desconto_p25, margem_alvo)

    if desconto_conservador > desconto_sugerido:
        desconto_conservador = desconto_sugerido * 0.85
    if desconto_agressivo < desconto_sugerido:
        desconto_agressivo = min(desconto_sugerido * 1.15, max_desconto)

    lance_cenario = valor * (1 - desconto_sugerido)
    lance_agressivo = valor * (1 - desconto_agressivo)
    lance_conservador = valor * (1 - desconto_conservador)

    score = _scenario_score(desconto_sugerido, desconto_mediano, num_competitors, std_descontos)
    bdi = margins["bdi_referencia"]
    margem = bdi - desconto_sugerido

    if historico_n >= 10 and std_descontos > 0:
        confianca = "ALTA"
    elif historico_n >= 5:
        confianca = "MEDIA"
    else:
        confianca = "BAIXA"

    parts = [
        f"Cenário heurístico (NÃO calibrado) com base em {historico_n} contratos "
        f"(desconto mediano {desconto_mediano:.1%})",
    ]
    if num_competitors > 0:
        parts.append(f"~{num_competitors} concorrentes estimados por HHI (heurística)")
    parts.append(
        f"Margem líquida projetada (BDI genérico): {margem:.1%} (BDI ref: {bdi:.0%}, desconto: {desconto_sugerido:.1%})"
    )
    parts.append(
        f"Score de cenário {score * 100:.0f}/100 — NÃO é probabilidade de vitória "
        f"(method={METHOD_UNVALIDATED_HEURISTIC}, prediction_claim_allowed=false)"
    )

    return BidSimulation(
        lance_cenario=round(lance_cenario, 2),
        desconto_cenario_pct=round(desconto_sugerido * 100, 1),
        heuristic_scenario_score=round(score * 100, 1),
        margem_liquida_pct=round(margem * 100, 1),
        valor_esperado_cenario=round(score * margem * valor, 2),
        lance_agressivo=round(lance_agressivo, 2),
        lance_conservador=round(lance_conservador, 2),
        desconto_agressivo_pct=round(desconto_agressivo * 100, 1),
        desconto_conservador_pct=round(desconto_conservador * 100, 1),
        competidores_esperados=num_competitors,
        historico_contratos=historico_n,
        confianca_cenario=confianca,
        racional=". ".join(parts) + ".",
    )


def format_bid_summary(sim: BidSimulation, valor_estimado: float) -> str:
    """Format heuristic scenario as concise summary for reports (honest wording)."""
    if not sim.has_data:
        return f"Dados insuficientes para cenário heurístico de lance (method={METHOD_UNVALIDATED_HEURISTIC})"

    return (
        f"Cenário heurístico (não validado): R$ {sim.lance_cenario:,.2f} "
        f"(desconto {sim.desconto_cenario_pct:.1f}%) — "
        f"score de cenário {sim.heuristic_scenario_score:.0f}/100 "
        f"(NÃO probabilidade), margem projetada {sim.margem_liquida_pct:.1f}%"
    )


def assert_not_probability_export(payload: dict[str, Any]) -> None:
    """Fail-closed helper: reject export dicts that mislabel heuristics as probability."""
    forbidden_as_true_prob = (
        "p_vitoria",
        "p_vitoria_pct",
        "p_win",
        "probability",
        "probabilidade_vitoria",
        "win_probability",
    )
    method = str(payload.get("method") or "")
    claim_ok = bool(payload.get("prediction_claim_allowed"))
    if method == METHOD_UNVALIDATED_HEURISTIC or not claim_ok:
        for k in forbidden_as_true_prob:
            if k in payload and payload[k] is not None:
                # Allow only if nested under explicit heuristic marker is absent —
                # any presence of these keys on heuristic export is forbidden.
                raise ValueError(
                    f"Heuristic bid simulation cannot export key '{k}' as probability "
                    f"(method={method!r}, prediction_claim_allowed={claim_ok})"
                )
