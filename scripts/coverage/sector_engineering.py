#!/usr/bin/env python3
"""Explainable engineering/construction sector filter for Extra Construtora.

Scores opportunity objects for relevance to civil engineering, construction,
urban infrastructure, and related services. Avoids false positives on generic
'serviço' without construction context.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

POSITIVE_TERMS: list[tuple[str, str, float]] = [
    ("obras", r"\bobras?\b", 0.35),
    ("engenharia", r"\bengenharia\b", 0.3),
    ("construcao", r"\bconstru[cç][aã]o\b|\bconstruir\b|\bconstru[ií]d", 0.3),
    ("pavimentacao", r"\bpaviment", 0.35),
    ("drenagem", r"\bdrenagem\b|\bgaleria\s+pluvial\b", 0.3),
    ("saneamento", r"\bsaneamento\b|\besgoto\b|\badutor", 0.3),
    ("edificacao", r"\bedifica[cç]|pr[eé]dio|edif[ií]cio", 0.25),
    ("reforma", r"\breforma\b|\breadequa[cç]|recupera[cç][aã]o\s+estrutural", 0.22),
    ("infraestrutura", r"\binfraestrutura\b|\binfra[- ]estrutura", 0.25),
    ("terraplenagem", r"\bterraplenagem\b|\bterraplanagem\b|\bmotoscraper", 0.35),
    ("contencao", r"\bconten[cç][aã]o\b|\bmuro\s+de\s+arrimo\b|\bgabi[aã]o", 0.3),
    ("instalacoes", r"\binstala[cç][oõ]es\s+(el[eé]tricas|hidr[aá]ulicas|prediais)", 0.22),
    ("fiscalizacao", r"\bfiscaliza[cç][aã]o\s+(de\s+)?(obra|engenharia|contrato\s+de\s+obra)", 0.25),
    ("projeto_engenharia", r"\bprojeto\s+(executivo|b[aá]sico|de\s+engenharia|arquitet[oô]nico)", 0.22),
    ("manutencao_predial", r"\bmanuten[cç][aã]o\s+(predial|de\s+edif|de\s+pr[eé]dio|de\s+im[oó]vel)", 0.22),
    ("ponte_viaduto", r"\bponte\b|\bviaduto\b|\bpassarela\b|\bpontilh[aã]o", 0.28),
    ("asfalto", r"\basfalt|\bcbu\b|\bcapeamento\b|\brevestimento\s+asf[aá]ltico", 0.3),
    ("demolicao", r"\bdemoli[cç]", 0.2),
    ("urbanismo", r"\burbaniza[cç]|\bcal[cç]ad|\bpasseio\s+p[uú]blico", 0.2),
    ("hidraulica", r"\bhidr[aá]ulic|\brede\s+de\s+[aá]gua|\brede\s+coletora", 0.22),
    ("alvenaria", r"\balvenaria\b|\bconcreto\b|\bestrutura\s+de\s+concreto", 0.2),
    ("cobertura", r"\bcobertura\s+(met[aá]lica|de\s+telha)|\btelhado\b", 0.18),
    ("sondagem", r"\bsondagem\b|\bgeot[eé]cnic", 0.2),
    ("meio_fio", r"\bmeio[- ]fio\b|\bsarjeta\b", 0.18),
]

NEGATIVE_TERMS: list[tuple[str, str, float]] = [
    ("ti_software", r"\b(software|licen[cç]a\s+de\s+uso|sistema\s+informat|nuvem|cloud|datacenter|"
     r"impressora|notebook|computador|telefonia\s+ip|link\s+de\s+dados|antiv[ií]rus)\b", 0.45),
    ("medicamentos", r"\b(medicamento|f[aá]rmaco|vacina|hospitalar\s+descart|pr[oó]tese)\b", 0.4),
    ("alimentacao", r"\b(g[eê]neros\s+aliment|merenda|refei[cç][aã]o|lanche\s+escolar)\b", 0.4),
    ("vigilancia", r"\b(vigil[aâ]ncia\s+(desarmada|armada)|seguran[cç]a\s+patrimonial|porteiro)\b", 0.35),
    ("combustivel", r"\b(combust[ií]vel|gasolina|diesel|etanol\s+combust)\b", 0.35),
    ("limpeza_sem_obra", r"\b(limpeza\s+predial|conserva[cç][aã]o\s+e\s+limpeza|copeiragem)\b", 0.25),
    ("uniformes", r"\b(uniforme|vestu[aá]rio|cal[cç]ado\s+de\s+seguran[cç]a)\b", 0.3),
    ("publicidade", r"\b(publicidade|propaganda|m[ií]dia\s+outdoor)\b", 0.35),
    ("capacitacao", r"\b(treinamento|capacita[cç][aã]o|curso\s+de\s+forma[cç])\b", 0.25),
    ("seguros", r"\b(seguro\s+de\s+vida|seguro\s+sa[uú]de|apolice)\b", 0.3),
]

# Generic "serviço" alone is NOT enough
_GENERIC_SERVICO = re.compile(r"\bservi[cç]os?\b", re.I)

SECTORS = (
    "obras_civis",
    "infraestrutura_urbana",
    "saneamento",
    "pavimentacao",
    "edificacoes",
    "engenharia_consultiva",
    "manutencao_predial",
    "terraplenagem_contencao",
    "misto_engenharia",
    "nao_engenharia",
)


@dataclass
class SectorMatch:
    sector_match: bool
    sector: str
    score: float
    terms: list[str]
    rules: list[str]
    justification: str
    negative_hits: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_sector(
    objeto: str | None = None,
    *,
    titulo: str | None = None,
    itens: str | None = None,
    modalidade: str | None = None,
    threshold: float = 0.35,
) -> SectorMatch:
    """Return explainable engineering/construction sector match."""
    blob = " ".join(x for x in [objeto or "", titulo or "", itens or "", modalidade or ""] if x)
    if not blob.strip():
        return SectorMatch(
            sector_match=False,
            sector="nao_engenharia",
            score=0.0,
            terms=[],
            rules=["empty_text"],
            justification="No object/title text to evaluate",
            negative_hits=[],
        )

    score = 0.0
    terms: list[str] = []
    rules: list[str] = []
    neg: list[str] = []

    for name, pattern, weight in POSITIVE_TERMS:
        if re.search(pattern, blob, re.I):
            score += weight
            terms.append(name)
            rules.append(f"+{name}:{weight}")

    for name, pattern, weight in NEGATIVE_TERMS:
        if re.search(pattern, blob, re.I):
            score -= weight
            neg.append(name)
            rules.append(f"-{name}:{weight}")

    # Generic serviço without engineering terms → mild penalty if no positives
    if _GENERIC_SERVICO.search(blob) and not terms:
        score -= 0.15
        rules.append("-generic_servico_without_eng_context:0.15")

    score = max(0.0, min(1.0, score))
    matched = score >= threshold and len(terms) > 0

    sector = "nao_engenharia"
    if matched:
        if any(t in terms for t in ("pavimentacao", "asfalto", "meio_fio")):
            sector = "pavimentacao"
        elif any(t in terms for t in ("saneamento", "drenagem", "hidraulica")):
            sector = "saneamento"
        elif any(t in terms for t in ("terraplenagem", "contencao")):
            sector = "terraplenagem_contencao"
        elif any(t in terms for t in ("fiscalizacao", "projeto_engenharia", "sondagem")):
            sector = "engenharia_consultiva"
        elif any(t in terms for t in ("manutencao_predial", "reforma", "instalacoes")):
            sector = "manutencao_predial"
        elif any(t in terms for t in ("edificacao", "alvenaria", "cobertura", "demolicao")):
            sector = "edificacoes"
        elif any(t in terms for t in ("infraestrutura", "urbanismo", "ponte_viaduto")):
            sector = "infraestrutura_urbana"
        elif "obras" in terms or "construcao" in terms or "engenharia" in terms:
            sector = "obras_civis"
        else:
            sector = "misto_engenharia"

    justification = (
        f"score={score:.2f} threshold={threshold} positives={terms} negatives={neg}"
        if terms or neg
        else "No engineering positive terms matched"
    )

    return SectorMatch(
        sector_match=matched,
        sector=sector,
        score=round(score, 4),
        terms=terms,
        rules=rules,
        justification=justification,
        negative_hits=neg,
    )
