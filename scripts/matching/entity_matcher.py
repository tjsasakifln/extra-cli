"""Entity matching module — cascade de 3 niveis para entidades publicas.

Fornece o pipeline de entity matching usado pelo sistema de monitoramento
para associar bids/licitacoes a entidades publicas cadastradas.

Strategies (aplicadas em ordem por bid):
    Level 1 — CNPJ exact match (8-digit base)          [confidence: high]
    Level 2 — Normalized name + municipio constraint   [confidence: high]
    Level 3 — Fuzzy matching (difflib / rapidfuzz)     [confidence: high|medium|low]
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from config.logging_config import get_logger
from scripts.lib.name_normalizer import normalize_name

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------

ENTITY_MATCH_FUZZY_THRESHOLD = float(os.getenv("ENTITY_MATCH_FUZZY_THRESHOLD", "0.85"))


# ---------------------------------------------------------------------------
# Single-entity matching
# ---------------------------------------------------------------------------


def match_entity(orgao_cnpj: str, entities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match an ``orgao_cnpj`` (14 digits) against entity list (``cnpj_8`` base).

    Args:
        orgao_cnpj: CNPJ string (may include non-digit chars).
        entities: List of entity dicts with ``cnpj_8`` key.

    Returns:
        Matched entity dict, or ``None``.
    """
    if not orgao_cnpj:
        return None
    cnpj_clean = "".join(c for c in orgao_cnpj if c.isdigit())
    # Try exact 14-digit match first
    for e in entities:
        if e["cnpj_8"] and cnpj_clean.startswith(e["cnpj_8"]):
            return e
    # Try just the 8-digit base
    cnpj_base = cnpj_clean[:8]
    for e in entities:
        if e["cnpj_8"] == cnpj_base:
            return e
    return None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def update_matched_entity_full(
    conn: Any,
    pncp_id: str,
    entity_id: int | None,
    match_method: str | None = None,
    match_score: float | None = None,
    match_confidence: str | None = None,
) -> None:
    """Set ``matched_entity_id`` + match metadata on a bid record."""
    cur = conn.cursor()
    cur.execute(
        """UPDATE pncp_raw_bids
           SET matched_entity_id = %s,
               match_method = %s,
               match_score = %s,
               match_confidence = %s
           WHERE pncp_id = %s""",
        (entity_id, match_method, match_score, match_confidence, pncp_id),
    )
    cur.close()


# ---------------------------------------------------------------------------
# Cascade matching
# ---------------------------------------------------------------------------


