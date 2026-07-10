#!/usr/bin/env python3
"""
Perfil de Vitória — aprende padrões de sucesso a partir do histórico de contratos.

Analisa os contratos ganhos pela empresa (coletados via PNCP /contratos) e
constrói um perfil probabilístico de preferências:
- Faixa de valor preferida (média, std, quantis)
- Modalidades com maior taxa de vitória
- Porte de município preferido (faixas populacionais)
- Tipos de obra/serviço recorrentes (clusters de keywords)
- Peso de proximidade geográfica

Usage:
    from lib.victory_profile import build_victory_profile, score_edital_fit
    profile = build_victory_profile(contracts, company_capital)
    fit = score_edital_fit(edital, profile)  # 0.0 - 1.0
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class VictoryProfile:
    """Perfil de vitória aprendido do histórico de contratos."""

    # Value preferences
    valor_mean: float = 0.0
    valor_std: float = 0.0
    valor_q25: float = 0.0
    valor_q75: float = 0.0
    valor_min: float = 0.0
    valor_max: float = 0.0

    # Modalidade preferences (modalidade_code -> frequency ratio 0-1)
    modalidade_weights: dict[int, float] = field(default_factory=dict)

    # Municipality size preferences (pop bracket label -> frequency ratio)
    pop_bracket_weights: dict[str, float] = field(default_factory=dict)

    # Keyword clusters (keyword -> frequency in won contracts)
    keyword_freq: dict[str, float] = field(default_factory=dict)

    # Distance preferences
    dist_mean_km: float = 0.0
    dist_max_km: float = 0.0

    # UF preferences (uf -> frequency ratio)
    uf_weights: dict[str, float] = field(default_factory=dict)

    # Metadata
    total_contracts: int = 0
    period_months: int = 24
    company_capital: float = 0.0

    @property
    def has_data(self) -> bool:
        return self.total_contracts >= 3


# ============================================================
# POPULATION BRACKETS
# ============================================================

POP_BRACKETS = [
    (5_000, "micro"),        # < 5k hab
    (20_000, "pequeno"),     # 5k-20k
    (100_000, "medio"),      # 20k-100k
    (500_000, "grande"),     # 100k-500k
    (float("inf"), "metropole"),  # > 500k
]


def _pop_bracket(pop: float | None) -> str:
    if not pop or pop <= 0:
        return "desconhecido"
    for threshold, label in POP_BRACKETS:
        if pop < threshold:
            return label
    return "metropole"


# ============================================================
# KEYWORD EXTRACTION
# ============================================================

_STOP_WORDS = {
    "de", "da", "do", "das", "dos", "para", "com", "por", "em", "no",
    "na", "nos", "nas", "ao", "aos", "um", "uma", "uns", "umas", "se",
    "ou", "que", "e", "a", "o", "as", "os", "ser", "ter", "esta",
    "este", "essa", "esse", "seu", "sua", "contratacao", "empresa",
    "servico", "servicos", "objeto", "licitacao", "pregao", "edital",
}


def _extract_keywords(text: str, min_len: int = 4) -> list[str]:
    """Extract meaningful keywords from object text."""
    words = re.findall(r"[a-záàâãéêíóôõúç]+", text.lower())
    return [w for w in words if len(w) >= min_len and w not in _STOP_WORDS]


# ============================================================
# PROFILE BUILDER
# ============================================================


def build_victory_profile(
    contracts: list[dict[str, Any]],
    company_capital: float = 0.0,
    company_ufs: list[str] | None = None,
) -> VictoryProfile:
    """
    Build a VictoryProfile from historical contracts.

    Args:
        contracts: List of contract dicts from PNCP /contratos or competitive_intel.
            Expected fields: valor_contrato, modalidade_code, uf, municipio,
            populacao (optional), objeto, distancia_km (optional)
        company_capital: Company's registered capital (capital_social)
        company_ufs: UFs where company operates (for distance estimation)

    Returns:
        VictoryProfile with learned weights
    """
    profile = VictoryProfile(company_capital=company_capital)

    if not contracts or len(contracts) < 3:
        profile.total_contracts = len(contracts) if contracts else 0
        return profile

    # --- Value statistics ---
    valores = [
        float(c.get("valor_contrato") or c.get("valor_estimado") or 0)
        for c in contracts
    ]
    valores = [v for v in valores if v > 0]

    if valores:
        valores.sort()
        n = len(valores)
        profile.valor_mean = sum(valores) / n
        profile.valor_std = (
            sum((v - profile.valor_mean) ** 2 for v in valores) / n
        ) ** 0.5
        profile.valor_min = valores[0]
        profile.valor_max = valores[-1]
        profile.valor_q25 = valores[max(0, n // 4)]
        profile.valor_q75 = valores[min(n - 1, 3 * n // 4)]

    # --- Modalidade preferences ---
    mod_counts: Counter[int] = Counter()
    for c in contracts:
        mod = c.get("modalidade_code")
        if mod is not None:
            mod_counts[int(mod)] += 1
    total_mod = sum(mod_counts.values()) or 1
    profile.modalidade_weights = {
        m: count / total_mod for m, count in mod_counts.items()
    }

    # --- Population bracket preferences ---
    pop_counts: Counter[str] = Counter()
    for c in contracts:
        pop = c.get("populacao") or c.get("ibge", {}).get("populacao")
        bracket = _pop_bracket(pop)
        if bracket != "desconhecido":
            pop_counts[bracket] += 1
    total_pop = sum(pop_counts.values()) or 1
    profile.pop_bracket_weights = {
        b: count / total_pop for b, count in pop_counts.items()
    }

    # --- Keyword clusters ---
    kw_counts: Counter[str] = Counter()
    for c in contracts:
        obj = c.get("objeto", "")
        kws = _extract_keywords(obj)
        kw_counts.update(kws)
    # Normalize by total contracts
    total_c = len(contracts)
    profile.keyword_freq = {
        kw: count / total_c
        for kw, count in kw_counts.most_common(50)
        if count >= 2  # Minimum 2 occurrences
    }

    # --- Distance preferences ---
    dists = [
        float(c.get("distancia_km") or c.get("distancia", {}).get("km") or 0)
        for c in contracts
    ]
    dists = [d for d in dists if d > 0]
    if dists:
        profile.dist_mean_km = sum(dists) / len(dists)
        profile.dist_max_km = max(dists)

    # --- UF preferences ---
    uf_counts: Counter[str] = Counter()
    for c in contracts:
        uf = c.get("uf", "")
        if uf:
            uf_counts[uf] += 1
    total_uf = sum(uf_counts.values()) or 1
    profile.uf_weights = {
        uf: count / total_uf for uf, count in uf_counts.items()
    }

    profile.total_contracts = len(contracts)
    return profile


# ============================================================
# SCORING — FIT BETWEEN EDITAL AND PROFILE
# ============================================================

# Component weights (sum = 1.0)
W_VALUE = 0.30       # Value range fit
W_KEYWORD = 0.25     # Keyword similarity
W_MODALIDADE = 0.15  # Modalidade preference
W_GEOGRAPHY = 0.15   # UF + distance
W_POPULATION = 0.15  # Municipality size


def _score_value_fit(valor: float, profile: VictoryProfile) -> float:
    """Score how well the edital value fits the company's historical range."""
    if not profile.valor_mean or valor <= 0:
        return 0.5  # Neutral when no data

    # Gaussian fit centered on mean, penalize extremes
    if profile.valor_std > 0:
        z = abs(valor - profile.valor_mean) / profile.valor_std
        score = math.exp(-0.5 * z * z)
    else:
        # No variance — exact match is 1.0, anything else decays
        ratio = valor / profile.valor_mean if profile.valor_mean else 1.0
        score = max(0, 1 - abs(1 - ratio))

    # Hard penalty for values > 3x the historical max
    if profile.valor_max > 0 and valor > profile.valor_max * 3:
        score *= 0.3

    return min(1.0, max(0.0, score))


