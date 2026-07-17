#!/usr/bin/env python3
"""Deterministic classifier for public procurement acts (DOM/DOE text).

Classifies free-text titles/bodies into procurement act categories without ML.
Used for CIGA/DOM-SC publications and bulk DOE-SC open data rows.

Categories (stable machine ids):
  aviso_licitacao, edital, retificacao, suspensao, revogacao, anulacao,
  homologacao, adjudicacao, extrato_contrato, termo_aditivo, rescisao,
  ata_registro_precos, dispensa, inexigibilidade, credenciamento,
  intencao_registro_precos, outros
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# Order matters: more specific patterns first.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("termo_aditivo", re.compile(r"\b(termo\s+aditiv|aditivo\s+ao\s+contrato|aditamento)\b", re.I)),
    ("ata_registro_precos", re.compile(r"\b(ata\s+de\s+registro\s+de\s+pre[cç]os?|registro\s+de\s+pre[cç]os?)\b", re.I)),
    ("intencao_registro_precos", re.compile(r"\b(inten[cç][aã]o\s+de\s+registro\s+de\s+pre[cç]os?|irp)\b", re.I)),
    ("extrato_contrato", re.compile(r"\b(extrato\s+d[eo]\s+contrato|contrato\s+n[ºo°]?)\b", re.I)),
    ("rescisao", re.compile(r"\b(rescis[aã]o|distrato)\b", re.I)),
    ("homologacao", re.compile(r"\bhomologa", re.I)),
    ("adjudicacao", re.compile(r"\badjudica", re.I)),
    ("revogacao", re.compile(r"\brevoga", re.I)),
    ("anulacao", re.compile(r"\banula", re.I)),
    ("suspensao", re.compile(r"\bsuspens", re.I)),
    ("retificacao", re.compile(r"\b(retifica[cç][aã]o|errata|republica)", re.I)),
    ("dispensa", re.compile(r"\bdispensa\s+de\s+licita", re.I)),
    ("inexigibilidade", re.compile(r"\binexigib", re.I)),
    ("credenciamento", re.compile(r"\bcredenciament", re.I)),
    ("edital", re.compile(r"\b(edital\s+de\s+licita|aviso\s+de\s+edital|publica[cç][aã]o\s+de\s+edital)\b", re.I)),
    ("aviso_licitacao", re.compile(r"\b(aviso\s+de\s+licita|chamamento\s+p[uú]blico|preg[aã]o|concorr[eê]ncia|tomada\s+de\s+pre[cç]os?)\b", re.I)),
]

ALL_CATEGORIES: tuple[str, ...] = tuple(sorted({c for c, _ in _RULES} | {"outros"}))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def classify_act(text: str, *, secondary: str | None = None) -> dict[str, object]:
    """Classify a single act text.

    Returns dict with category, matched_rule, confidence ('high'|'low'), evidence snippet.
    """
    blob = _normalize(text)
    if secondary:
        blob = f"{blob} {_normalize(secondary)}".strip()
    if not blob:
        return {
            "category": "outros",
            "matched_rule": None,
            "confidence": "low",
            "evidence": "",
        }
    for category, pattern in _RULES:
        m = pattern.search(blob)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(blob), m.end() + 20)
            return {
                "category": category,
                "matched_rule": pattern.pattern,
                "confidence": "high",
                "evidence": blob[start:end],
            }
    return {
        "category": "outros",
        "matched_rule": None,
        "confidence": "low",
        "evidence": blob[:80],
    }


def classify_many(texts: Iterable[str]) -> list[dict[str, object]]:
    return [classify_act(t) for t in texts]
