"""Hierarchical contract object relevance for CONFENGE commercial queue.

Separates strong engineering terms (Layer A) from weak generic tokens (Layer B).
Weak tokens alone never qualify a contract.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

RULE_VERSION = "contract-relevance-v1"

# Layer A — strong engineering / construction phrases and tokens
STRONG_PHRASES: tuple[str, ...] = (
    "obra de engenharia",
    "execucao de obra",
    "execucao de obras",
    "construcao civil",
    "pavimentacao",
    "pavimentacao asfaltica",
    "drenagem",
    "drenagem urbana",
    "saneamento",
    "terraplenagem",
    "fundacao",
    "edificacao",
    "reforma predial",
    "projeto de engenharia",
    "projeto estrutural",
    "fiscalizacao de obra",
    "supervisao de obra",
    "levantamento topografico",
    "geotecnia",
    "orcamento de obra",
    "servicos de engenharia",
    "servico de engenharia",
    "obras e servicos de engenharia",
    "empreitada",
    "infraestrutura viaria",
    "construcao de escola",
    "construcao de ponte",
    "engenharia e arquitetura",
    "estruturas metalicas",
    "concreto armado",
    "alvenaria estrutural",
    "recuperacao estrutural",
    "ponte",
    "viaduto",
    "barragem",
    "adutora",
    "estacao de tratamento",
    "rede de agua",
    "rede de esgoto",
    "asfalto",
    "asfaltica",
    "rodovia",
    "estrada vicinal",
)

STRONG_TOKENS: tuple[str, ...] = (
    "pavimentacao",
    "terraplenagem",
    "saneamento",
    "drenagem",
    "geotecnia",
    "topografia",
    "topografico",
    "edificacao",
    "fundacao",
    "empreitada",
    "engenheir",
    "construtora",
    "infraestrutura",
)

# Layer B — weak tokens (need positive engineering context)
WEAK_TOKENS: tuple[str, ...] = (
    "projeto",
    "servico",
    "servicos",
    "manutencao",
    "consultoria",
    "fornecimento",
    "apoio tecnico",
    "reforma",
    "obra",
    "obras",
    "tecnico",
    "tecnica",
)

# Positive context that can elevate a weak token
POSITIVE_CONTEXT: tuple[str, ...] = (
    "engenharia",
    "engenheir",
    "construcao",
    "civil",
    "estrutural",
    "predial",
    "ponte",
    "viaduto",
    "edificio",
    "edificacao",
    "paviment",
    "saneamento",
    "drenagem",
    "terraplenagem",
    "obra publica",
    "obras publicas",
    "fiscalizacao",
    "supervisao",
    "arquitetura",
    "fundacao",
    "estrutura",
    "hidraulica",
    "eletrica predial",
    "instalacoes prediais",
    "orcamento de obra",
    "bdi",
    "composicao de preco",
)

# Negative context — exclude even with weak engineering-ish words
NEGATIVE_CONTEXT: tuple[str, ...] = (
    "autopeca",
    "auto peca",
    "autopecas",
    "pecas automotivas",
    "pneu",
    "pneus",
    "veiculo",
    "veiculos",
    "automovel",
    "caminhao",
    "caminhoes",
    "impressora",
    "impressoras",
    "limpeza",
    "conservacao e limpeza",
    "vigilancia",
    "seguranca patrimonial",
    "terceirizacao",
    "mao de obra exclusiva",
    "dedicacao exclusiva de mao de obra",
    "software",
    "sistema de informacao",
    "tecnologia da informacao",
    "ti ",
    "informatica",
    "contabil",
    "contabilidade",
    "cultural",
    "evento cultural",
    "projeto cultural",
    "alimentacao",
    "refeicao",
    "refeicoes",
    "generos alimenticios",
    "medicamento",
    "hospitalar",
    "locacao de veiculo",
    "locacao de veiculos",
    "transporte escolar",
    "combustivel",
    "posto de combustivel",
)


@dataclass
class ContractRelevanceResult:
    status: str  # PASS | FAIL | REVIEW
    score: float
    strong_hits: list[str] = field(default_factory=list)
    weak_hits: list[str] = field(default_factory=list)
    positive_context: list[str] = field(default_factory=list)
    negative_context: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION
    normalized_object: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_hits(norm: str, patterns: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        if p in norm:
            hits.append(p)
    return hits


def classify_contract_relevance(objeto: str | None) -> ContractRelevanceResult:
    """Classify a single contract object string.

    Rules:
    - Negative context with no strong engineering evidence → FAIL
    - Any strong phrase/token without dominating negative automotive/food/etc. → PASS
    - Weak token(s) + positive engineering context, no strong negative → PASS
    - Weak token alone → FAIL (never qualifies alone)
    - Empty object → FAIL
    """
    norm = normalize_text(objeto)
    if not norm:
        return ContractRelevanceResult(
            status="FAIL",
            score=0.0,
            reason_codes=["empty_object"],
            normalized_object="",
        )

    strong = _find_hits(norm, STRONG_PHRASES) + _find_hits(norm, STRONG_TOKENS)
    # de-dupe preserve order
    seen: set[str] = set()
    strong_u: list[str] = []
    for h in strong:
        if h not in seen:
            seen.add(h)
            strong_u.append(h)
    strong = strong_u

    weak = _find_hits(norm, WEAK_TOKENS)
    pos = _find_hits(norm, POSITIVE_CONTEXT)
    neg = _find_hits(norm, NEGATIVE_CONTEXT)

    reasons: list[str] = []

    # Strong negative without strong engineering → out
    strong_neg_only = bool(neg) and not strong and not (
        any(w in ("obra", "obras", "reforma") for w in weak) and pos
    )
    if neg and not strong:
        # Allow weak+pos override only if negatives are not "hard" out-of-scope
        hard_neg = any(
            n in neg
            for n in (
                "autopeca",
                "auto peca",
                "autopecas",
                "pneu",
                "pneus",
                "limpeza",
                "vigilancia",
                "software",
                "contabil",
                "contabilidade",
                "cultural",
                "projeto cultural",
                "alimentacao",
                "refeicao",
                "refeicoes",
                "terceirizacao",
                "mao de obra exclusiva",
                "dedicacao exclusiva de mao de obra",
                "impressora",
                "impressoras",
            )
        )
        if hard_neg:
            return ContractRelevanceResult(
                status="FAIL",
                score=0.0,
                strong_hits=strong,
                weak_hits=weak,
                positive_context=pos,
                negative_context=neg,
                reason_codes=["negative_context_hard"],
                normalized_object=norm[:500],
            )
        if strong_neg_only and not pos:
            return ContractRelevanceResult(
                status="FAIL",
                score=0.05,
                strong_hits=strong,
                weak_hits=weak,
                positive_context=pos,
                negative_context=neg,
                reason_codes=["negative_context_without_engineering"],
                normalized_object=norm[:500],
            )

    if strong:
        # If strong engineering + hard out-of-scope conflict → REVIEW
        hard_neg = any(
            n in neg
            for n in (
                "autopeca",
                "limpeza",
                "software",
                "alimentacao",
                "terceirizacao",
            )
        )
        if hard_neg and len(strong) < 2:
            return ContractRelevanceResult(
                status="REVIEW",
                score=0.4,
                strong_hits=strong,
                weak_hits=weak,
                positive_context=pos,
                negative_context=neg,
                reason_codes=["conflicting_strong_and_negative"],
                normalized_object=norm[:500],
            )
        reasons.append("strong_layer_a")
        return ContractRelevanceResult(
            status="PASS",
            score=min(1.0, 0.7 + 0.05 * len(strong)),
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_context=neg,
            reason_codes=reasons,
            normalized_object=norm[:500],
        )

    if weak and pos:
        reasons.append("weak_with_positive_context")
        return ContractRelevanceResult(
            status="PASS",
            score=0.55 + 0.05 * min(3, len(pos)),
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_context=neg,
            reason_codes=reasons,
            normalized_object=norm[:500],
        )

    if weak and not pos:
        return ContractRelevanceResult(
            status="FAIL",
            score=0.1,
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_context=neg,
            reason_codes=["weak_token_alone"],
            normalized_object=norm[:500],
        )

    return ContractRelevanceResult(
        status="FAIL",
        score=0.0,
        strong_hits=strong,
        weak_hits=weak,
        positive_context=pos,
        negative_context=neg,
        reason_codes=["no_relevance_evidence"],
        normalized_object=norm[:500],
    )


def contract_passes_relevance(objeto: str | None) -> bool:
    return classify_contract_relevance(objeto).status == "PASS"


def filter_relevant_contracts(
    rows: list[dict[str, Any]],
    *,
    object_field: str = "objeto_contrato",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into relevant vs excluded with evidence."""
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        res = classify_contract_relevance(row.get(object_field))
        annotated = dict(row)
        annotated["contract_relevance"] = res.as_dict()
        if res.status == "PASS":
            kept.append(annotated)
        else:
            excluded.append(annotated)
    return kept, excluded