def _score_keyword_fit(objeto: str, profile: VictoryProfile) -> float:
    """Score keyword overlap between edital object and historical wins."""
    if not profile.keyword_freq:
        return 0.5  # Neutral

    edital_kws = set(_extract_keywords(objeto))
    if not edital_kws:
        return 0.3

    # Weighted overlap: keywords that appear more in wins count more
    overlap_score = 0.0
    for kw in edital_kws:
        if kw in profile.keyword_freq:
            overlap_score += profile.keyword_freq[kw]

    # Normalize by number of edital keywords (cap at 1.0)
    normalized = overlap_score / max(len(edital_kws), 1)
    return min(1.0, normalized * 3)  # Scale up (typical values are low)


def _score_modalidade_fit(modalidade_code: int | None, profile: VictoryProfile) -> float:
    """Score how well the modalidade matches historical preferences."""
    if not profile.modalidade_weights or modalidade_code is None:
        return 0.5

    return profile.modalidade_weights.get(modalidade_code, 0.1)


def _score_geography_fit(
    uf: str,
    distancia_km: float | None,
    profile: VictoryProfile,
) -> float:
    """Score geographic proximity and UF preference."""
    score = 0.5  # Neutral baseline

    # UF preference (0-0.5 component)
    if profile.uf_weights:
        uf_score = profile.uf_weights.get(uf, 0.0)
        score = 0.5 + (uf_score * 0.5)  # 0.5-1.0 range

    # Distance penalty (reduces score)
    if distancia_km is not None and distancia_km > 0:
        if profile.dist_mean_km > 0:
            # Penalty if much farther than historical mean
            ratio = distancia_km / profile.dist_mean_km
            if ratio > 2.0:
                score *= max(0.3, 1.0 - (ratio - 2.0) * 0.2)
        else:
            # No historical distance data — use absolute penalty
            if distancia_km > 500:
                score *= 0.7
            elif distancia_km > 300:
                score *= 0.85

    return min(1.0, max(0.0, score))


