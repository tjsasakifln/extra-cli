#!/usr/bin/env python3
"""Classificador setorial auditável para Extra Construtora (B2G / engenharia civil).

Labels canônicos (fail-closed comercial):
  ENGINEERING_HIGH_CONFIDENCE | ENGINEERING_REVIEW | NON_ENGINEERING
  | AMBIGUOUS | EXCLUDED_CATEGORY

Nenhum objeto vira aderente só por palavra genérica (serviço, manutenção,
construção, projeto). Regras versionadas; output sempre auditável.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULE_VERSION = "extra-sector-classifier/2.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "config/client_profiles/extra.yaml"

LABELS = (
    "ENGINEERING_HIGH_CONFIDENCE",
    "ENGINEERING_REVIEW",
    "NON_ENGINEERING",
    "AMBIGUOUS",
    "EXCLUDED_CATEGORY",
)

# Labels that may appear in commercial Deliverable E
E_ALLOWED_LABELS = frozenset({"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"})

_GENERIC_ALONE = re.compile(
    r"^(?:servi[cç]os?|manuten[cç][aã]o|constru[cç][aã]o|projeto|obras?|"
    r"engenharia|infraestrutura)\s*$",
    re.I,
)
_GENERIC_WEAK = (
    "servico",
    "servicos",
    "manutencao",
    "construcao",
    "projeto",
    "obra",
    "obras",
    "engenharia",
    "infraestrutura",
)


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    t = _strip_accents(str(text)).lower()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


@dataclass
class SectorClassification:
    label: str
    positive_terms: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    category: str = ""
    subcategory: str = ""
    reason: str = ""
    confidence: float = 0.0
    textual_evidence: str = ""
    rule_version: str = RULE_VERSION
    sector_match: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def allowed_in_deliverable_e(self) -> bool:
        return self.label in E_ALLOWED_LABELS


# Fallback vocabulary if profile lacks sector_vocabulary block
_FALLBACK_POSITIVE: list[tuple[str, str, str, float]] = [
    # (term_id, regex, subcategory, weight)
    ("pavimentacao", r"\bpaviment", "pavimentacao", 0.45),
    ("asfalto", r"\basfalt|\bcbu\b|\bcapeamento\b", "pavimentacao", 0.4),
    ("drenagem", r"\bdrenagem\b|\bgaleria\s+pluvial\b|\bsarjeta\b|\bmeio[- ]fio\b", "drenagem", 0.42),
    ("terraplenagem", r"\bterraplenagem\b|\bterraplanagem\b", "terraplenagem", 0.45),
    ("saneamento", r"\bsaneamento\b|\besgoto\b|\badutor|\brede\s+coletora\b", "saneamento", 0.4),
    ("infraestrutura_urbana", r"\binfraestrutura\s+urbana\b|\burbaniza[cç]|\brevitaliza[cç][aã]o\s+urbana\b", "infraestrutura_urbana", 0.38),
    ("calcada", r"\bcal[cç]ad[ao]\b|\bpasseio\s+publico\b", "infraestrutura_urbana", 0.3),
    ("edificacao", r"\bedifica|\bpredio\s+publico\b|\bedificio\s+publico\b", "edificacoes", 0.38),
    ("construcao_edificios", r"\bconstru[cç][aã]o\s+de\s+(edif|pred|escola|creche|ubs|pronto.?socorro|ginasio|quadra)", "edificacoes", 0.45),
    ("ampliacao", r"\bamplia[cç][aã]o\s+de\s+(escola|creche|pred|edif|ubs|hospital|ginasio)", "edificacoes", 0.42),
    ("reforma_predial", r"\breforma\s+(predial|de\s+edif|de\s+pred|estrutural|de\s+escola|de\s+creche)", "reformas", 0.4),
    ("manutencao_predial", r"\bmanuten[cç][aã]o\s+(predial|de\s+edif|de\s+pred|civil\s+das\s+edifica|de\s+imovel)", "manutencao_predial", 0.38),
    ("obra_engenharia", r"\bobra[s]?\s+de\s+engenharia\b|\bexecu[cç][aã]o\s+das\s+obras\s+de\s+engenharia\b|\bservicos?\s+de\s+engenharia\s+(civil|para)\b", "obras_civis", 0.45),
    ("ponte_viaduto", r"\bponte\b|\bviaduto\b|\bpassarela\b|\bpontilh", "infraestrutura_urbana", 0.35),
    ("contencao", r"\bconten[cç][aã]o\b|\bmuro\s+de\s+arrimo\b|\bgabiao\b", "terraplenagem", 0.35),
    ("demolicao", r"\bdemoli[cç]", "reformas", 0.28),
    ("projeto_engenharia", r"\bprojetos?\s+(executivo|basico|de\s+engenharia|arquitetonicos?|complementares?)", "projetos", 0.35),
    ("projetos_complementares", r"\bprojetos?\s+complementares\b|\bprojeto\s+estrutural\b|\bprojeto\s+hidrossanitario\b|\barquitetonicos?\s+e\s+complementares\b", "projetos", 0.35),
    ("fiscalizacao_obra", r"\bfiscaliza[cç][aã]o\s+(de\s+)?(obra|engenharia)", "projetos", 0.3),
    ("instalacoes_prediais", r"\binstala[cç][oõ]es\s+(eletricas|hidraulicas|prediais)\b", "manutencao_predial", 0.28),
    ("cobertura_telhado", r"\bcobertura\s+(metalica|de\s+telha)|\btelhado\b", "reformas", 0.25),
    ("alvenaria_concreto", r"\balvenaria\b|\bestrutura\s+de\s+concreto\b", "edificacoes", 0.28),
    ("recuperacao_estrutural", r"\brecupera[cç][aã]o\s+estrutural\b", "reformas", 0.35),
    ("obras_publicas", r"\bexecu[cç][aã]o\s+de\s+obras?\b|\bobras?\s+publicas?\b", "obras_civis", 0.28),
]

_FALLBACK_NEGATIVE: list[tuple[str, str, float]] = [
    ("frota", r"\bmanuten[cç][aã]o\s+da\s+frota\b|\bfrota\s+municipal\b|\boficina\s+mecanica\b|\bveiculo[s]?\b", 0.55),
    ("computador", r"\bcomputador\b|\bnotebook\b|\ball\s+in\s+one\b|\bimpressora\b|\binformatica\b|\bhardware\b", 0.55),
    ("lencois", r"\blen[cç][oó]is?\b|\bmantas?\s+destinad|\bcama\s+hospitalar\b|\benxoval\b", 0.55),
    ("exames", r"\bexames?\s+(laborator|clinico|de\s+imagem)|\blaboratoriais\b|\bcomplementar\s+ao\s+sus\b", 0.55),
    ("saude_assistencial", r"\bmedicamento\b|\bfarmaco\b|\bvacina\b|\bprótese\b|\bhospitalar\s+descart", 0.5),
    ("combustivel", r"\bcombustivel\b|\bgasolina\b|\bdiesel\b|\betanol\s+combust", 0.5),
    ("cursos", r"\bcurso[s]?\s+(para|de)\b|\bcapacita[cç][aã]o\b|\btreinamento\b|\bprofessores?\b", 0.45),
    ("eventos_culturais", r"\boficina\s+de\s+karate\b|\bkarat[eé]\b|\bevento\s+cultural\b|\boficina\s+cultural\b|\besportiv", 0.5),
    ("bancario", r"\barrecada[cç][aã]o\s+bancaria\b|\bservi[cç]os?\s+bancarios?\b|\btarifa\s+bancaria\b", 0.5),
    ("equip_hospitalar", r"\bequipamento[s]?\s+hospitalar|\bmateriais?\s+medico.?hospitalar", 0.5),
    ("software", r"\bmanuten[cç][aã]o\s+de\s+software\b|\blicenca\s+de\s+uso\b|\bsistema\s+informat|\bsoftware\b|\bnuvem\b|\bcloud\b", 0.55),
    ("construcao_conhecimento", r"\bconstru[cç][aã]o\s+de\s+conhecimento\b|\bconstru[cç][aã]o\s+coletiva\s+de\s+saberes\b", 0.6),
    ("alimentacao", r"\bgeneros\s+aliment|\bmerenda\b|\brefeicao\b|\balimentos?\b", 0.45),
    ("roupas", r"\buniforme\b|\bvestuario\b|\broupa[s]?\b|\bcalcado\s+de\s+seguranca\b", 0.4),
    ("castracao", r"\bcastra[cç][aã]o\b|\besteriliza[cç][aã]o\s+de\s+animais\b|\bzoonoses\b", 0.55),
    ("residuos_cc", r"\bresiduos?\s+da\s+constru[cç][aã]o\s+civil\b|\bentulho\b|\bca[cç]amba\s+de\s+entulho\b", 0.4),
    ("vigilancia", r"\bvigilancia\s+(desarmada|armada)\b|\bseguranca\s+patrimonial\b", 0.4),
    ("publicidade", r"\bpublicidade\b|\bpropaganda\b|\bmidia\s+outdoor\b", 0.4),
]

_FALLBACK_EXCLUSION: list[tuple[str, str]] = [
    ("credenciamento_generico", r"\bcredenciamento\b(?!.*\b(obra|engenharia|paviment|edifica|reforma\s+predial))"),
    ("saude_assistencial_cat", r"\b(sus\b|unidade\s+basica\s+de\s+saude|atencao\s+basica\s+a\s+saude)"),
    ("admin_puro", r"\b(servicos?\s+administrativos?\s+continuados|locacao\s+de\s+mao\s+de\s+obra\s+administrativa)"),
]

# "material de construção" isolado (sem execução de obra)
_MATERIAL_ONLY = re.compile(
    r"\b(aquisicao|fornecimento|compra|registro\s+de\s+precos?)\b.+\b("
    r"materiais?\s+(de\s+)?(constru\w*|paviment\w*|obra|hidraul\w*)|"
    r"materiais?\s+para\s+(uso\s+nas\s+)?paviment\w*"
    r")",
    re.I,
)
_EXECUCAO_OBRA = re.compile(
    r"\b(execu[cç][aã]o|empreitada|construcao\s+de|obra[s]?\s+de|servicos?\s+de\s+engenharia|"
    r"reforma\s+predial|manutencao\s+predial|pavimentacao|drenagem|terrapl)\b",
    re.I,
)


def load_profile(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_PROFILE_PATH
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _compile_from_profile(profile: dict[str, Any]) -> tuple[
    list[tuple[str, re.Pattern[str], str, float]],
    list[tuple[str, re.Pattern[str], float]],
    list[tuple[str, re.Pattern[str]]],
]:
    """Build compiled rules from profile sector_vocabulary when present."""
    vocab = profile.get("sector_vocabulary") or {}
    positives: list[tuple[str, re.Pattern[str], str, float]] = []
    if isinstance(vocab.get("positive"), list) and vocab["positive"]:
        for item in vocab["positive"]:
            if isinstance(item, dict):
                tid = str(item.get("id") or item.get("term") or "pos")
                pat = str(item.get("pattern") or item.get("term") or "")
                sub = str(item.get("subcategory") or item.get("category") or "obras_civis")
                w = float(item.get("weight") or 0.35)
            else:
                tid = normalize_text(str(item)).replace(" ", "_")[:40]
                pat = re.escape(normalize_text(str(item)))
                sub = "obras_civis"
                w = 0.35
            if pat:
                positives.append((tid, re.compile(pat, re.I), sub, w))
    else:
        for tid, pat, sub, w in _FALLBACK_POSITIVE:
            positives.append((tid, re.compile(pat, re.I), sub, w))

    negatives: list[tuple[str, re.Pattern[str], float]] = []
    if isinstance(vocab.get("negative"), list) and vocab["negative"]:
        for item in vocab["negative"]:
            if isinstance(item, dict):
                tid = str(item.get("id") or item.get("term") or "neg")
                pat = str(item.get("pattern") or item.get("term") or "")
                w = float(item.get("weight") or 0.45)
            else:
                tid = normalize_text(str(item)).replace(" ", "_")[:40]
                pat = re.escape(normalize_text(str(item)))
                w = 0.45
            if pat:
                negatives.append((tid, re.compile(pat, re.I), w))
    else:
        for tid, pat, w in _FALLBACK_NEGATIVE:
            negatives.append((tid, re.compile(pat, re.I), w))

    exclusions: list[tuple[str, re.Pattern[str]]] = []
    if isinstance(vocab.get("exclusion"), list) and vocab["exclusion"]:
        for item in vocab["exclusion"]:
            if isinstance(item, dict):
                tid = str(item.get("id") or item.get("term") or "exc")
                pat = str(item.get("pattern") or item.get("term") or "")
            else:
                tid = normalize_text(str(item)).replace(" ", "_")[:40]
                pat = re.escape(normalize_text(str(item)))
            if pat:
                exclusions.append((tid, re.compile(pat, re.I)))
    else:
        for tid, pat in _FALLBACK_EXCLUSION:
            exclusions.append((tid, re.compile(pat, re.I)))

    return positives, negatives, exclusions


def _pick_category(pos_hits: list[tuple[str, str, float]]) -> tuple[str, str]:
    if not pos_hits:
        return "nao_engenharia", ""
    # highest weight subcategory
    best = max(pos_hits, key=lambda x: x[2])
    sub = best[1]
    cat_map = {
        "pavimentacao": "infraestrutura",
        "drenagem": "infraestrutura",
        "terraplenagem": "infraestrutura",
        "saneamento": "infraestrutura",
        "infraestrutura_urbana": "infraestrutura",
        "edificacoes": "edificacoes",
        "reformas": "edificacoes",
        "manutencao_predial": "edificacoes",
        "obras_civis": "obras_civis",
        "projetos": "projetos_engenharia",
    }
    return cat_map.get(sub, "obras_civis"), sub


def classify_object(
    objeto: str | None = None,
    *,
    titulo: str | None = None,
    itens: str | None = None,
    profile: dict[str, Any] | None = None,
    profile_path: Path | None = None,
) -> SectorClassification:
    """Classifica um objeto de compra/contrato/edital de forma auditável."""
    prof = profile if profile is not None else load_profile(profile_path)
    raw_parts = [p for p in (objeto, titulo, itens) if p]
    raw = " | ".join(str(p) for p in raw_parts)
    blob = normalize_text(raw)
    evidence = (raw[:280] + "…") if len(raw) > 280 else raw

    if not blob:
        return SectorClassification(
            label="AMBIGUOUS",
            reason="texto vazio — sem objeto para classificar",
            confidence=0.0,
            textual_evidence="",
            category="desconhecido",
            subcategory="",
            sector_match=False,
        )

    # Generic-only short text
    if _GENERIC_ALONE.match(blob) or (
        len(blob.split()) <= 2 and all(w in _GENERIC_WEAK for w in blob.split())
    ):
        return SectorClassification(
            label="NON_ENGINEERING",
            reason="apenas termo genérico (serviço/manutenção/construção/projeto) sem contexto de obra",
            confidence=0.95,
            textual_evidence=evidence,
            category="generico",
            subcategory="termo_generico_isolado",
            positive_terms=[],
            sector_match=False,
        )

    positives, negatives, exclusions = _compile_from_profile(prof)

    # Explicit false friends first
    if re.search(r"\b(aquisicao|compra)\b.+\b(livro|exemplares?\s+do\s+livro|publicacao)\b", blob, re.I):
        return SectorClassification(
            label="NON_ENGINEERING",
            negative_terms=["publicacao_livro"],
            reason="aquisição de livro/publicação — não é execução de obra",
            confidence=0.95,
            textual_evidence=evidence,
            category="nao_engenharia",
            subcategory="publicacao",
            sector_match=False,
        )
    if re.search(r"\bconstru[cç][aã]o\s+de\s+conhecimento\b", blob, re.I):
        return SectorClassification(
            label="NON_ENGINEERING",
            negative_terms=["construcao_conhecimento"],
            reason="metáfora educacional 'construção de conhecimento' — não é obra",
            confidence=0.98,
            textual_evidence=evidence,
            category="nao_engenharia",
            subcategory="metafora_educacional",
            sector_match=False,
        )
    if re.search(r"\bmanuten[cç][aã]o\s+de\s+software\b", blob, re.I):
        return SectorClassification(
            label="NON_ENGINEERING",
            negative_terms=["software"],
            reason="manutenção de software — fora do mercado de obras da Extra",
            confidence=0.98,
            textual_evidence=evidence,
            category="ti",
            subcategory="software",
            sector_match=False,
        )

    pos_hits: list[tuple[str, str, float]] = []
    for tid, cre, sub, w in positives:
        if cre.search(blob):
            pos_hits.append((tid, sub, w))

    neg_hits: list[tuple[str, float]] = []
    for tid, cre, w in negatives:
        if cre.search(blob):
            neg_hits.append((tid, w))

    exc_hits: list[str] = []
    for tid, cre in exclusions:
        if cre.search(blob):
            exc_hits.append(tid)

    pos_score = sum(w for _, _, w in pos_hits)
    neg_score = sum(w for _, w in neg_hits)
    pos_ids = [t for t, _, _ in pos_hits]
    neg_ids = [t for t, _ in neg_hits]
    category, subcategory = _pick_category(pos_hits)

    # Residuos da construção civil: negative unless explicit obra execution for Extra
    if "residuos_cc" in neg_ids and not any(
        s in {h[1] for h in pos_hits}
        for s in ("edificacoes", "reformas", "pavimentacao", "obras_civis")
    ):
        return SectorClassification(
            label="NON_ENGINEERING",
            positive_terms=pos_ids,
            negative_terms=neg_ids,
            reason="resíduos da construção civil sem execução de obra aderente",
            confidence=0.9,
            textual_evidence=evidence,
            category="residuos",
            subcategory="residuos_cc",
            sector_match=False,
        )

    # Material de construção isolado
    if _MATERIAL_ONLY.search(blob) and not _EXECUCAO_OBRA.search(blob):
        return SectorClassification(
            label="ENGINEERING_REVIEW",
            positive_terms=pos_ids,
            negative_terms=neg_ids + ["material_isolado"],
            reason="material de construção/pavimentação sem execução de obra — review comercial",
            confidence=0.75,
            textual_evidence=evidence,
            category=category or "materiais",
            subcategory="material_sem_execucao",
            sector_match=False,
        )

    # Strong exclusion categories with no engineering execution context
    if exc_hits and pos_score < 0.35:
        return SectorClassification(
            label="EXCLUDED_CATEGORY",
            positive_terms=pos_ids,
            negative_terms=neg_ids,
            excluded_terms=exc_hits,
            reason=f"categoria excluída pelo perfil: {', '.join(exc_hits)}",
            confidence=0.88,
            textual_evidence=evidence,
            category="excluido",
            subcategory=exc_hits[0],
            sector_match=False,
        )

    # Strong negatives dominate
    if neg_score >= 0.45 and pos_score < 0.35:
        return SectorClassification(
            label="NON_ENGINEERING",
            positive_terms=pos_ids,
            negative_terms=neg_ids,
            excluded_terms=exc_hits,
            reason=f"termos negativos setoriais dominam (neg={neg_score:.2f}, pos={pos_score:.2f})",
            confidence=min(0.99, 0.7 + neg_score * 0.3),
            textual_evidence=evidence,
            category="nao_engenharia",
            subcategory=neg_ids[0] if neg_ids else "",
            sector_match=False,
        )

    # Strong engineering execution categories
    STRONG_SUBS = {
        "pavimentacao",
        "drenagem",
        "terraplenagem",
        "saneamento",
        "edificacoes",
        "reformas",
        "obras_civis",
        "infraestrutura_urbana",
    }

    if pos_score >= 0.38 and neg_score < 0.35:
        # projetos alone → REVIEW (comercialmente relevante só com contexto)
        if subcategory == "projetos" and not any(h[1] in STRONG_SUBS for h in pos_hits):
            return SectorClassification(
                label="ENGINEERING_REVIEW",
                positive_terms=pos_ids,
                negative_terms=neg_ids,
                reason="projeto de engenharia/arquitetura — review de capacidade/CAT",
                confidence=min(0.9, 0.55 + pos_score * 0.3),
                textual_evidence=evidence,
                category=category,
                subcategory=subcategory,
                sector_match=True,
            )
        if subcategory == "manutencao_predial" and pos_score < 0.55:
            return SectorClassification(
                label="ENGINEERING_REVIEW",
                positive_terms=pos_ids,
                negative_terms=neg_ids,
                reason="manutenção predial — engineering/review (escopo e CAT)",
                confidence=min(0.88, 0.5 + pos_score * 0.35),
                textual_evidence=evidence,
                category=category,
                subcategory=subcategory,
                sector_match=True,
            )
        if subcategory in STRONG_SUBS or pos_score >= 0.5:
            return SectorClassification(
                label="ENGINEERING_HIGH_CONFIDENCE",
                positive_terms=pos_ids,
                negative_terms=neg_ids,
                reason=f"objeto de engenharia aderente (pos={pos_score:.2f})",
                confidence=min(0.99, 0.65 + pos_score * 0.25),
                textual_evidence=evidence,
                category=category,
                subcategory=subcategory,
                sector_match=True,
            )

    if pos_score >= 0.28 and neg_score < pos_score:
        return SectorClassification(
            label="ENGINEERING_REVIEW",
            positive_terms=pos_ids,
            negative_terms=neg_ids,
            reason=f"sinais de engenharia parciais (pos={pos_score:.2f}, neg={neg_score:.2f})",
            confidence=min(0.85, 0.4 + pos_score * 0.4),
            textual_evidence=evidence,
            category=category,
            subcategory=subcategory,
            sector_match=True,
        )

    if pos_hits and neg_hits and abs(pos_score - neg_score) < 0.2:
        return SectorClassification(
            label="AMBIGUOUS",
            positive_terms=pos_ids,
            negative_terms=neg_ids,
            reason="sinais mistos positivos e negativos — ambíguo",
            confidence=0.45,
            textual_evidence=evidence,
            category=category or "ambiguo",
            subcategory=subcategory,
            sector_match=False,
        )

    if not pos_hits and not neg_hits:
        # pure generic words embedded
        if any(g in blob.split() for g in _GENERIC_WEAK) and len(blob.split()) < 8:
            return SectorClassification(
                label="NON_ENGINEERING",
                reason="vocabulário genérico sem termos de obra aderente",
                confidence=0.7,
                textual_evidence=evidence,
                category="generico",
                subcategory="",
                sector_match=False,
            )
        return SectorClassification(
            label="AMBIGUOUS",
            reason="sem termos positivos ou negativos do vocabulário Extra",
            confidence=0.35,
            textual_evidence=evidence,
            category="desconhecido",
            subcategory="",
            sector_match=False,
        )

    return SectorClassification(
        label="NON_ENGINEERING",
        positive_terms=pos_ids,
        negative_terms=neg_ids,
        excluded_terms=exc_hits,
        reason=f"não aderente ao perfil Extra (pos={pos_score:.2f}, neg={neg_score:.2f})",
        confidence=min(0.9, 0.55 + max(0.0, neg_score - pos_score) * 0.3),
        textual_evidence=evidence,
        category="nao_engenharia",
        subcategory=neg_ids[0] if neg_ids else "",
        sector_match=False,
    )


def is_engineering_for_e(clf: SectorClassification) -> bool:
    return clf.allowed_in_deliverable_e


def filter_engineering_rows(
    rows: list[dict[str, Any]],
    *,
    text_keys: tuple[str, ...] = ("objeto", "titulo", "objeto_contrato"),
    profile: dict[str, Any] | None = None,
    allow_labels: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter rows keeping only allowed engineering labels; attach sector_classification."""
    allow = allow_labels or E_ALLOWED_LABELS
    prof = profile if profile is not None else load_profile()
    out: list[dict[str, Any]] = []
    for row in rows:
        text = ""
        for k in text_keys:
            if row.get(k):
                text = str(row[k])
                break
        clf = classify_object(text, profile=prof)
        enriched = dict(row)
        enriched["sector_classification"] = clf.to_dict()
        if clf.label in allow:
            out.append(enriched)
    return out


