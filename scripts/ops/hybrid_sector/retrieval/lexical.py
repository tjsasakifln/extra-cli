"""Canal A — lexical retrieval with full vocabulary accounting (no silent 80-term cap)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from scripts.ops.sector_classifier import (
    _FALLBACK_POSITIVE,
    normalize_text,
)
from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit


# Morphological / common variants beyond base fallback patterns
_EXTRA_VARIANTS: list[tuple[str, str, float]] = [
    ("pavimentacao_typo", r"\bpavimenta[cç]ao\b|\bpavimentacao\b|\bpavimenta[cç][aã]o\b", 0.4),
    ("recape", r"\brecape\b|\brecapeamento\b|\brecapagem\b", 0.38),
    ("drenagem_abbrev", r"\bdren\.?\s+pluv|\bgal\.?\s+pluv", 0.35),
    ("ete_eta", r"\bete\b|\beta\b|\beee\b|\bestacao\s+elevatoria\b", 0.35),
    ("obra_civil", r"\bobra\s+civil\b|\bobras\s+civis\b", 0.4),
    ("execucao", r"\bexecu[cç][aã]o\s+de\s+obra", 0.42),
    ("implantacao", r"\bimplanta[cç][aã]o\s+(de\s+)?(rede|sistema|obra|infra)", 0.4),
    ("instalacao_exec", r"\binstala[cç][aã]o\s+(de\s+)?(rede|drenagem|adutora|tubul)", 0.38),
    ("requalificacao", r"\brequalifica[cç]|\brevitaliza[cç]|\breadequa[cç]", 0.36),
    ("contencao_encosta", r"\bconten[cç][aã]o\s+de\s+encosta|\bestabiliza[cç][aã]o\s+geotec", 0.4),
    ("empreitada", r"\bempreitada\b|\bcontratacao\s+integrada\b", 0.38),
    ("modular", r"\bconstru[cç][aã]o\s+modular\b|\bmodulo\s+escolar\b", 0.35),
    ("acessibilidade", r"\badequa[cç][aã]o\s+de\s+acessibilidade|\brampa\s+de\s+acesso\b", 0.32),
]


@dataclass
class LexicalRunReport:
    total_terms: int = 0
    terms_executed: int = 0
    terms_omitted: int = 0
    omission_reason: str | None = None
    term_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_terms": self.total_terms,
            "terms_executed": self.terms_executed,
            "terms_omitted": self.terms_omitted,
            "omission_reason": self.omission_reason,
            "term_ids": list(self.term_ids),
        }


def _build_term_list(max_terms: int | None = None) -> tuple[list[tuple[str, re.Pattern[str], float]], LexicalRunReport]:
    terms: list[tuple[str, re.Pattern[str], float]] = []
    for tid, pat, _sub, w in _FALLBACK_POSITIVE:
        terms.append((tid, re.compile(pat, re.I), w))
    for tid, pat, w in _EXTRA_VARIANTS:
        terms.append((tid, re.compile(pat, re.I), w))

    report = LexicalRunReport(total_terms=len(terms), term_ids=[t[0] for t in terms])
    if max_terms is not None and max_terms < len(terms):
        report.terms_omitted = len(terms) - max_terms
        report.omission_reason = f"technical_cap max_terms={max_terms}"
        terms = terms[:max_terms]
    report.terms_executed = len(terms)
    report.term_ids = [t[0] for t in terms]
    return terms, report


def retrieve_lexical(
    universe: Iterable[RawOpportunity],
    *,
    max_terms: int | None = None,
) -> tuple[dict[str, RetrievalHit], LexicalRunReport]:
    """Return hits keyed by canonical_id. Searches object + title + items + categories."""
    terms, report = _build_term_list(max_terms=max_terms)
    hits: dict[str, RetrievalHit] = {}
    scored: list[tuple[str, float, str]] = []

    for rec in universe:
        blob = normalize_text(rec.text_blob())
        if not blob:
            continue
        matched: list[str] = []
        score = 0.0
        for tid, cre, w in terms:
            if cre.search(blob):
                matched.append(tid)
                score += w
        if matched:
            scored.append((rec.canonical_id, score, ",".join(matched[:8])))

    scored.sort(key=lambda x: (-x[1], x[0]))
    for rank, (cid, score, reason) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="lexical",
            score=score,
            rank=rank,
            reason=f"terms:{reason}",
        )
    return hits, report
