"""Canal C — metadata / official category / modality / technical docs signals.

Categories are retrieval signals, not final classification decisions.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from scripts.ops.sector_classifier import normalize_text
from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit

DEFAULT_CATEGORY_TERMS = [
    "obras",
    "engenharia",
    "construcao",
    "construcao",
    "pavimentacao",
    "paviment",
    "drenagem",
    "saneamento",
    "infraestrutura",
    "urbanismo",
    "terraplenagem",
    "edificacao",
    "edificacoes",
    "reforma",
    "manutencao predial",
    "obras publicas",
    "engenharia civil",
]

DEFAULT_MODALIDADE_HINTS = [
    "concorrencia",
    "tomada de precos",
    "regime diferenciado",
    "contratacao integrada",
    "rdc",
    "dialogo competitivo",
]


def retrieve_metadata(
    universe: Iterable[RawOpportunity],
    *,
    category_terms: list[str] | None = None,
) -> dict[str, RetrievalHit]:
    terms = category_terms or DEFAULT_CATEGORY_TERMS
    term_res = [(t, re.compile(re.escape(normalize_text(t)), re.I)) for t in terms]
    scored: list[tuple[str, float, str]] = []

    for rec in universe:
        score = 0.0
        reasons: list[str] = []
        cat_blob = normalize_text(" ".join(rec.categories))
        for t, cre in term_res:
            if cat_blob and cre.search(cat_blob):
                score += 0.5
                reasons.append(f"cat:{t}")
        # Nature of object / modality
        mod = normalize_text(rec.modalidade)
        for hint in DEFAULT_MODALIDADE_HINTS:
            if hint in mod:
                score += 0.15
                reasons.append(f"mod:{hint}")
        # Technical documents associated
        if rec.has_tr:
            score += 0.2
            reasons.append("has_tr")
        if rec.has_etp:
            score += 0.15
            reasons.append("has_etp")
        if rec.has_edital and rec.has_anexos:
            score += 0.1
            reasons.append("edital+anexos")
        # Org name infrastructure signals (weak metadata)
        org = normalize_text(rec.orgao)
        for kw in ("obras", "infraestrutura", "saneamento", "urbanismo", "engenharia"):
            if kw in org:
                score += 0.25
                reasons.append(f"org_meta:{kw}")
                break

        if score > 0:
            scored.append((rec.canonical_id, score, ",".join(reasons[:6])))

    scored.sort(key=lambda x: (-x[1], x[0]))
    hits: dict[str, RetrievalHit] = {}
    for rank, (cid, score, reason) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="metadata",
            score=score,
            rank=rank,
            reason=reason,
        )
    return hits
