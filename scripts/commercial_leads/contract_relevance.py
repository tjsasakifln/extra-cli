"""Hierarchical contract object relevance for CONFENGE commercial queue.

Separates strong engineering terms (Layer A) from weak generic tokens (Layer B).
Weak tokens alone never qualify a contract.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

RULE_VERSION = "contract-relevance-v3"

# Unambiguous structural-foundation phraseology. Replaces the bare token
# "fundacao", which was also matching legal-person names ("Fundação Municipal de
# Cultura", "Fundação de Apoio...") and produced the SEBRAE-ES false positive.
FOUNDATION_ENGINEERING_PHRASES: tuple[str, ...] = (
    "fundacao profunda",
    "fundacoes profundas",
    "fundacao rasa",
    "fundacoes rasas",
    "execucao de fundacao",
    "execucao de fundacoes",
    "servicos de fundacao",
    "servico de fundacao",
    "obra de fundacao",
    "obras de fundacao",
    "bloco de fundacao",
    "blocos de fundacao",
    "fundacao e estrutura",
    "fundacoes e estruturas",
    "estaqueamento",
    "estaca helice",
    "estaca raiz",
    "sapata corrida",
    "radier",
    "fundacao em concreto",
)

# Layer A — strong engineering / construction phrases and tokens
_BASE_STRONG_PHRASES: tuple[str, ...] = (
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
    "infraestrutura urbana",
    "infraestrutura de saneamento",
    "obras de infraestrutura",
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

STRONG_PHRASES: tuple[str, ...] = _BASE_STRONG_PHRASES + FOUNDATION_ENGINEERING_PHRASES

# Bare tokens that are strong only when NOT purely IT/telecom/generic.
# Note: "infraestrutura" alone is NOT here — it requires positive engineering
# context (see POSITIVE_CONTEXT / compound STRONG_PHRASES) to avoid TI/telecom FPs.
STRONG_TOKENS: tuple[str, ...] = (
    "pavimentacao",
    "terraplenagem",
    "saneamento",
    "drenagem",
    "geotecnia",
    "topografia",
    "topografico",
    "edificacao",
    "empreitada",
    "engenheir",
    "construtora",
)

# Broad SQL prefilter seeds (recall layer). DECOUPLED on purpose from
# STRONG_PHRASES/STRONG_TOKENS ordering: `pipeline._segment_sql_prefilter` used to
# slice those tuples positionally (`[:12]` / `[:10]`), so removing the bare
# "fundacao" token would have silently dropped `ILIKE '%fundacao%'` from the scan
# over the ~4M contract table and killed recall for legitimate deep-foundation
# works BEFORE the Python precision layer ever saw them.
# Bare "fundacao" MUST stay here: precision is enforced downstream in Python.
SQL_PREFILTER_SEEDS: tuple[str, ...] = (
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
    "geotecnia",
    "topografia",
    "topografico",
    "empreitada",
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
    " de ti",
    "informatica",
    "telecomunicacoes",
    "telecomunicacao",
    "rede de dados",
    "infraestrutura de ti",
    "infraestrutura de rede",
    "infraestrutura de telecomunicacoes",
    "cloud",
    "datacenter",
    "data center",
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
    "locacao de maquinas",
    "locacao de equipamentos",
    "transporte escolar",
    "combustivel",
    "posto de combustivel",
    "engenharia clinica",
    "hospitalar",
    "respirador",
    "materiais de construcao",
    "materiais para construcao",
    "fornecimento de materiais",
    "aquisicao de materiais",
    "aquisicao de cimento",
    "fornecimento de cimento",
    "agregados",
)

# Supply / rental of materials-equipment is not engineering service execution
SUPPLY_ONLY_PATTERNS: tuple[str, ...] = (
    "fornecimento de materiais",
    "aquisicao de materiais",
    "materiais de construcao",
    "materiais para construcao",
    "aquisicao de cimento",
    "fornecimento de cimento",
    "fornecimento de agregados",
    "locacao de maquinas",
    "locacao de equipamentos",
    "locacao de guindaste",
)

# Clinical / biomedical engineering is out of CONFENGE civil/infra scope
CLINICAL_PATTERNS: tuple[str, ...] = (
    "engenharia clinica",
    "equipamentos de engenharia clinica",
    "respirador",
    "hospitalar",
)


# --- Evidence neutralization -------------------------------------------------
# Two families of false evidence produced the SEBRAE-ES incident:
#   (a) a legal-person name "Fundação <qualificador>" read as structural foundation;
#   (b) physical presence at a construction-themed EVENT (booth, fair, sponsorship,
#       congress) read as execution of construction work.
# Both are neutralized by stripping the offending span before classification, so
# the remaining text is judged on its own merits.

ENTITY_FUNDACAO_RE = re.compile(
    r"\bfundac(?:ao|oes)\s+(?:municipal|estadual|federal|nacional|educacional|cultural|"
    r"universitaria|hospitalar|de\s+(?:apoio|cultura|saude|ensino|pesquisa|"
    r"desenvolvimento|amparo|assistencia|previdencia|educacao)|"
    r"[a-z]+\s+de\s+[a-z]+)\b"
)

# NARROW on purpose: physical event presence only. Training/education terms are
# deliberately NOT here — "centro de capacitacao" can be a real building (AC 10).
# `\b` boundaries keep "estande" from matching as a bare substring.
EVENT_PRESENCE_RE = re.compile(
    r"\b(feira|estande|expositor|exposicao|congresso|seminario|simposio|"
    r"salao|patrocinio|inscricao|credenciamento\s+de\s+evento)\b"
)

# Execution language that overrides the event gate (real works that merely happen
# to mention an event/venue, e.g. "reforma do estande de tiro").
EVENT_EXECUTION_ESCAPE: tuple[str, ...] = (
    "execucao de obra",
    "empreitada",
    "pavimentacao",
    "terraplenagem",
    "reforma predial",
    "obra de construcao civil",
    "construcao de",
    "reforma d",
    "ampliacao d",
    "drenagem",
    "saneamento",
)

_EVENT_THEME_WORDS_RE = re.compile(r"\b(construcao civil|construcao|engenharia|obra|obras)\b")

NEUTRALIZED_REASON_CODE = "evidence_neutralized_entity_or_event"


def neutralize_evidence(objeto: str | None) -> str:
    """Return the normalized object with entity-name / event-theme evidence stripped.

    Returns the plain normalized text when nothing was neutralized, so callers can
    detect "no change" by comparing against ``normalize_text(objeto)``.
    """
    n = normalize_text(objeto)
    if not n:
        return n
    stripped = n
    if ENTITY_FUNDACAO_RE.search(n) and not any(
        p in n for p in FOUNDATION_ENGINEERING_PHRASES
    ):
        stripped = ENTITY_FUNDACAO_RE.sub(" ", stripped)
    if EVENT_PRESENCE_RE.search(n) and not any(e in n for e in EVENT_EXECUTION_ESCAPE):
        # Event theme: the construction words describe the EVENT, not the work.
        stripped = _EVENT_THEME_WORDS_RE.sub(" ", stripped)
    return stripped


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


def _classify_relevance_raw(objeto: str | None) -> ContractRelevanceResult:
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
    supply_only = _find_hits(norm, SUPPLY_ONLY_PATTERNS)
    clinical = _find_hits(norm, CLINICAL_PATTERNS)

    reasons: list[str] = []

    # Materials supply / equipment rental without execution language → FAIL
    if supply_only and not any(
        x in norm
        for x in (
            "execucao de obra",
            "empreitada",
            "servicos de engenharia",
            "fiscalizacao de obra",
            "pavimentacao",
        )
    ):
        return ContractRelevanceResult(
            status="FAIL",
            score=0.0,
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_context=neg + supply_only,
            reason_codes=["materials_or_rental_supply_only"],
            normalized_object=norm[:500],
        )

    # Clinical/biomedical engineering is outside civil/infra commercial scope
    if clinical:
        return ContractRelevanceResult(
            status="FAIL",
            score=0.0,
            strong_hits=strong,
            weak_hits=weak,
            positive_context=pos,
            negative_context=neg + clinical,
            reason_codes=["clinical_biomedical_out_of_scope"],
            normalized_object=norm[:500],
        )

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
                "telecomunicacoes",
                "telecomunicacao",
                "rede de dados",
                "infraestrutura de ti",
                "infraestrutura de rede",
                "infraestrutura de telecomunicacoes",
                "tecnologia da informacao",
                "informatica",
                "engenharia clinica",
                "hospitalar",
                "materiais de construcao",
                "fornecimento de materiais",
                "aquisicao de materiais",
                "locacao de maquinas",
                "locacao de equipamentos",
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


def classify_contract_relevance(objeto: str | None) -> ContractRelevanceResult:
    """Public entry point: neutralize false evidence, then classify.

    When entity-name or event-theme evidence was stripped, the classification runs
    over the stripped text and the result carries the
    ``evidence_neutralized_entity_or_event`` reason code for auditability.
    """
    stripped = neutralize_evidence(objeto)
    if stripped != normalize_text(objeto):
        res = _classify_relevance_raw(stripped)
        res.reason_codes = [*res.reason_codes, NEUTRALIZED_REASON_CODE]
        return res
    return _classify_relevance_raw(objeto)


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