def match_entities_cascade(conn: Any, source: str, entities: list[dict[str, Any]]) -> dict[str, int]:
    """3-level cascade entity matching for a source.

    Logs ``match_method``, ``match_score``, ``match_confidence`` to the bid row
    for every bid (including unmatched).

    Args:
        conn: Database connection.
        source: Data source tag (``pncp``, ``dom_sc``, etc.).
        entities: List of entity dicts from ``load_entities()``.

    Returns:
        Stats dict with keys ``cnpj``, ``name_normalized``, ``fuzzy``,
        ``unmatched``, ``total``.
    """
    logger.info(
        "Starting cascade matching for source=%s with %d entities",
        source,
        len(entities),
    )
    # Step 1 — fetch all unmatched bids for this source
    cur = conn.cursor()
    cur.execute(
        """SELECT pncp_id, orgao_cnpj, orgao_razao_social, municipio,
                  codigo_municipio_ibge
           FROM pncp_raw_bids
           WHERE source = %s AND matched_entity_id IS NULL
             AND (
                (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
                OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
             )""",
        (source,),
    )
    cols = [d[0] for d in cur.description]
    unmatched_bids = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()

    if not unmatched_bids:
        logger.info("No unmatched bids for source=%s — skipping matching", source)
        return {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 0}

    logger.info("Matching %d bids for source=%s", len(unmatched_bids), source)
    # Step 2 — build entity lookup structures
    # CNPJ index: cnpj_8 -> entity
    cnpj_index: dict[str, dict[str, Any]] = {}
    for e in entities:
        cnpj_8 = e.get("cnpj_8")
        if cnpj_8:
            cnpj_index[cnpj_8] = e

    # Name indexes
    name_exact_index: dict[str, dict[str, Any]] = {}
    name_muni_index: dict[tuple[str, str], dict[str, Any]] = {}
    all_entities_norm: list[dict[str, Any]] = []

    for e in entities:
        norm = normalize_name(e.get("razao_social", ""))
        if norm:
            name_exact_index[norm] = e
            e["_normalized_name"] = norm
            ibge = e.get("codigo_ibge")
            if ibge:
                name_muni_index[(norm, ibge)] = e
            all_entities_norm.append(e)

    # Step 3 — try to import rapidfuzz (fallback to difflib)
    try:
        from rapidfuzz import fuzz as _rapidfuzz

        _fuzz_ratio: Callable[[str, str], float] = lambda a, b: _rapidfuzz.ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher

        logger.warning(
            "rapidfuzz not installed — falling back to difflib.SequenceMatcher "
            "for fuzzy entity matching. This is slower and less accurate. "
            "Install rapidfuzz via: pip install rapidfuzz"
        )
        _fuzz_ratio = lambda a, b: SequenceMatcher(None, a, b).ratio()

    # Step 4 — cascade matching per bid
    stats: dict[str, int] = {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0}

    for bid in unmatched_bids:
        pncp_id = bid["pncp_id"]
        orgao_cnpj = (bid.get("orgao_cnpj") or "").strip()
        orgao_razao = (bid.get("orgao_razao_social") or "").strip()
        codigo_ibge = (bid.get("codigo_municipio_ibge") or "").strip()

        matched_entity = None
        match_method = "unmatched"
        match_score = 0.0
        match_confidence: str | None = None

        # ------------------------------------------------------------------
        # Level 1: CNPJ exact match (8-digit base)
        # ------------------------------------------------------------------
        if orgao_cnpj and not matched_entity:
            cnpj_clean = "".join(c for c in orgao_cnpj if c.isdigit())
            cnpj_base = cnpj_clean[:8]

            # Exact 8-digit match
            if cnpj_base in cnpj_index:
                matched_entity = cnpj_index[cnpj_base]
                match_method = "cnpj"
                match_score = 1.0
                match_confidence = "high"
            elif len(cnpj_clean) >= 14:
                # Prefix match: 14-digit CNPJ starting with entity's 8-digit base
                for prefix, e in cnpj_index.items():
                    if cnpj_clean.startswith(prefix):
                        matched_entity = e
                        match_method = "cnpj"
                        match_score = 1.0
                        match_confidence = "high"
                        break

        # ------------------------------------------------------------------
        # Level 2: Normalized name + municipio constraint
        # ------------------------------------------------------------------
        if orgao_razao and not matched_entity:
            norm_name = normalize_name(orgao_razao)
            if norm_name:
                # 2a — with municipio constraint (IBGE code)
                if codigo_ibge and (norm_name, codigo_ibge) in name_muni_index:
                    matched_entity = name_muni_index[(norm_name, codigo_ibge)]
                    match_method = "name_normalized"
                    match_score = 1.0
                    match_confidence = "high"

                # 2b — without municipio constraint (fallback)
                if not matched_entity and norm_name in name_exact_index:
                    matched_entity = name_exact_index[norm_name]
                    match_method = "name_normalized"
                    match_score = 1.0
                    match_confidence = "high"

        # ------------------------------------------------------------------
        # Level 3: Fuzzy matching (difflib / rapidfuzz)
        # ------------------------------------------------------------------
        if orgao_razao and not matched_entity and all_entities_norm:
            norm_name = normalize_name(orgao_razao)
            if norm_name:
                best_score = 0.0
                best_entity = None

                # Filter candidates by IBGE code if available
                candidates = all_entities_norm
                if codigo_ibge:
                    candidates = [e for e in all_entities_norm if e.get("codigo_ibge") == codigo_ibge]

                for e in candidates:
                    e_norm = e.get("_normalized_name", "")
                    if not e_norm:
                        continue
                    score = _fuzz_ratio(norm_name, e_norm)
                    if score > best_score:
                        best_score = score
                        best_entity = e

                threshold = ENTITY_MATCH_FUZZY_THRESHOLD
                if best_score >= threshold and best_entity:
                    matched_entity = best_entity
                    match_method = "fuzzy"
                    match_score = round(best_score, 3)
                    if best_score >= 0.95:
                        match_confidence = "high"
                    elif best_score >= threshold:
                        match_confidence = "medium"
                    else:
                        match_confidence = "low"

        # ------------------------------------------------------------------
        # Update bid with result
        # ------------------------------------------------------------------
        if matched_entity:
            update_matched_entity_full(
                conn,
                pncp_id,
                matched_entity["id"],
                match_method,
                match_score,
                match_confidence,
            )
            stats[match_method] = stats[match_method] + 1
        else:
            update_matched_entity_full(
                conn,
                pncp_id,
                None,
                "unmatched",
                0.0,
                None,
            )
            stats["unmatched"] += 1

    # Single commit for the entire batch
    conn.commit()

    stats["total"] = sum(stats.values())
    logger.info(
        "Cascade matching done for source=%s — CNPJ=%d, name=%d, fuzzy=%d, unmatched=%d, total=%d",
        source,
        stats["cnpj"],
        stats["name_normalized"],
        stats["fuzzy"],
        stats["unmatched"],
        stats["total"],
    )
    return stats
