"""Entity matching module — cascade de 3 niveis para entidades publicas.

Fornece o pipeline de entity matching usado pelo sistema de monitoramento
para associar bids/licitacoes a entidades publicas cadastradas.

Strategies (aplicadas em ordem por bid):
    Level 1 — CNPJ exact match (8-digit base)          [confidence: high]
    Level 2 — Normalized name + municipio constraint   [confidence: high]
    Level 2b — Alias matching (siglas e padroes)       [confidence: high]
    Level 3 — Fuzzy matching (difflib / rapidfuzz)     [confidence: high|medium|low]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config.logging_config import get_logger
from scripts.lib.name_normalizer import find_unknown_abbreviations, normalize_name

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------

ENTITY_MATCH_FUZZY_THRESHOLD = float(os.getenv("ENTITY_MATCH_FUZZY_THRESHOLD", "0.85"))
"""Default fuzzy threshold for entity name matching."""

ENTITY_MATCH_FUZZY_THRESHOLD_SMALL_CITY = float(os.getenv("ENTITY_MATCH_FUZZY_THRESHOLD_SMALL_CITY", "0.75"))
"""Fuzzy threshold for small cities (< 5,000 inhabitants)."""

SMALL_CITY_POPULATION_THRESHOLD = int(os.getenv("SMALL_CITY_POPULATION_THRESHOLD", "5000"))
"""Population below which a city is considered 'small' for threshold adjustment."""

ENTITY_MATCH_LOG_UNKNOWN_ABBREVIATIONS = os.getenv("ENTITY_MATCH_LOG_UNKNOWN_ABBREVIATIONS", "true").lower() == "true"
"""Whether to log unknown abbreviations found during normalization."""

# ---------------------------------------------------------------------------
# Population data cache
# ---------------------------------------------------------------------------

_POPULATION_DATA: dict[str, int] | None = None


def _load_population_data() -> dict[str, int]:
    """Load municipality population data from ``config/municipio_population.yaml``.

    Returns:
        Dict mapping IBGE code (str) -> population (int).
    """
    global _POPULATION_DATA
    if _POPULATION_DATA is not None:
        return _POPULATION_DATA

    _POPULATION_DATA = {}
    path = Path(__file__).resolve().parent.parent.parent / "config" / "municipio_population.yaml"
    if not path.exists():
        logger.warning("Population data not found at %s — using default threshold for all cities", path)
        return _POPULATION_DATA

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    _POPULATION_DATA[str(k)] = int(v)
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        logger.error("Failed to load population data: %s", e)

    logger.debug("Loaded population data for %d municipalities", len(_POPULATION_DATA))
    return _POPULATION_DATA


def _get_fuzzy_threshold(codigo_ibge: str) -> float:
    """Get appropriate fuzzy threshold based on municipality population.

    Small cities (< SMALL_CITY_POPULATION_THRESHOLD) use a lower threshold
    to compensate for shorter/less distinctive entity names.

    Args:
        codigo_ibge: IBGE code (7 digits) of the municipality.

    Returns:
        Fuzzy threshold to use for matching.
    """
    pop_data = _load_population_data()
    pop = pop_data.get(codigo_ibge)
    if pop is not None and pop < SMALL_CITY_POPULATION_THRESHOLD:
        return ENTITY_MATCH_FUZZY_THRESHOLD_SMALL_CITY
    return ENTITY_MATCH_FUZZY_THRESHOLD


def _get_small_city_ibge_codes() -> set[str]:
    """Return set of IBGE codes for municipalities with population < threshold."""
    pop_data = _load_population_data()
    return {code for code, pop in pop_data.items() if pop < SMALL_CITY_POPULATION_THRESHOLD}


# ---------------------------------------------------------------------------
# Name alias generation for fuzzy matching
# ---------------------------------------------------------------------------


def generate_name_aliases(norm_name: str) -> list[str]:
    """Generate alternate normalized names for common entity name patterns.

    Handles:
    1. "PREFEITURA MUNICIPAL DE X" -> "MUNICIPIO DE X"
    2. "PREFEITURA DE X" -> "MUNICIPIO DE X"
    3. "CAMARA DE VEREADORES DE X" -> "X CAMARA DE VEREADORES"
    4. "X CAMARA DE VEREADORES" -> "CAMARA DE VEREADORES DE X"
    5. "CAMARA MUNICIPAL DE X" -> "X CAMARA MUNICIPAL"
    6. "CAMARA MUNICIPAL DE VEREADORES DE X" -> "X CAMARA MUNICIPAL DE VEREADORES"

    Args:
        norm_name: Already-normalized name string.

    Returns:
        List of zero or more alias normalized strings (unique, order preserved).
    """
    aliases: list[str] = []

    # Pattern 1: "PREFEITURA MUNICIPAL DE X" -> "MUNICIPIO DE X"
    prefix_prefeitura = "PREFEITURA MUNICIPAL DE "
    if norm_name.startswith(prefix_prefeitura):
        city = norm_name[len(prefix_prefeitura) :]
        aliases.append(normalize_name(f"MUNICIPIO DE {city}"))

    # Pattern 2: "PREFEITURA DE X" -> "MUNICIPIO DE X"
    prefix_prefeitura_short = "PREFEITURA DE "
    if norm_name.startswith(prefix_prefeitura_short):
        city = norm_name[len(prefix_prefeitura_short) :]
        aliases.append(normalize_name(f"MUNICIPIO DE {city}"))

    # Pattern 3: "CAMARA DE VEREADORES DE X" -> "X CAMARA DE VEREADORES"
    prefix_camara_vereadores = "CAMARA DE VEREADORES DE "
    if norm_name.startswith(prefix_camara_vereadores):
        city = norm_name[len(prefix_camara_vereadores) :]
        aliases.append(normalize_name(f"{city} CAMARA DE VEREADORES"))

    # Pattern 4: "X CAMARA DE VEREADORES" -> "CAMARA DE VEREADORES DE X"
    suffix_camara_vereadores = " CAMARA DE VEREADORES"
    if norm_name.endswith(suffix_camara_vereadores):
        city = norm_name[: -len(suffix_camara_vereadores)]
        aliases.append(normalize_name(f"CAMARA DE VEREADORES DE {city}"))

    # Pattern 5: "CAMARA MUNICIPAL DE X" -> "X CAMARA MUNICIPAL"
    prefix_camara_municipal = "CAMARA MUNICIPAL DE "
    if norm_name.startswith(prefix_camara_municipal):
        city = norm_name[len(prefix_camara_municipal) :]
        aliases.append(normalize_name(f"{city} CAMARA MUNICIPAL"))

    # Pattern 6: "CAMARA MUNICIPAL DE VEREADORES DE X" -> "X CAMARA MUNICIPAL DE VEREADORES"
    prefix_camara_municipal_vereadores = "CAMARA MUNICIPAL DE VEREADORES DE "
    if norm_name.startswith(prefix_camara_municipal_vereadores):
        city = norm_name[len(prefix_camara_municipal_vereadores) :]
        aliases.append(normalize_name(f"{city} CAMARA MUNICIPAL DE VEREADORES"))

    # Filter out duplicates while preserving order
    seen: set[str] = set()
    unique_aliases: list[str] = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            unique_aliases.append(a)

    return unique_aliases


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
    """3-level+ cascade entity matching for a source.

    Logs ``match_method``, ``match_score``, ``match_confidence`` to the bid row
    for every bid (including unmatched).

    Strategies (applied in order per bid):
        Level 1 — CNPJ exact match (8-digit base)          [confidence: high]
        Level 2 — Normalized name + municipio constraint   [confidence: high]
        Level 2b — Alias matching (padroes de nome)        [confidence: high]
        Level 3 — Fuzzy matching (rapidfuzz / difflib)     [confidence: high|medium|low]

    Args:
        conn: Database connection.
        source: Data source tag (``pncp``, ``dom_sc``, etc.).
        entities: List of entity dicts from ``load_entities()``.

    Returns:
        Stats dict with keys ``cnpj``, ``name_normalized``, ``alias``,
        ``fuzzy``, ``unmatched``, ``total``.
    """
    logger.info(
        "Starting cascade matching for source=%s with %d entities",
        source,
        len(entities),
    )

    # Build known abbreviations set for AC5 detection
    known_abbrev: set[str] = set()
    try:
        from scripts.lib.name_normalizer import ABBREVIATIONS

        known_abbrev.update(ABBREVIATIONS.keys())
    except Exception:
        pass

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
        return {"cnpj": 0, "name_normalized": 0, "alias": 0, "fuzzy": 0, "unmatched": 0, "total": 0}

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
    alias_muni_index: dict[tuple[str, str], dict[str, Any]] = {}
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

            # Build alias index for Level 2b
            aliases = generate_name_aliases(norm)
            for alias in aliases:
                if alias not in name_exact_index:
                    name_exact_index[alias] = e
                if ibge:
                    key = (alias, ibge)
                    if key not in alias_muni_index:
                        alias_muni_index[key] = e

    # Step 3 — try to import rapidfuzz (fallback to difflib)
    try:
        from rapidfuzz import fuzz as _rapidfuzz

        def _fuzz_ratio(a: str, b: str) -> float:
            return _rapidfuzz.ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher

        logger.warning(
            "rapidfuzz not installed — falling back to difflib.SequenceMatcher "
            "for fuzzy entity matching. This is slower and less accurate. "
            "Install rapidfuzz via: pip install rapidfuzz"
        )

        def _fuzz_ratio(a: str, b: str) -> float:  # type: ignore[misc]
            return SequenceMatcher(None, a, b).ratio()

    # Step 4 — cascade matching per bid
    stats: dict[str, int] = {"cnpj": 0, "name_normalized": 0, "alias": 0, "fuzzy": 0, "unmatched": 0}

    # Track unknown abbreviations across all bids (AC5)
    all_unknown_abbrevs: set[str] = set()

    for bid in unmatched_bids:
        pncp_id = bid["pncp_id"]
        orgao_cnpj = (bid.get("orgao_cnpj") or "").strip()
        orgao_razao = (bid.get("orgao_razao_social") or "").strip()
        codigo_ibge = (bid.get("codigo_municipio_ibge") or "").strip()

        matched_entity = None
        match_method = "unmatched"
        match_score = 0.0
        match_confidence: str | None = None

        # Detect unknown abbreviations (AC5)
        if ENTITY_MATCH_LOG_UNKNOWN_ABBREVIATIONS and orgao_razao:
            raw_upper = orgao_razao.upper()
            unknown = find_unknown_abbreviations(raw_upper, known_set=known_abbrev)
            if unknown:
                all_unknown_abbrevs.update(unknown)

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
        # Level 2b: Alias matching (AC3)
        # ------------------------------------------------------------------
        if orgao_razao and not matched_entity:
            norm_name = normalize_name(orgao_razao)
            if norm_name:
                aliases = generate_name_aliases(norm_name)
                for alias in aliases:
                    # Try with municipio constraint first
                    if codigo_ibge and (alias, codigo_ibge) in alias_muni_index:
                        matched_entity = alias_muni_index[(alias, codigo_ibge)]
                        match_method = "alias"
                        match_score = 1.0
                        match_confidence = "high"
                        break
                    # Then without constraint
                    if not matched_entity and alias in name_exact_index:
                        matched_entity = name_exact_index[alias]
                        match_method = "alias"
                        match_score = 1.0
                        match_confidence = "high"
                        break

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

                # Use adaptive threshold based on municipality size (AC4)
                threshold = _get_fuzzy_threshold(codigo_ibge) if codigo_ibge else ENTITY_MATCH_FUZZY_THRESHOLD
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

    # Log unknown abbreviations found (AC5)
    if ENTITY_MATCH_LOG_UNKNOWN_ABBREVIATIONS and all_unknown_abbrevs:
        logger.info(
            "Unknown abbreviations detected (%d unique): %s",
            len(all_unknown_abbrevs),
            sorted(all_unknown_abbrevs),
        )

    stats["total"] = sum(stats.values())
    logger.info(
        "Cascade matching done for source=%s — CNPJ=%d, name=%d, alias=%d, fuzzy=%d, unmatched=%d, total=%d",
        source,
        stats["cnpj"],
        stats["name_normalized"],
        stats["alias"],
        stats["fuzzy"],
        stats["unmatched"],
        stats["total"],
    )
    return stats
