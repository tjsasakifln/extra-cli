#!/usr/bin/env python3
"""
Estimador de custo de proposta para sessoes presenciais.

Calcula custo estimado de deslocamento, hospedagem, alimentacao,
pedagio e tempo tecnico com base na distancia sede->edital.

Usage (como modulo):
    from lib.cost_estimator import estimate_proposal_cost
    cost = estimate_proposal_cost(distancia_km=350, duracao_horas=4.5)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostParams:
    """Parametros configuraveis do modelo de custo."""
    custo_km: float = 0.80                  # R$/km (ANTT referencia)
    diaria_hospedagem_interior: float = 180.0  # R$ interior
    diaria_hospedagem_capital: float = 280.0   # R$ capital
    per_diem_alimentacao: float = 80.0       # R$/dia
    custo_hora_tecnico: float = 150.0        # R$/hora
    horas_sessao: float = 4.0               # horas estimadas em sessao presencial
    limiar_hospedagem_km: float = 200.0      # acima disso: precisa hospedagem
    limiar_duas_diarias_km: float = 500.0    # acima disso: 2 diarias
    pedagio_por_faixa: dict = field(default_factory=lambda: {
        100: 0.0,       # ate 100km: sem pedagio
        300: 30.0,      # 100-300km: ~R$30
        600: 80.0,      # 300-600km: ~R$80
        1000: 150.0,    # 600-1000km: ~R$150
        99999: 250.0,   # >1000km: ~R$250
    })
    custo_fixo_proposta: float = 0.0      # Fixed cost: certifications, ART, docs
    custo_fixo_mobilizacao: float = 0.0    # Fixed cost: team, equipment


# ============================================================
# SECTOR COST PROFILES
# ============================================================

SECTOR_COST_PROFILES: dict[str, CostParams] = {
    "engenharia_obras": CostParams(
        custo_hora_tecnico=180.0,
        horas_sessao=6.0,
        custo_fixo_proposta=2500.0,
        custo_fixo_mobilizacao=5000.0,
    ),
    "ti_software": CostParams(
        custo_hora_tecnico=120.0,
        horas_sessao=3.0,
        custo_fixo_proposta=800.0,
        custo_fixo_mobilizacao=0.0,
    ),
    "consultoria": CostParams(
        custo_hora_tecnico=150.0,
        horas_sessao=4.0,
        custo_fixo_proposta=1200.0,
        custo_fixo_mobilizacao=0.0,
    ),
    "avaliacao_imoveis": CostParams(
        custo_hora_tecnico=160.0,
        horas_sessao=8.0,
        custo_fixo_proposta=1500.0,
        custo_fixo_mobilizacao=2000.0,
    ),
    "saude": CostParams(
        custo_hora_tecnico=130.0,
        horas_sessao=4.0,
        custo_fixo_proposta=1000.0,
        custo_fixo_mobilizacao=0.0,
    ),
    "default": CostParams(),  # Original defaults
}

# ============================================================
# CNAE PREFIX -> SECTOR PROFILE MAPPING
# ============================================================

CNAE_TO_COST_SECTOR: dict[str, str] = {
    "41": "engenharia_obras",    # Construcao de edificios
    "42": "engenharia_obras",    # Obras de infraestrutura
    "43": "engenharia_obras",    # Servicos especializados para construcao
    "71": "engenharia_obras",    # Servicos de arquitetura e engenharia
    "62": "ti_software",         # Desenvolvimento de software
    "63": "ti_software",         # Servicos de TI
    "70": "consultoria",         # Consultoria em gestao
    "69": "consultoria",         # Juridica e contabilidade
    "68": "avaliacao_imoveis",   # Atividades imobiliarias
    "86": "saude",               # Atividades de atencao a saude
}


def get_sector_params(cnae_principal: str) -> CostParams:
    """Get cost params for a CNAE prefix (first 2 digits)."""
    prefix = str(cnae_principal)[:2]
    sector = CNAE_TO_COST_SECTOR.get(prefix, "default")
    return SECTOR_COST_PROFILES.get(sector, SECTOR_COST_PROFILES["default"])


DEFAULT_PARAMS = CostParams()


def estimate_proposal_cost(
    distancia_km: float | None,
    duracao_horas: float | None,
    is_capital: bool = False,
    is_eletronico: bool = False,
    params: CostParams | None = None,
) -> dict[str, Any]:
    """Estima custo de proposta para participacao em edital.

    Args:
        distancia_km: Distancia sede->local em km (OSRM)
        duracao_horas: Tempo de viagem em horas (OSRM, uma via)
        is_capital: Se o destino e capital de estado
        is_eletronico: Se a modalidade e eletronica (sem deslocamento)
        params: Parametros customizaveis (default: DEFAULT_PARAMS)

    Returns:
        dict com total, breakdown, e metadata
    """
    p = params or DEFAULT_PARAMS

    # Sessao eletronica: custo base (tempo tecnico) + visita tecnica se distante (>200km)
    if is_eletronico:
        tempo_preparo = p.horas_sessao * p.custo_hora_tecnico
        custo_base = max(600.0, tempo_preparo)  # Minimo R$ 600

        # Site visit surcharge: pregoes eletronicos podem exigir visita tecnica previa
        visita_tecnica = 0.0
        km = distancia_km if (distancia_km is not None and distancia_km > 0) else 0.0
        if km > 200:
            visita_tecnica = km * 2.0  # R$ 2/km (deslocamento ida+volta simplificado)

        total_eletronico = custo_base + visita_tecnica
        nota_eletronico = "Sessao eletronica -- custo limitado a tempo de preparacao da proposta"
        if visita_tecnica > 0:
            nota_eletronico += f"; acrescimo de R${visita_tecnica:.0f} para visita tecnica ({km:.0f}km)"

        return {
            "total": round(total_eletronico, 2),
            "modalidade_tipo": "eletronica",
            "breakdown": {
                "deslocamento": 0.0,
                "hospedagem": 0.0,
                "alimentacao": 0.0,
                "pedagio": 0.0,
                "tempo_tecnico": round(custo_base, 2),
                "visita_tecnica": round(visita_tecnica, 2),
            },
            "premissas": {
                "horas_preparo": p.horas_sessao,
                "custo_hora": p.custo_hora_tecnico,
                "custo_base_minimo": 600.0,
                "distancia_km_visita": round(km, 1),
                "custo_km_visita": 2.0 if km > 200 else 0.0,
            },
            "nota": nota_eletronico,
        }

    # Se nao tem dados de distancia, retornar indisponivel
    if distancia_km is None or distancia_km <= 0:
        return {
            "total": None,
            "modalidade_tipo": "presencial",
            "breakdown": None,
            "premissas": None,
            "nota": "Distancia indisponivel -- custo nao calculado",
        }

    dur = duracao_horas or (distancia_km / 60.0)  # fallback: ~60km/h

    # 1. Deslocamento (ida + volta)
    deslocamento = distancia_km * 2 * p.custo_km

    # 2. Hospedagem
    hospedagem = 0.0
    diarias = 0
    if distancia_km > p.limiar_hospedagem_km:
        diaria = p.diaria_hospedagem_capital if is_capital else p.diaria_hospedagem_interior
        diarias = 2 if distancia_km > p.limiar_duas_diarias_km else 1
        hospedagem = diarias * diaria

    # 3. Alimentacao
    # Se precisa hospedagem: dias completos; senao: 1 refeicao
    if diarias > 0:
        alimentacao = (diarias + 1) * p.per_diem_alimentacao  # +1 dia de viagem
    elif distancia_km > 50:
        alimentacao = p.per_diem_alimentacao  # 1 refeicao
    else:
        alimentacao = 0.0

    # 4. Pedagio (por faixa)
    pedagio = 0.0
    for faixa_km, valor in sorted(p.pedagio_por_faixa.items()):
        if distancia_km <= faixa_km:
            pedagio = valor * 2  # ida + volta
            break

    # 5. Tempo tecnico (viagem + sessao)
    horas_viagem = dur * 2  # ida + volta
    horas_total = horas_viagem + p.horas_sessao
    tempo_tecnico = horas_total * p.custo_hora_tecnico

    # 6. Custos fixos setoriais (proposta + mobilizacao)
    custo_fixo_proposta = p.custo_fixo_proposta
    custo_fixo_mobilizacao = p.custo_fixo_mobilizacao

    total = deslocamento + hospedagem + alimentacao + pedagio + tempo_tecnico
    total += custo_fixo_proposta + custo_fixo_mobilizacao

    return {
        "total": round(total, 2),
        "modalidade_tipo": "presencial",
        "breakdown": {
            "deslocamento": round(deslocamento, 2),
            "hospedagem": round(hospedagem, 2),
            "alimentacao": round(alimentacao, 2),
            "pedagio": round(pedagio, 2),
            "tempo_tecnico": round(tempo_tecnico, 2),
            "custo_fixo_proposta": round(custo_fixo_proposta, 2),
            "custo_fixo_mobilizacao": round(custo_fixo_mobilizacao, 2),
        },
        "premissas": {
            "distancia_km": round(distancia_km, 1),
            "duracao_horas_via": round(dur, 1),
            "horas_viagem_total": round(horas_viagem, 1),
            "horas_sessao": p.horas_sessao,
            "diarias_hospedagem": diarias,
            "custo_km": p.custo_km,
            "custo_hora_tecnico": p.custo_hora_tecnico,
            "custo_fixo_proposta": custo_fixo_proposta,
            "custo_fixo_mobilizacao": custo_fixo_mobilizacao,
        },
        "nota": _build_nota(distancia_km, diarias, is_capital),
    }


def _build_nota(distancia_km: float, diarias: int, is_capital: bool) -> str:
    """Gera nota explicativa do custo."""
    parts = []
    if distancia_km <= 50:
        parts.append("Proximidade favoravel -- deslocamento local")
    elif distancia_km <= 200:
        parts.append("Deslocamento regional -- sem necessidade de hospedagem")
    elif distancia_km <= 500:
        parts.append(f"Deslocamento interestadual -- {diarias} diaria(s) de hospedagem")
    else:
        parts.append(f"Deslocamento de longa distancia -- {diarias} diarias de hospedagem")

    if is_capital:
        parts.append("destino em capital (custo de hospedagem majorado)")

    return "; ".join(parts)


def estimate_roi_simple(
    valor_edital: float | None,
    custo_proposta: float | None,
) -> dict[str, Any] | None:
    """Calcula ROI simplificado da participacao.

    Returns:
        dict com ratio, classificacao, ou None se dados insuficientes
    """
    if not valor_edital or not custo_proposta or custo_proposta <= 0:
        return None

    ratio = valor_edital / custo_proposta

    if ratio >= 500:
        classificacao = "EXCELENTE"
    elif ratio >= 100:
        classificacao = "BOM"
    elif ratio >= 30:
        classificacao = "MODERADO"
    elif ratio >= 10:
        classificacao = "MARGINAL"
    else:
        classificacao = "DESFAVORAVEL"

    return {
        "ratio_valor_custo": round(ratio, 0),
        "classificacao": classificacao,
        "custo_percentual_valor": round((custo_proposta / valor_edital) * 100, 2),
    }
