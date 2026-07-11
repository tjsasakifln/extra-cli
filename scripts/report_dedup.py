#!/usr/bin/env python3
"""
HARD-001: Semantic deduplication module.

Extracted from collect-report-data.py to keep the main file focused on
data collection. Provides token normalization, Jaccard similarity, and
a two-pass deduplication pipeline (exact + semantic).

Usage:
    from report_dedup import normalize_for_dedup, jaccard_similarity, semantic_dedup
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _strip_accents(s: str) -> str:
    """Remove diacritics from string."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize_for_dedup(text: str) -> set[str]:
    """Normalize object text for deduplication comparison.

    Strips accents, lowercases, removes punctuation, and splits into
    a set of meaningful tokens (ignores very short words and stopwords).

    Returns a set of tokens for Jaccard similarity comparison.
    """
    if not text:
        return set()

    # Normalize: lowercase, strip accents
    text = _strip_accents(text.lower().strip())

    # Remove punctuation (keep letters, digits, spaces)
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Tokenize and filter short/noise words
    stopwords = {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "para",
        "com",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "ao",
        "aos",
        "as",
        "um",
        "uma",
        "uns",
        "umas",
        "e",
        "ou",
        "que",
        "se",
        "sem",
        "ate",
        "ser",
        "sao",
        "mais",
        "mas",
        "ja",
        "la",
        "lhe",
        "lhes",
        "pelo",
        "pela",
        "pelos",
        "pelas",
        "pra",
        "pro",
        "a",
        "o",
        "os",
        "as",
        "d",
        "s",
        "n",
        "r$",
        "rs",
        "valor",
        "total",
        "item",
        "items",
        "itens",
        "edital",
        "licitacao",
        "contrato",
        "processo",
    }

    tokens = set()
    for word in text.split():
        word = word.strip()
        # Skip very short words and stopwords
        if len(word) <= 2 and word not in ("r$",):
            continue
        if word in stopwords:
            continue
        # Skip pure numbers
        if word.isdigit():
            continue
        tokens.add(word)

    return tokens


def jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Compute Jaccard similarity coefficient between two token sets.

    Returns a float in [0.0, 1.0]. Returns 0.0 if both sets are empty.
    """
    if not tokens_a and not tokens_b:
        return 0.0
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)

    if union == 0:
        return 0.0

    return intersection / union


def semantic_dedup(
    editais: list[dict],
    jaccard_threshold: float = 0.85,
    warning_threshold: float = 0.75,
) -> tuple[list[dict], dict[str, Any]]:
    """Two-pass deduplication: exact (by ID) then semantic (Jaccard).

    Args:
        editais: List of edital dicts with at least 'objeto' field.
        jaccard_threshold: Score above this = definite duplicate (removed).
        warning_threshold: Score between warning_threshold and jaccard_threshold
                          = grey zone (logged in warnings).

    Returns:
        (deduped_editais, stats_dict) where stats_dict has:
            exact_removed: int
            semantic_removed: int
            candidates_evaluated: int
            semantic_warnings: list[dict] — items in grey zone
    """
    stats: dict[str, Any] = {
        "exact_removed": 0,
        "semantic_removed": 0,
        "candidates_evaluated": 0,
        "semantic_warnings": [],
    }

    if not editais:
        return [], stats

    # ── Pass 1: Exact dedup by unique ID (cnpj_orgao + ano + sequencial) ──
    seen_ids: set[str] = set()
    pass1: list[dict] = []

    for ed in editais:
        # Build a unique key
        cnpj_orgao = str(ed.get("cnpj_orgao", ed.get("orgao_cnpj", "")) or "")
        ano = str(ed.get("ano_compra", ed.get("ano", "")) or "")
        sequencial = str(ed.get("sequencial_compra", ed.get("id", ed.get("numero", ""))) or "")
        unique_id = f"{cnpj_orgao}|{ano}|{sequencial}"

        # Fallback: use objeto hash
        if unique_id.strip("|") == "":
            obj = str(ed.get("objeto", ed.get("objetoCompra", "")) or "")
            unique_id = f"obj_{hash(obj)}"

        if unique_id in seen_ids:
            stats["exact_removed"] += 1
            continue

        seen_ids.add(unique_id)
        # Keep PNCP-sourced items when priority matters
        if ed.get("_source_name") == "PNCP":
            pass1.append(ed)
        else:
            pass1.append(ed)

    # ── Pass 2: Semantic dedup by Jaccard similarity ──
    deduped: list[dict] = []
    semantic_removed_indices: set[int] = set()

    for i in range(len(pass1)):
        if i in semantic_removed_indices:
            continue

        obj_i = str(pass1[i].get("objeto", pass1[i].get("objetoCompra", "")) or "")
        tokens_i = normalize_for_dedup(obj_i)
        current_best = pass1[i]

        for j in range(i + 1, len(pass1)):
            if j in semantic_removed_indices:
                continue

            obj_j = str(pass1[j].get("objeto", pass1[j].get("objetoCompra", "")) or "")
            tokens_j = normalize_for_dedup(obj_j)
            sim = jaccard_similarity(tokens_i, tokens_j)

            stats["candidates_evaluated"] += 1

            if sim >= jaccard_threshold:
                # Definite duplicate — keep PNCP source if conflict
                semantic_removed_indices.add(j)
                stats["semantic_removed"] += 1
            elif sim >= warning_threshold:
                # Grey zone — log warning
                warning_obj_a = obj_i[:100]
                warning_obj_b = obj_j[:100]
                if warning_obj_a != warning_obj_b:
                    stats["semantic_warnings"].append(
                        {
                            "score": round(sim, 4),
                            "objeto_a": warning_obj_a,
                            "objeto_b": warning_obj_b,
                        }
                    )

        deduped.append(current_best)

    return deduped, stats
