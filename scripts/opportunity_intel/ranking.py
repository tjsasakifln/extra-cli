"""Explainable ranking for bidding opportunities.

Deterministic rules produce:
- ranking: GO, REVIEW, or NO_GO
- score: 0–100
- fatores: positive and negative factors
- regras: which rules were triggered
- confianca: HIGH, MEDIUM, LOW

Rules are applied in priority order. Higher priority rules
can override or cap scores from lower priority rules.

Design principles:
- Deterministic first — LLM optional enrichment, never requirement
- Explainable — every factor traces to a rule
- Conservative — NO_GO is default for insufficient data
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Rule definition
# ---------------------------------------------------------------------------


class Rule:
    """A single ranking rule with weight and explanation."""

    def __init__(
        self,
        name: str,
        weight: int,
        description: str,
        category: str = "neutral",  # positive, negative, hard_block
    ):
        self.name = name
        self.weight = weight
        self.description = description
        self.category = category


# ---------------------------------------------------------------------------
# Hard-block rules (NO_GO triggers)
# ---------------------------------------------------------------------------

HARD_BLOCKS: list[Rule] = [
    Rule("status_terminal", -100, "Status terminal (revoked/annulled/failed/closed)", "hard_block"),
    Rule("data_encerramento_passada", -100, "Data de encerramento no passado sem status aberto", "hard_block"),
    Rule("sem_objeto", -100, "Sem descrição do objeto", "hard_block"),
    Rule("sem_orgao", -100, "Sem identificação do órgão", "hard_block"),
    Rule("valor_negativo", -50, "Valor estimado negativo", "hard_block"),
    Rule("fora_raio", -30, "Fora do raio de 200 km de Florianópolis", "hard_block"),
]

# ---------------------------------------------------------------------------
# Positive factors (increase score)
# ---------------------------------------------------------------------------

POSITIVE_FACTORS: list[Rule] = [
    Rule("status_open", 30, "Status confirmado como aberto", "positive"),
    Rule("data_abertura_futura", 15, "Data de abertura no futuro próximo (≤30 dias)", "positive"),
    Rule("orgao_conhecido", 10, "Órgão conhecido (match com sc_public_entities)", "positive"),
    Rule("valor_realista", 10, "Valor estimado em faixa realista (R$ 10K–R$ 50M)", "positive"),
    Rule("modalidade_competitiva", 10, "Modalidade competitiva (concorrência, pregão)", "positive"),
    Rule("documentos_completos", 15, "Possui edital e anexos", "positive"),
    Rule("dentro_raio", 15, "Dentro do raio de 200 km de Florianópolis", "positive"),
    Rule("fonte_confiavel", 5, "Fonte oficial com boa reputação", "positive"),
    Rule("dados_completos", 10, "Todos os campos obrigatórios preenchidos", "positive"),
]

# ---------------------------------------------------------------------------
# Negative factors (decrease score)
# ---------------------------------------------------------------------------

NEGATIVE_FACTORS: list[Rule] = [
    Rule("status_unknown", -20, "Status não pôde ser determinado (unknown)", "negative"),
    Rule("sem_data_abertura", -15, "Sem data de abertura/sessão", "negative"),
    Rule("sem_data_encerramento", -10, "Sem data de encerramento", "negative"),
    Rule("sem_valor", -10, "Sem valor estimado", "negative"),
    Rule("sem_edital", -10, "Sem link para edital", "negative"),
    Rule("fonte_baixa_confianca", -10, "Fonte com baixa confiabilidade conhecida", "negative"),
    Rule("modalidade_nao_competitiva", -10, "Modalidade não competitiva (dispensa, inexigibilidade)", "negative"),
    Rule("dados_incompletos", -15, "Múltiplos campos críticos ausentes", "negative"),
    Rule("publicacao_antiga", -5, "Publicação com mais de 60 dias", "negative"),
    Rule("sem_municipio", -5, "Município não identificado", "negative"),
]

# ---------------------------------------------------------------------------
# Modalidade classification
# ---------------------------------------------------------------------------

COMPETITIVE_MODALITIES: set[str] = {
    "concorrência",
    "concorrencia",
    "concorrência eletrônica",
    "concorrencia eletronica",
    "pregão",
    "pregao",
    "pregão eletrônico",
    "pregao eletronico",
    "concurso",
    "leilão",
    "leilao",
    "diálogo competitivo",
    "dialogo competitivo",
}

NON_COMPETITIVE_MODALITIES: set[str] = {
    "dispensa",
    "inexigibilidade",
    "inegixibilidade",
    "credenciamento",
    "adesão",
    "adesao",
    "chamamento público",
    "chamamento publico",
    "chamada pública",
    "chamada publica",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_ranking(
    status_canonico: str,
    orgao_cnpj: str | None = None,
    objeto: str | None = None,
    valor_estimado: float | None = None,
    modalidade: str | None = None,
    data_abertura: datetime | None = None,
    data_encerramento: datetime | None = None,
    data_publicacao: datetime | None = None,
    uf: str | None = None,
    municipio: str | None = None,
    link_edital: str | None = None,
    link_anexos: list[str] | None = None,
    has_match_entity: bool = False,
    dentro_raio: bool = False,
    fonte_confiavel: bool = True,
) -> dict[str, Any]:
    """Compute explainable ranking for an opportunity.

    Args:
        status_canonico: Computed canonical status.
        orgao_cnpj: Org CNPJ.
        objeto: Object description.
        valor_estimado: Estimated value.
        modalidade: Modality name.
        data_abertura: Opening date.
        data_encerramento: Closing date.
        data_publicacao: Publication date.
        uf: State.
        municipio: Municipality.
        link_edital: Link to edital.
        link_anexos: Links to attachments.
        has_match_entity: Whether org matches sc_public_entities.
        dentro_raio: Whether within 200km of Florianópolis.
        fonte_confiavel: Whether source is trusted.

    Returns:
        Dict with ranking, score, fatores, regras, confianca.
    """
    score = 50  # Neutral baseline
    fatores: dict[str, list[str]] = {"positivos": [], "negativos": [], "bloqueadores": []}
    regras: list[str] = []

    now = datetime.now(UTC)

    # -----------------------------------------------------------------------
    # Check hard blocks first
    # -----------------------------------------------------------------------

    block_reasons: list[str] = []

    if status_canonico in ("revoked", "annulled", "failed"):
        block_reasons.append("status_terminal")
    if status_canonico == "closed":
        block_reasons.append("status_terminal")
    if not objeto or not objeto.strip():
        block_reasons.append("sem_objeto")
    if not orgao_cnpj:
        block_reasons.append("sem_orgao")
    if valor_estimado is not None and valor_estimado < 0:
        block_reasons.append("valor_negativo")
    if data_encerramento and data_encerramento <= now and status_canonico != "open":
        block_reasons.append("data_encerramento_passada")

    for block_name in block_reasons:
        rule = next((r for r in HARD_BLOCKS if r.name == block_name), None)
        if rule:
            score = min(score, 0)
            fatores["bloqueadores"].append(rule.description)
            regras.append(f"BLOQUEIO:{rule.name}")
            score += rule.weight  # Apply penalty

    if block_reasons:
        score = max(0, min(score, 20))  # Cap at 20 if any blocks triggered
        return _build_result(score, fatores, regras, block_reasons)

    # -----------------------------------------------------------------------
    # Positive factors
    # -----------------------------------------------------------------------

    if status_canonico == "open":
        score += _apply_rule("status_open", fatores, regras, POSITIVE_FACTORS)

    if status_canonico == "upcoming":
        score += _apply_rule("status_open", fatores, regras, POSITIVE_FACTORS, weight_mod=0.7)

    if data_abertura and data_abertura > now:
        days_until = (data_abertura - now).days
        if days_until <= 30:
            score += _apply_rule("data_abertura_futura", fatores, regras, POSITIVE_FACTORS)

    if has_match_entity:
        score += _apply_rule("orgao_conhecido", fatores, regras, POSITIVE_FACTORS)

    if valor_estimado and 10_000 <= valor_estimado <= 50_000_000:
        score += _apply_rule("valor_realista", fatores, regras, POSITIVE_FACTORS)

    if modalidade and _is_competitive(modalidade):
        score += _apply_rule("modalidade_competitiva", fatores, regras, POSITIVE_FACTORS)

    if link_edital and link_anexos:
        score += _apply_rule("documentos_completos", fatores, regras, POSITIVE_FACTORS)
    elif link_edital:
        score += _apply_rule("documentos_completos", fatores, regras, POSITIVE_FACTORS, weight_mod=0.5)

    if dentro_raio:
        score += _apply_rule("dentro_raio", fatores, regras, POSITIVE_FACTORS)

    if fonte_confiavel:
        score += _apply_rule("fonte_confiavel", fatores, regras, POSITIVE_FACTORS)

    # Check data completeness
    missing = _count_missing_critical(orgao_cnpj, objeto, valor_estimado, data_abertura, data_encerramento, municipio)
    if missing == 0:
        score += _apply_rule("dados_completos", fatores, regras, POSITIVE_FACTORS)

    # -----------------------------------------------------------------------
    # Negative factors
    # -----------------------------------------------------------------------

    if status_canonico == "unknown":
        score += _apply_rule("status_unknown", fatores, regras, NEGATIVE_FACTORS)

    if not data_abertura:
        score += _apply_rule("sem_data_abertura", fatores, regras, NEGATIVE_FACTORS)

    if not data_encerramento:
        score += _apply_rule("sem_data_encerramento", fatores, regras, NEGATIVE_FACTORS)

    if not valor_estimado:
        score += _apply_rule("sem_valor", fatores, regras, NEGATIVE_FACTORS)

    if not link_edital:
        score += _apply_rule("sem_edital", fatores, regras, NEGATIVE_FACTORS)

    if not fonte_confiavel:
        score += _apply_rule("fonte_baixa_confianca", fatores, regras, NEGATIVE_FACTORS)

    if modalidade and _is_non_competitive(modalidade):
        score += _apply_rule("modalidade_nao_competitiva", fatores, regras, NEGATIVE_FACTORS)

    if missing >= 3:
        score += _apply_rule("dados_incompletos", fatores, regras, NEGATIVE_FACTORS)

    if data_publicacao and (now - data_publicacao).days > 60:
        score += _apply_rule("publicacao_antiga", fatores, regras, NEGATIVE_FACTORS)

    if not municipio:
        score += _apply_rule("sem_municipio", fatores, regras, NEGATIVE_FACTORS)

    # -----------------------------------------------------------------------
    # Determine final ranking tier
    # -----------------------------------------------------------------------

    score = max(0, min(100, score))
    ranking, confianca = _tier_from_score(score, missing)

    return {
        "ranking": ranking,
        "ranking_score": score,
        "ranking_fatores": fatores,
        "ranking_regras": regras,
        "ranking_confianca": confianca,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_rule(
    rule_name: str,
    fatores: dict[str, list[str]],
    regras: list[str],
    rule_list: list[Rule],
    weight_mod: float = 1.0,
) -> int:
    """Look up a rule by name and apply it, recording in fatores/regras."""
    rule = next((r for r in rule_list if r.name == rule_name), None)
    if rule is None:
        return 0
    regras.append(f"{rule.category.upper()}:{rule.name}")
    target_list = fatores["positivos"] if rule.category == "positive" else fatores["negativos"]
    if target_list is not None:
        target_list.append(rule.description)
    return int(rule.weight * weight_mod)


def _tier_from_score(score: int, missing_count: int) -> tuple[str, str]:
    """Map score to ranking tier and confidence."""
    if score >= 70:
        return "GO", "HIGH" if missing_count == 0 else "MEDIUM"
    if score >= 40:
        return "REVIEW", "MEDIUM" if missing_count <= 2 else "LOW"
    return "NO_GO", "LOW"


def _is_competitive(modalidade: str) -> bool:
    modalidade_lower = modalidade.strip().lower()
    return modalidade_lower in COMPETITIVE_MODALITIES


def _is_non_competitive(modalidade: str) -> bool:
    modalidade_lower = modalidade.strip().lower()
    return modalidade_lower in NON_COMPETITIVE_MODALITIES


def _count_missing_critical(
    orgao_cnpj: str | None,
    objeto: str | None,
    valor_estimado: float | None,
    data_abertura: datetime | None,
    data_encerramento: datetime | None,
    municipio: str | None,
) -> int:
    """Count how many critical fields are missing."""
    missing = 0
    if not orgao_cnpj:
        missing += 1
    if not objeto or not objeto.strip():
        missing += 1
    if not valor_estimado:
        missing += 1
    if not data_abertura:
        missing += 1
    if not data_encerramento:
        missing += 1
    if not municipio:
        missing += 1
    return missing


def _build_result(
    score: int,
    fatores: dict[str, list[str]],
    regras: list[str],
    block_reasons: list[str],
) -> dict[str, Any]:
    """Build final result dict for blocked opportunities."""
    return {
        "ranking": "NO_GO",
        "ranking_score": score,
        "ranking_fatores": fatores,
        "ranking_regras": regras,
        "ranking_confianca": "HIGH" if block_reasons else "MEDIUM",
    }
