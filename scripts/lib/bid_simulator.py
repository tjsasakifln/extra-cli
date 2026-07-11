#!/usr/bin/env python3
"""
Simulador de Lance Ótimo — calcula bid strategy baseado em concorrência e histórico.

Usa:
- Distribuição de descontos históricos do órgão (benchmark)
- Concentração de mercado (HHI) → número esperado de concorrentes
- Margem mínima do setor
- Valor estimado do edital

Para calcular o lance que maximiza P(vitória) × margem.

Usage:
    from lib.bid_simulator import simulate_bid, BidSimulation
    result = simulate_bid(edital, competitive_intel, benchmark, sector="engenharia_obras")
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class BidSimulation:
    """Resultado da simulação de lance."""

    # Core outputs
    lance_sugerido: float  # R$ suggested bid value (maximizes P(win) × margin)
    desconto_sugerido_pct: float  # % discount from estimated value
    p_vitoria_pct: float  # Estimated probability of winning (0-100)
    margem_liquida_pct: float  # Expected net margin — what remains after discount
    valor_esperado: float  # EV = P(win) × margem × valor_estimado — expected profit (R$)

    # Range
    lance_agressivo: float  # Lower bound — higher discount, higher P(win), lower margin
    lance_conservador: float  # Upper bound — lower discount, lower P(win), higher margin
    desconto_agressivo_pct: float
    desconto_conservador_pct: float

    # Context
    competidores_esperados: int  # Estimated number of competing bidders for this bid
    historico_contratos: int  # Number of sector contracts used for benchmark
    confianca: str  # ALTA / MEDIA / BAIXA — reliability of the simulation

    # Explanation
    racional: str  # Human-readable rationale for the suggested bid

    @property
    def has_data(self) -> bool:
        return self.historico_contratos >= 3


# ============================================================
# SECTOR MARGIN PROFILES
# ============================================================

SECTOR_MARGINS: dict[str, dict[str, float]] = {
    "engenharia_obras": {
        "margem_minima": 0.05,  # 5% min margin
        "margem_alvo": 0.12,  # 12% target
        "bdi_referencia": 0.25,  # 25% BDI reference
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

# Map 2-digit CNAE prefix to sector
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
# COMPETITION ESTIMATION
# ============================================================


def _estimate_competitors(hhi: float | None, concentration: str | None) -> int:
    """Estimate number of active bidders from HHI/concentration."""
    if hhi is not None and hhi > 0:
        # HHI = sum(share^2). With N equal competitors, HHI = 1/N
        # Effective N = 1/HHI
        effective_n = 1.0 / hhi
        # Add noise factor — actual bidders ≈ 1.5x effective
        return max(2, min(20, round(effective_n * 1.5)))

    # Fallback to concentration label
    estimates = {
        "BAIXA": 8,
        "MODERADA": 5,
        "ALTA": 3,
        "MUITO_ALTA": 2,
    }
    return estimates.get((concentration or "").upper(), 5)


# ============================================================
# PROBABILITY MODEL
# ============================================================


def _p_win(
    desconto_ofertado: float,
    desconto_mediano_hist: float,
    num_competidores: int,
    std_descontos: float,
) -> float:
    """
    Estimate P(win) given a discount offer.

    Model: Beta CDF approximation.
    If our discount > historical median, we're likely below the competition.
    Adjusted for number of competitors.
    """
    if std_descontos <= 0:
        std_descontos = 0.05  # 5% default spread

    # Z-score: how many std devs above the median our discount is
    z = (desconto_ofertado - desconto_mediano_hist) / std_descontos

    # Normal CDF approximation (logistic function)
    cdf = 1.0 / (1.0 + math.exp(-1.7 * z))

    # Adjust for competition: with N bidders, P(winning) = P(being best of N)
    # If we're at the Xth percentile, P(all others worse) = X^(N-1)
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
    Simulate optimal bid for an edital.

    Args:
        edital: Edital dict with valor_estimado
        competitive_intel: From intel-collect competitive_intel field
        benchmark: Price benchmark data with desconto_mediano, desconto_p25, etc.
        cnae_principal: Company CNAE for sector margin lookup

    Returns:
        BidSimulation with suggested bid and probability analysis
    """
    valor = float(edital.get("valor_estimado") or 0)
    sector = _get_sector(cnae_principal)
    margins = SECTOR_MARGINS.get(sector, SECTOR_MARGINS["default"])

    # Extract competitive data
    ci = competitive_intel or {}
    hhi = ci.get("hhi")
    concentration = ci.get("concentration") or ci.get("predicted_competition")
    num_competitors = _estimate_competitors(hhi, concentration)

    # Extract benchmark data — check both _orgao and plain key variants (field naming evolved)
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

    # --- Insufficient data fallback ---
    if valor <= 0 or historico_n < 3:
        return BidSimulation(
            lance_sugerido=valor,
            desconto_sugerido_pct=0.0,
            p_vitoria_pct=0.0,
            margem_liquida_pct=0.0,
            valor_esperado=0.0,
            lance_agressivo=valor,
            lance_conservador=valor,
            desconto_agressivo_pct=0.0,
            desconto_conservador_pct=0.0,
            competidores_esperados=num_competitors,
            historico_contratos=historico_n,
            confianca="INSUFICIENTE",
            racional=(
                f"Dados insuficientes para simulação ({historico_n} contratos, "
                f"mínimo 3). Lance sugerido igual ao valor estimado."
            ),
        )

    # --- Calculate optimal discount ---
    margem_min = margins["margem_minima"]
    margem_alvo = margins["margem_alvo"]

    # Start from historical median and adjust
    desconto_base = desconto_mediano

    # Strategy: offer slightly above median to increase P(win)
    # but not so much that margin drops below minimum
    desconto_sugerido = desconto_base + (std_descontos * 0.3)  # 0.3 std above median

    # Cap at maximum feasible (margin floor)
    max_desconto = 1.0 - margem_min
    desconto_sugerido = min(desconto_sugerido, max_desconto)

    # Aggressive: P75 + small buffer (high win chance, lower margin)
    desconto_agressivo = min(
        desconto_p75 + (std_descontos * 0.5),
        max_desconto,
    )

    # Conservative: P25 (lower win chance, higher margin)
    desconto_conservador = max(desconto_p25, margem_alvo)

    # Ensure ordering
    if desconto_conservador > desconto_sugerido:
        desconto_conservador = desconto_sugerido * 0.85
    if desconto_agressivo < desconto_sugerido:
        desconto_agressivo = min(desconto_sugerido * 1.15, max_desconto)

    # Calculate values
    lance_sugerido = valor * (1 - desconto_sugerido)
    lance_agressivo = valor * (1 - desconto_agressivo)
    lance_conservador = valor * (1 - desconto_conservador)

    # Probability estimation
    p_win = _p_win(desconto_sugerido, desconto_mediano, num_competitors, std_descontos)
    # Margin = how much of the BDI remains after giving the discount
    # BDI is already embedded in valor_estimado, so: margem = bdi - desconto
    bdi = margins["bdi_referencia"]
    margem = bdi - desconto_sugerido  # e.g., BDI 25% - desconto 4.3% = 20.7% margin

    # Confidence level
    if historico_n >= 10 and std_descontos > 0:
        confianca = "ALTA"
    elif historico_n >= 5:
        confianca = "MEDIA"
    else:
        confianca = "BAIXA"

    # Build rationale
    parts = []
    parts.append(f"Baseado em {historico_n} contratos do orgao (desconto mediano {desconto_mediano:.1%})")
    if num_competitors > 0:
        parts.append(f"~{num_competitors} concorrentes esperados")
    parts.append(f"Margem liquida projetada: {margem:.1%} (BDI ref: {bdi:.0%}, desconto: {desconto_sugerido:.1%})")
    if p_win >= 0.6:
        parts.append("Probabilidade favoravel de vitoria")
    elif p_win >= 0.3:
        parts.append("Probabilidade moderada — considere ajustar conforme urgencia")
    else:
        parts.append("Probabilidade baixa — lance conservador ou estrategia diferenciada")

    return BidSimulation(
        lance_sugerido=round(lance_sugerido, 2),
        desconto_sugerido_pct=round(desconto_sugerido * 100, 1),
        p_vitoria_pct=round(p_win * 100, 1),
        margem_liquida_pct=round(margem * 100, 1),
        valor_esperado=round(p_win * margem * valor, 2),
        lance_agressivo=round(lance_agressivo, 2),
        lance_conservador=round(lance_conservador, 2),
        desconto_agressivo_pct=round(desconto_agressivo * 100, 1),
        desconto_conservador_pct=round(desconto_conservador * 100, 1),
        competidores_esperados=num_competitors,
        historico_contratos=historico_n,
        confianca=confianca,
        racional=". ".join(parts) + ".",
    )


def format_bid_summary(sim: BidSimulation, valor_estimado: float) -> str:
    """Format bid simulation as a concise summary for reports."""
    if not sim.has_data:
        return "Dados insuficientes para simulacao de lance"

    return (
        f"Lance sugerido: R$ {sim.lance_sugerido:,.2f} "
        f"(desconto {sim.desconto_sugerido_pct:.1f}%) — "
        f"P(vitoria) {sim.p_vitoria_pct:.0f}%, "
        f"margem projetada {sim.margem_liquida_pct:.1f}%"
    )