def sql_engineering_ilike_terms(profile: dict[str, Any] | None = None) -> list[str]:
    """Terms for SQL ILIKE pre-filter (recall-oriented; classifier re-filters)."""
    prof = profile if profile is not None else load_profile()
    vocab = prof.get("sector_vocabulary") or {}
    terms: list[str] = []
    for item in vocab.get("positive") or []:
        if isinstance(item, dict):
            t = item.get("sql_term") or item.get("term")
            if t:
                terms.append(str(t))
        elif item:
            terms.append(str(item))
    desired = prof.get("desired_object_types") or []
    for d in desired:
        if isinstance(d, dict):
            for t in d.get("terms") or []:
                terms.append(str(t))
    # Always include high-recall core
    core = [
        "paviment",
        "drenagem",
        "terraplenagem",
        "terraplanagem",
        "saneamento",
        "reforma predial",
        "manutenção predial",
        "manutencao predial",
        "construção de edif",
        "construcao de edif",
        "obra de engenharia",
        "engenharia civil",
        "edificação",
        "edificacao",
        "ampliação de escola",
        "ampliacao de escola",
        "infraestrutura urbana",
        "revitalização urbana",
        "revitalizacao urbana",
        "muro de arrimo",
        "projeto executivo",
        "projeto básico",
        "projeto basico",
    ]
    terms.extend(core)
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        k = t.lower()
        if k not in seen and len(t) >= 4:
            seen.add(k)
            out.append(t)
    return out[:80]
