"""
Buyer Intelligence — Perfil e Ranking de Órgãos Compradores.

Foco: AEC (engenharia/construção/obras), Santa Catarina, raio 200km.
Fonte primária: pncp_supplier_contracts (PNCP).

O ranking é explicável, multi-fator e orientado à tomada de decisão comercial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# AEC classification
# ---------------------------------------------------------------------------

AEC_KEYWORDS = [
    "obra", "construção", "edificação", "pavimentação", "drenagem",
    "saneamento", "reforma", "manutenção predial", "engenharia",
    "infraestrutura", "instalação", "fiscalização obra", "execução",
    "edifício", "rodovia", "ponte", "galeria", "concreto", "asfalto",
    "terraplenagem", "fundação", "estrutura", "contenção",
    "revestimento", "telhado", "cobertura", "hidráulica",
    "elétrica predial", "combate incêndio", "acessibilidade",
    "calçada", "passeio", "praça", "urbanização", "paisagismo",
    "arquitet", "projeto executivo", "projeto básico",
    "memorial descritivo", "orçamento obra", "CREA", "CAU",
]


def is_aec(objeto: str | None) -> bool:
    """Classifica um objeto de contrato como AEC ou não."""
    if not objeto:
        return False
    obj_lower = objeto.lower()
    return any(kw in obj_lower for kw in AEC_KEYWORDS)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class BuyerProfile:
    """Perfil completo de um órgão comprador."""

    cnpj_8: str
    razao_social: str
    municipio: str
    distancia_km: float | None

    # Contratos
    total_contratos: int = 0
    contratos_aec: int = 0
    valor_total: float = 0.0
    valor_total_aec: float = 0.0
    ticket_medio: float = 0.0
    ticket_medio_aec: float = 0.0
    mediana_valor: float = 0.0
    p25_valor: float = 0.0
    p75_valor: float = 0.0

    # Temporal
    primeira_data: str | None = None
    ultima_data: str | None = None
    frequencia_anual: float = 0.0
    contratos_ultimo_ano: int = 0

    # Fornecedores
    fornecedores_distintos: int = 0
    top_fornecedores: list[dict] = field(default_factory=list)
    hhi_concentracao: float = 0.0

    # Contratos vincendos
    contratos_vencendo_90d: int = 0
    contratos_vencendo_180d: int = 0
    contratos_vencendo_365d: int = 0

    # Oportunidades
    oportunidades_abertas: int = 0

    # Metadados
    qualidade_dados: str = "unknown"
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cnpj_8": self.cnpj_8,
            "razao_social": self.razao_social,
            "municipio": self.municipio,
            "distancia_km": self.distancia_km,
            "total_contratos": self.total_contratos,
            "contratos_aec": self.contratos_aec,
            "valor_total": self.valor_total,
            "valor_total_aec": self.valor_total_aec,
            "ticket_medio": self.ticket_medio,
            "ticket_medio_aec": self.ticket_medio_aec,
            "mediana_valor": self.mediana_valor,
            "p25_valor": self.p25_valor,
            "p75_valor": self.p75_valor,
            "primeira_data": self.primeira_data,
            "ultima_data": self.ultima_data,
            "frequencia_anual": self.frequencia_anual,
            "contratos_ultimo_ano": self.contratos_ultimo_ano,
            "fornecedores_distintos": self.fornecedores_distintos,
            "top_fornecedores": self.top_fornecedores,
            "hhi_concentracao": self.hhi_concentracao,
            "contratos_vencendo_90d": self.contratos_vencendo_90d,
            "contratos_vencendo_180d": self.contratos_vencendo_180d,
            "contratos_vencendo_365d": self.contratos_vencendo_365d,
            "oportunidades_abertas": self.oportunidades_abertas,
            "qualidade_dados": self.qualidade_dados,
            "limitations": self.limitations,
        }


@dataclass
class BuyerRankingEntry:
    """Entrada no ranking de órgãos com scores por fator."""

    cnpj_8: str
    razao_social: str
    municipio: str
    distancia_km: float | None

    score_total: float = 0.0
    score_aderencia: float = 0.0      # 0-25: AEC relevance
    score_volume: float = 0.0          # 0-20: contract volume/value
    score_frequencia: float = 0.0      # 0-15: contracting frequency
    score_ticket: float = 0.0          # 0-10: ticket compatibility
    score_proximidade: float = 0.0     # 0-10: geographic proximity
    score_oportunidades: float = 0.0   # 0-10: current open opportunities
    score_renovacao: float = 0.0       # 0-5: expiring contracts signal
    score_concentracao: float = 0.0    # 0-5: competitive concentration (lower=better)

    classificacao: str = "REVIEW"      # PRIORITARIO / ATIVO / REVIEW / BAIXA_PRIORIDADE

    def to_dict(self) -> dict[str, Any]:
        return {
            "cnpj_8": self.cnpj_8,
            "razao_social": self.razao_social,
            "municipio": self.municipio,
            "distancia_km": self.distancia_km,
            "score_total": round(self.score_total, 1),
            "score_aderencia": round(self.score_aderencia, 1),
            "score_volume": round(self.score_volume, 1),
            "score_frequencia": round(self.score_frequencia, 1),
            "score_ticket": round(self.score_ticket, 1),
            "score_proximidade": round(self.score_proximidade, 1),
            "score_oportunidades": round(self.score_oportunidades, 1),
            "score_renovacao": round(self.score_renovacao, 1),
            "score_concentracao": round(self.score_concentracao, 1),
            "classificacao": self.classificacao,
        }


# ---------------------------------------------------------------------------
# Ranking engine
# ---------------------------------------------------------------------------


def compute_buyer_ranking(
    profiles: list[BuyerProfile],
    extra_aec_pct: float = 0.30,
) -> list[BuyerRankingEntry]:
    """Calcula ranking de órgãos a partir dos perfis.

    Args:
        profiles: lista de BuyerProfile
        extra_aec_pct: percentual mínimo de contratos AEC para aderência máxima

    Returns:
        Lista ordenada por score_total decrescente
    """
    if not profiles:
        return []

    # Extrair máximos para normalização
    max_contratos = max(p.total_contratos for p in profiles) or 1
    max_valor = max(p.valor_total for p in profiles) or 1
    max_freq = max(p.frequencia_anual for p in profiles) or 1
    max_abertas = max(p.oportunidades_abertas for p in profiles) or 1
    max_vencendo = max(p.contratos_vencendo_90d for p in profiles) or 1

    rankings = []
    for p in profiles:
        # Aderência (0-25): % de contratos AEC, bônus por AEC puro
        aec_pct = p.contratos_aec / max(p.total_contratos, 1)
        score_aderencia = min(25, (aec_pct / max(extra_aec_pct, 0.01)) * 20 + (5 if aec_pct > 0.5 else 0))

        # Volume (0-20): contratos + valor
        vol_contratos = min(10, (p.total_contratos / max_contratos) * 10)
        vol_valor = min(10, (p.valor_total / max_valor) * 10)
        score_volume = vol_contratos + vol_valor

        # Frequência (0-15): contratos por ano
        score_frequencia = min(15, (p.frequencia_anual / max_freq) * 15)

        # Ticket (0-10): compatibilidade com engenharia (ticket > 100K = bom)
        ticket = p.ticket_medio_aec or p.ticket_medio
        score_ticket = min(10, (ticket / 500_000) * 10)  # R$500K = 10

        # Proximidade (0-10): mais perto = melhor
        if p.distancia_km is None:
            score_proximidade = 2
        elif p.distancia_km <= 50:
            score_proximidade = 10
        elif p.distancia_km <= 100:
            score_proximidade = 7
        elif p.distancia_km <= 150:
            score_proximidade = 5
        elif p.distancia_km <= 200:
            score_proximidade = 3
        else:
            score_proximidade = 1

        # Oportunidades (0-10): editais abertos
        score_oportunidades = min(10, (p.oportunidades_abertas / max_abertas) * 10) if max_abertas > 0 else 0

        # Renovação (0-5): contratos vincendos = sinal de possível nova contratação
        score_renovacao = min(5, (p.contratos_vencendo_90d / max_vencendo) * 5) if max_vencendo > 0 else 0

        # Concentração (0-5): menos concentrado = mais acessível
        hhi = p.hhi_concentracao
        if hhi <= 1500:
            score_concentracao = 5  # não concentrado
        elif hhi <= 2500:
            score_concentracao = 3  # moderado
        else:
            score_concentracao = 1  # concentrado

        score_total = (
            score_aderencia
            + score_volume
            + score_frequencia
            + score_ticket
            + score_proximidade
            + score_oportunidades
            + score_renovacao
            + score_concentracao
        )

        # Classificação
        if score_total >= 60:
            classificacao = "PRIORITARIO"
        elif score_total >= 40:
            classificacao = "ATIVO"
        elif score_total >= 20:
            classificacao = "REVIEW"
        else:
            classificacao = "BAIXA_PRIORIDADE"

        rankings.append(BuyerRankingEntry(
            cnpj_8=p.cnpj_8,
            razao_social=p.razao_social,
            municipio=p.municipio,
            distancia_km=p.distancia_km,
            score_total=score_total,
            score_aderencia=score_aderencia,
            score_volume=score_volume,
            score_frequencia=score_frequencia,
            score_ticket=score_ticket,
            score_proximidade=score_proximidade,
            score_oportunidades=score_oportunidades,
            score_renovacao=score_renovacao,
            score_concentracao=score_concentracao,
            classificacao=classificacao,
        ))

    rankings.sort(key=lambda r: r.score_total, reverse=True)
    return rankings
