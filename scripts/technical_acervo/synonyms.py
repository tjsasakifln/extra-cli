"""Synonym expansion for acervo search (pure)."""

from __future__ import annotations

from typing import Any

from scripts.technical_acervo.normalize import normalize_text


def build_synonym_map(synonyms: dict[str, list[str]] | None) -> dict[str, set[str]]:
    """Bidirectional synonym map of normalized terms."""
    graph: dict[str, set[str]] = {}
    if not synonyms:
        return graph
    for head, alts in synonyms.items():
        h = normalize_text(head)
        members = {h}
        for a in alts or []:
            members.add(normalize_text(a))
        for m in members:
            graph.setdefault(m, set()).update(members)
    return graph


def expand_query_terms(query: str, synonym_map: dict[str, set[str]]) -> set[str]:
    """Expand a free-text query into normalized terms including synonyms."""
    q = normalize_text(query)
    terms: set[str] = {q}
    if not q:
        return terms
    # whole-phrase synonyms
    for key, group in synonym_map.items():
        if key and key in q:
            terms |= group
            terms.add(key)
    # token-level
    tokens = [t for t in q.split() if len(t) > 1]
    for i, tok in enumerate(tokens):
        terms.add(tok)
        if tok in synonym_map:
            terms |= synonym_map[tok]
        # bigrams / trigrams
        if i + 1 < len(tokens):
            bi = f"{tok} {tokens[i + 1]}"
            terms.add(bi)
            if bi in synonym_map:
                terms |= synonym_map[bi]
        if i + 2 < len(tokens):
            tri = f"{tok} {tokens[i + 1]} {tokens[i + 2]}"
            terms.add(tri)
            if tri in synonym_map:
                terms |= synonym_map[tri]
    # multi-word keys contained in query
    for key, group in synonym_map.items():
        if " " in key and key in q:
            terms |= group
    return {t for t in terms if t}


_STOPWORDS = frozenset(
    {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "em",
        "para",
        "com",
        "por",
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "no",
        "na",
        "nos",
        "nas",
        "ao",
        "aos",
        "contra",  # avoids contrapiso false positive from "prevenção contra incêndio"
        "acima",
        "maior",
        "minimo",
        "possui",
        "acervo",
        "extra",
        "quais",
        "qual",
        "existe",
        "ha",
    }
)


def terms_match_blob(terms: set[str], blob: str) -> tuple[bool, list[str]]:
    """Return whether any meaningful term hits the blob and which ones.

    Prefer multi-word / longer terms. Single tokens must appear as whole words
    (space-bounded) to avoid 'contra' matching 'contrapiso'.
    """
    import re

    hits: list[str] = []
    nb = normalize_text(blob)
    padded = f" {nb} "
    for t in sorted(terms, key=len, reverse=True):
        if len(t) < 3 or t in _STOPWORDS:
            continue
        if " " in t:
            if t in nb:
                hits.append(t)
        else:
            if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", padded):
                hits.append(t)
    return (bool(hits), hits)


def service_related_to_query(service: str, query: str, synonym_map: dict[str, set[str]]) -> bool:
    terms = expand_query_terms(query, synonym_map)
    ok, _ = terms_match_blob(terms, service)
    return ok


def default_builtin_synonyms() -> dict[str, list[str]]:
    """Fallback synonyms if store has none (should match seed)."""
    return {
        "drywall": ["gesso acartonado", "parede de gesso acartonado"],
        "gesso acartonado": ["drywall"],
        "instalacao hidraulica": ["rede hidrossanitaria", "instalacoes hidraulicas"],
        "rede hidrossanitaria": ["instalacao hidraulica", "instalacoes hidraulicas"],
        "spcip": ["sistema preventivo contra incendio", "prevencao contra incendio"],
        "estrutura metalica": ["estrutura de aco"],
        "estrutura de aco": ["estrutura metalica"],
        "galpao": ["galpao industrial"],
        "galpao industrial": ["galpao"],
        "eletrica bt": ["instalacao eletrica de baixa tensao"],
        "edificacao tombada": ["edificacao historica", "patrimonio historico"],
        "edificacao historica": ["edificacao tombada", "patrimonio historico"],
    }


def synonym_map_from_store(store: Any) -> dict[str, set[str]]:
    raw = getattr(store, "synonyms", None) or default_builtin_synonyms()
    return build_synonym_map(raw)