def _score_population_fit(populacao: float | None, profile: VictoryProfile) -> float:
    """Score how well municipality size matches historical preferences."""
    if not profile.pop_bracket_weights:
        return 0.5

    bracket = _pop_bracket(populacao)
    if bracket == "desconhecido":
        return 0.4

    return max(0.1, profile.pop_bracket_weights.get(bracket, 0.1))


def score_edital_fit(edital: dict[str, Any], profile: VictoryProfile) -> float:
    """
    Score how well an edital fits the company's historical victory profile.

    Returns:
        Float 0.0-1.0 where:
        - 0.0-0.3: Poor fit (very different from historical wins)
        - 0.3-0.5: Moderate fit
        - 0.5-0.7: Good fit (similar to past wins)
        - 0.7-1.0: Excellent fit (strong match with historical pattern)
    """
    if not profile.has_data:
        return 0.5  # No data → neutral score

    valor = float(edital.get("valor_estimado") or 0)
    objeto = edital.get("objeto", "")
    modalidade = edital.get("modalidade_code")
    uf = edital.get("uf", "")
    dist_data = edital.get("distancia", {})
    distancia_km = float(dist_data.get("km") or 0) if isinstance(dist_data, dict) else None
    pop_data = edital.get("ibge", {})
    populacao = float(pop_data.get("populacao") or 0) if isinstance(pop_data, dict) else None

    s_value = _score_value_fit(valor, profile)
    s_keyword = _score_keyword_fit(objeto, profile)
    s_mod = _score_modalidade_fit(modalidade, profile)
    s_geo = _score_geography_fit(uf, distancia_km, profile)
    s_pop = _score_population_fit(populacao, profile)

    weighted = (
        W_VALUE * s_value
        + W_KEYWORD * s_keyword
        + W_MODALIDADE * s_mod
        + W_GEOGRAPHY * s_geo
        + W_POPULATION * s_pop
    )

    return round(min(1.0, max(0.0, weighted)), 4)


def format_fit_label(score: float) -> str:
    """Convert fit score to human-readable label."""
    if score >= 0.70:
        return "Excelente"
    if score >= 0.50:
        return "Bom"
    if score >= 0.30:
        return "Moderado"
    return "Baixo"
