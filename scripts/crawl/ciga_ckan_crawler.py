#!/usr/bin/env python3
"""CIGA CKAN Crawler — DOM-SC public procurement entity coverage.

Source: https://dados.ciga.sc.gov.br/ — CIGA open data portal (CKAN)
Dataset: ``domsc-publicacoes-de-{month}-{year}`` (Jan 2023 - Dec 2025)
Each monthly dataset contains ~90 ZIP resources (3 per day), each with a JSON
containing an ``autopublicacoes`` array of flat publication records.

The crawler extracts unique entity names (entidade + municipio) from
procurement-relevant categories (Contratos, Licitações, Ata de registro de preços,
Extrato de Contrato, Convênios), matches them against ``sc_public_entities``
by normalized name + municipio, and records coverage in ``entity_coverage``.

Integration with monitor.py:
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Usage:
    python -m scripts.crawl.ciga_ckan_crawler --month 12-2025
    python -m scripts.crawl.ciga_ckan_crawler --all-months
    python -m scripts.crawl.ciga_ckan_crawler --report
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DEFAULT_DSN  # noqa: E402
from scripts.crawl.security import USER_AGENT  # noqa: E402

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CKAN_BASE = "https://dados.ciga.sc.gov.br"
CKAN_API = f"{CKAN_BASE}/api/3/action"

# Procurement-relevant categories in DOM-SC publications
PROCUREMENT_CATEGORIES = frozenset(
    {
        "Contratos",
        "Licitações",
        "Ata de registro de preços",
        "Extrato de Contrato",
        "Convênios",
    }
)

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between CKAN requests
HTTP_TIMEOUT = 60  # seconds per request

# User agent — imported from scripts.crawl.security

# CIGA CKAN only discovers entities and updates entity_coverage.
# It does NOT extract bid records — transform() legitimately returns [].
# monitor.py reads this attribute to skip the upsert phase.
SOURCE_PURPOSE = "coverage_only"


# ---------------------------------------------------------------------------
# CKAN API client
# ---------------------------------------------------------------------------


def _ckan_request(url: str) -> dict | None:
    """Make a CKAN API GET request with error handling."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            result = json.loads(resp.read())
        if not result.get("success"):
            _logger.warning("CKAN API returned success=false for %s", url)
            return None
        return result.get("result")
    except urllib.error.HTTPError as e:
        _logger.error("CKAN HTTP %d for %s: %s", e.code, url, e.reason)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        _logger.error("CKAN request failed for %s: %s", url, e)
        return None


def list_datasets() -> list[str]:
    """List all available CKAN datasets."""
    result = _ckan_request(f"{CKAN_API}/package_list")
    if not result:
        return []
    return sorted(result)


def get_package(pkg_id: str) -> dict | None:
    """Get details for a CKAN package (dataset)."""
    return _ckan_request(f"{CKAN_API}/package_show?id={pkg_id}")


def list_domsc_months() -> list[str]:
    """List all DOM-SC monthly dataset IDs, sorted oldest first."""
    all_datasets = list_datasets()
    domsc = sorted([d for d in all_datasets if d.startswith(("domsc-publicacoes-de-", "dom-sc-publicacoes-de-"))])
    return domsc


def classify_month(domsc_id: str) -> str | None:
    """Extract month-year label from DOM-SC dataset ID.

    Returns "MM-YYYY" or None.
    """
    # Format: domsc-publicacoes-de-{month}-{year}
    parts = domsc_id.split("-")
    for i, p in enumerate(parts):
        if p == "de" and i + 2 < len(parts):
            return f"{parts[i + 1]}-{parts[i + 2]}"
    return None


def get_package_resources(pkg: dict) -> list[dict]:
    """Extract resource list from a CKAN package dict."""
    return pkg.get("resources", [])


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------


def download_resource(url: str) -> dict | None:
    """Download a ZIP resource, parse it, return the JSON content.

    DOM-SC resources are ZIP files containing one JSON file with key
    ``autopublicacoes`` (a list of publication dicts).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
    except Exception as e:
        _logger.error("Failed to download %s: %s", url, e)
        return None

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        _logger.error("Bad ZIP file %s: %s", url, e)
        return None

    json_files = [n for n in zf.namelist() if n.endswith(".json")]
    if not json_files:
        _logger.warning("No JSON found in ZIP %s", url)
        return None

    try:
        # The ZIP contains a single JSON file
        content = json.loads(zf.read(json_files[0]))
        return content
    except (json.JSONDecodeError, KeyError) as e:
        _logger.error("Failed to parse JSON from %s: %s", url, e)
        return None


def download_month(domsc_id: str, *, progress_cb=None) -> list[dict]:
    """Download all resources for a DOM-SC monthly dataset.

    Returns the concatenated list of all ``autopublicacoes`` records
    whose category is in ``PROCUREMENT_CATEGORIES``.
    """
    pkg = get_package(domsc_id)
    if not pkg:
        _logger.error("Could not fetch package %s", domsc_id)
        return []

    resources = get_package_resources(pkg)
    if not resources:
        _logger.warning("No resources for %s", domsc_id)
        return []

    month_label = classify_month(domsc_id) or domsc_id
    total = len(resources)
    all_publications: list[dict] = []

    for idx, r in enumerate(resources):
        if progress_cb:
            progress_cb(month_label, idx + 1, total)
        time.sleep(REQUEST_DELAY)

        content = download_resource(r["url"])
        if not content:
            continue

        autopub = content.get("autopublicacoes") or []
        if not isinstance(autopub, list):
            continue

        # Filter to procurement-relevant categories
        for item in autopub:
            if item.get("categoria") in PROCUREMENT_CATEGORIES:
                all_publications.append(item)

    _logger.info(
        "Downloaded %s: %d procurement publications from %d resources",
        domsc_id,
        len(all_publications),
        total,
    )
    return all_publications


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Normalize an entity name for matching.

    Delegates to ``scripts.lib.name_normalizer.normalize_name`` for
    consistency with the rest of the codebase (accents removed,
    apostrophes/spaces normalized).
    """
    if not name:
        return ""
    from scripts.lib.name_normalizer import normalize_name

    return normalize_name(name)


def extract_entities(publications: list[dict]) -> dict[str, dict]:
    """Extract unique entities from a list of publications.

    Returns a dict keyed by ``(normalized_name, municipio)`` tuple
    (as a single string key), with metadata:
        - raw_name: original entidade value
        - municipio: municipio field
        - count: number of publications for this entity
        - categories: set of categories seen
        - first_seen: earliest date
        - last_seen: latest date
    """
    entities: dict[str, dict] = {}

    for pub in publications:
        raw_name = (pub.get("entidade") or "").strip()
        municipio = (pub.get("municipio") or "").strip()
        data = (pub.get("data") or "")[:10]
        categoria = pub.get("categoria") or ""

        norm_name = _normalize_name(raw_name)
        if not norm_name:
            continue

        key = f"{norm_name}||{municipio}"

        if key not in entities:
            entities[key] = {
                "raw_name": raw_name,
                "norm_name": norm_name,
                "municipio": municipio,
                "count": 0,
                "categories": set(),
                "first_seen": data,
                "last_seen": data,
            }

        entry = entities[key]
        entry["count"] += 1
        entry["categories"].add(categoria)
        if data and (data < entry["first_seen"]):
            entry["first_seen"] = data
        if data and (data > entry["last_seen"]):
            entry["last_seen"] = data

    # Convert sets to lists for serialization
    for entry in entities.values():
        entry["categories"] = sorted(entry["categories"])

    return entities


# ---------------------------------------------------------------------------
# Name alias generation for fuzzy matching
# ---------------------------------------------------------------------------


def _generate_name_aliases(norm_name: str) -> list[str]:
    """Generate alternate normalized names for common DOM-SC patterns.

    Uses the library's ``normalize_name`` to ensure aliases match the
    normalization used in ``sc_public_entities`` (accents removed,
    apostrophes/spaces normalized, etc.).

    Handles:
    1. "PREFEITURA MUNICIPAL DE X" -> "MUNICIPIO DE X"
    2. "PREFEITURA DE X" -> "MUNICIPIO DE X"
    3. "CAMARA DE VEREADORES DE X" -> "X CAMARA DE VEREADORES"
    4. "X CAMARA DE VEREADORES" -> "CAMARA DE VEREADORES DE X"
    5. "CAMARA MUNICIPAL DE X" -> "X CAMARA MUNICIPAL"
    6. "CAMARA MUNICIPAL DE VEREADORES DE X" -> "X CAMARA MUNICIPAL DE VEREADORES"

    Returns a list of zero or more alias normalized strings.
    """
    from scripts.lib.name_normalizer import normalize_name

    aliases: list[str] = []

    # Pattern 1: "PREFEITURA MUNICIPAL DE X" -> "MUNICIPIO DE X"
    _prefix_prefeitura = "PREFEITURA MUNICIPAL DE "
    if norm_name.startswith(_prefix_prefeitura):
        city = norm_name[len(_prefix_prefeitura) :]
        # Use library normalizer to handle accents, apostrophes
        aliases.append(normalize_name(f"MUNICIPIO DE {city}"))

    # Pattern 2: "PREFEITURA DE X" -> "MUNICIPIO DE X"
    _prefix_prefeitura_short = "PREFEITURA DE "
    if norm_name.startswith(_prefix_prefeitura_short):
        city = norm_name[len(_prefix_prefeitura_short) :]
        aliases.append(normalize_name(f"MUNICIPIO DE {city}"))

    # Pattern 3: "CAMARA DE VEREADORES DE X" -> "X CAMARA DE VEREADORES"
    _prefix_camara_vereadores = "CAMARA DE VEREADORES DE "
    if norm_name.startswith(_prefix_camara_vereadores):
        city = norm_name[len(_prefix_camara_vereadores) :]
        aliases.append(normalize_name(f"{city} CAMARA DE VEREADORES"))

    # Pattern 4: "X CAMARA DE VEREADORES" -> "CAMARA DE VEREADORES DE X"
    _suffix_camara_vereadores = " CAMARA DE VEREADORES"
    if norm_name.endswith(_suffix_camara_vereadores):
        city = norm_name[: -len(_suffix_camara_vereadores)]
        aliases.append(normalize_name(f"CAMARA DE VEREADORES DE {city}"))

    # Pattern 5: "CAMARA MUNICIPAL DE X" -> "X CAMARA MUNICIPAL"
    _prefix_camara_municipal = "CAMARA MUNICIPAL DE "
    if norm_name.startswith(_prefix_camara_municipal):
        city = norm_name[len(_prefix_camara_municipal) :]
        aliases.append(normalize_name(f"{city} CAMARA MUNICIPAL"))

    # Pattern 6: "CAMARA MUNICIPAL DE VEREADORES DE X" -> "X CAMARA MUNICIPAL DE VEREADORES"
    _prefix_camara_municipal_vereadores = "CAMARA MUNICIPAL DE VEREADORES DE "
    if norm_name.startswith(_prefix_camara_municipal_vereadores):
        city = norm_name[len(_prefix_camara_municipal_vereadores) :]
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
# Entity matching
# ---------------------------------------------------------------------------


def _load_db_entities(conn, within_200km_only: bool = True) -> list[dict]:
    """Load all active SC public entities from DB."""
    cur = conn.cursor()
    sql = (
        "SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, "
        "natureza_juridica, raio_200km "
        "FROM sc_public_entities WHERE is_active = TRUE"
    )
    if within_200km_only:
        sql += " AND raio_200km = TRUE"
    sql += " ORDER BY id"
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    entities = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return entities


def match_entities(
    ciga_entities: dict[str, dict],
    db_entities: list[dict],
) -> dict[str, dict]:
    """Match CIGA CKAN entities against DB entities by normalized name.

    Matching strategy (cascade):
        1. Exact normalized name + municipio match (high confidence)
        2. Exact normalized name match without municipio (high confidence)
        3. Fuzzy name match within same municipio (medium confidence)
        4. Fuzzy name match across all entities (low confidence)

    Returns the input entities dict augmented with:
        - matched_entity_id: int | None
        - match_method: str
        - match_confidence: str
        - match_score: float
    """
    # Build DB entity indexes
    from scripts.lib.name_normalizer import normalize_name

    # Index by (normalized_name, municipio_upper)
    name_muni_index: dict[tuple[str, str], dict] = {}
    # Index by normalized_name (any municipio)
    name_index: dict[str, list[dict]] = {}

    for e in db_entities:
        norm = normalize_name(e.get("razao_social", ""))
        if not norm:
            continue
        # Store in name index
        name_index.setdefault(norm, []).append(e)
        # Store in name+municipio index
        mun = (e.get("municipio") or "").upper().strip()
        if mun:
            name_muni_index[(norm, mun)] = e

    # Fuzzy matching
    def _fuzz_ratio(a: str, b: str) -> float:
        try:
            from rapidfuzz import fuzz as _rapidfuzz

            return _rapidfuzz.ratio(a, b) / 100.0
        except ImportError:
            from difflib import SequenceMatcher

            return SequenceMatcher(None, a, b).ratio()

    fuzzy_threshold = 0.85

    matched_count = 0
    unmatched_count = 0

    for key, entry in ciga_entities.items():
        norm = entry["norm_name"]
        municipio = entry["municipio"].upper().strip()
        matched_entity = None
        match_method = "unmatched"
        match_score = 0.0
        match_confidence = None

        # --- Level 1: Exact name + municipio ---
        if not matched_entity and municipio:
            if (norm, municipio) in name_muni_index:
                matched_entity = name_muni_index[(norm, municipio)]
                match_method = "name_muni"
                match_score = 1.0
                match_confidence = "high"

        # --- Level 2: Exact name only ---
        if not matched_entity and norm in name_index:
            candidates = name_index[norm]
            if len(candidates) == 1:
                matched_entity = candidates[0]
                match_method = "name_only"
                match_score = 1.0
                match_confidence = "high"
            elif municipio:
                # Multiple candidates with same name, try municipio match
                for c in candidates:
                    c_mun = (c.get("municipio") or "").upper().strip()
                    if c_mun == municipio:
                        matched_entity = c
                        match_method = "name_only"
                        match_score = 1.0
                        match_confidence = "high"
                        break
                if not matched_entity:
                    # Take the first one
                    matched_entity = candidates[0]
                    match_method = "name_only"
                    match_score = 1.0
                    match_confidence = "medium"

        # --- Level 2b: Alias exact match ---
        # Check if generated aliases hit the name index directly
        if not matched_entity:
            aliases = _generate_name_aliases(norm)
            for alias in aliases:
                if alias in name_index:
                    candidates = name_index[alias]
                    if len(candidates) == 1:
                        matched_entity = candidates[0]
                        match_method = "alias"
                        match_score = 1.0
                        match_confidence = "high"
                    elif municipio:
                        for c in candidates:
                            c_mun = (c.get("municipio") or "").upper().strip()
                            if c_mun == municipio:
                                matched_entity = c
                                match_method = "alias"
                                match_score = 1.0
                                match_confidence = "high"
                                break
                    if matched_entity:
                        break

        # --- Level 3: Fuzzy within same municipio ---
        if not matched_entity:
            # Filter candidates by municipio
            candidates = [e for e in db_entities if (e.get("municipio") or "").upper().strip() == municipio]
            if not candidates:
                candidates = db_entities  # fallback to all

            best_score = 0.0
            best_entity = None
            for e in candidates:
                e_norm = normalize_name(e.get("razao_social", ""))
                if not e_norm:
                    continue
                score = _fuzz_ratio(norm, e_norm)
                if score > best_score:
                    best_score = score
                    best_entity = e

            if best_score >= fuzzy_threshold and best_entity:
                matched_entity = best_entity
                match_method = "fuzzy"
                match_score = round(best_score, 3)
                match_confidence = "high" if best_score >= 0.95 else "medium"

        # --- Annotate ---
        if matched_entity:
            entry["matched_entity_id"] = matched_entity["id"]
            entry["matched_cnpj_8"] = matched_entity.get("cnpj_8")
            entry["matched_razao_social"] = matched_entity["razao_social"]
            entry["matched_municipio"] = matched_entity.get("municipio")
            entry["match_method"] = match_method
            entry["match_score"] = match_score
            entry["match_confidence"] = match_confidence
            matched_count += 1
        else:
            entry["matched_entity_id"] = None
            entry["match_method"] = match_method
            entry["match_score"] = match_score
            entry["match_confidence"] = None
            unmatched_count += 1

    _logger.info(
        "Entity matching: %d matched, %d unmatched (threshold=%.2f)",
        matched_count,
        unmatched_count,
        fuzzy_threshold,
    )
    return ciga_entities


# ---------------------------------------------------------------------------
# Coverage upsert
# ---------------------------------------------------------------------------


def update_coverage(conn, matched_entities: dict[str, dict], source: str) -> dict:
    """Insert matched entities into entity_coverage.

    Args:
        conn: DB connection.
        matched_entities: Entities dict from match_entities().
        source: Source tag (e.g. 'ciga_ckan').

    Returns:
        Stats dict.
    """
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    errors = 0

    for key, entry in matched_entities.items():
        entity_id = entry.get("matched_entity_id")
        if entity_id is None:
            skipped += 1
            continue

        try:
            # Upsert: INSERT ... ON CONFLICT DO UPDATE
            cur.execute(
                """INSERT INTO entity_coverage
                   (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
                   VALUES (%s, %s, %s, 1, TRUE, TRUE)
                   ON CONFLICT (entity_id, source)
                   DO UPDATE SET
                       last_seen_at = GREATEST(entity_coverage.last_seen_at, EXCLUDED.last_seen_at),
                       total_bids = entity_coverage.total_bids + 1,
                       is_covered = TRUE
                """,
                (entity_id, source, entry.get("last_seen") or datetime.now(UTC).strftime("%Y-%m-%d")),
            )
            inserted += 1
        except Exception as e:
            _logger.error("Failed to upsert entity_id=%s: %s", entity_id, e)
            errors += 1

    conn.commit()
    cur.close()

    _logger.info(
        "Coverage upsert: %d inserted, %d skipped, %d errors",
        inserted,
        skipped,
        errors,
    )
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def get_existing_coverage(conn, source: str) -> set[int]:
    """Get set of entity_ids already covered by this source."""
    cur = conn.cursor()
    cur.execute(
        "SELECT entity_id FROM entity_coverage WHERE source = %s",
        (source,),
    )
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    return existing


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def report_coverage_impact(conn, source: str) -> dict:
    """Measure coverage impact of a source."""
    cur = conn.cursor()

    # Total entities within 200km
    cur.execute("SELECT COUNT(*) FROM sc_public_entities WHERE is_active = TRUE AND raio_200km = TRUE")
    total_200km = cur.fetchone()[0]

    # Entities covered by this source
    cur.execute(
        """SELECT COUNT(DISTINCT ec.entity_id)
           FROM entity_coverage ec
           JOIN sc_public_entities e ON e.id = ec.entity_id
           WHERE ec.source = %s AND e.is_active = TRUE AND e.raio_200km = TRUE
              AND ec.is_covered = TRUE""",
        (source,),
    )
    source_covered = cur.fetchone()[0]

    # Total covered (any source)
    cur.execute(
        """SELECT COUNT(DISTINCT entity_id)
           FROM entity_coverage ec
           JOIN sc_public_entities e ON e.id = ec.entity_id
           WHERE e.is_active = TRUE AND e.raio_200km = TRUE AND ec.is_covered = TRUE"""
    )
    total_covered = cur.fetchone()[0]

    # Newly covered (only this source)
    cur.execute(
        """SELECT COUNT(DISTINCT ec.entity_id)
           FROM entity_coverage ec
           JOIN sc_public_entities e ON e.id = ec.entity_id
           WHERE ec.source = %s AND e.is_active = TRUE AND e.raio_200km = TRUE
              AND ec.is_covered = TRUE
              AND ec.entity_id NOT IN (
                  SELECT entity_id FROM entity_coverage
                  WHERE source != %s AND is_covered = TRUE
              )""",
        (source, source),
    )
    exclusive_covered = cur.fetchone()[0]

    # Uncovered remaining
    total_uncovered = total_200km - total_covered

    cur.close()

    return {
        "total_entities_200km": total_200km,
        "source_covered": source_covered,
        "total_covered": total_covered,
        "exclusive_covered": exclusive_covered,
        "total_uncovered": total_uncovered,
        "coverage_pct": round(total_covered / total_200km * 100, 1) if total_200km else 0,
        "source_pct": round(source_covered / total_200km * 100, 1) if total_200km else 0,
    }


# ---------------------------------------------------------------------------
# Module interface (monitor.py compatible)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Monitor.py-compatible crawl entry point.

    Downloads the latest month of DOM-SC data and returns procurement
    publications as raw dicts.
    """
    months = list_domsc_months()
    if not months:
        _logger.error("No DOM-SC datasets found on CKAN")
        return []

    if mode == "incremental":
        # Fetch only the latest month
        target_months = [months[-1]]
    else:
        # Fetch all
        target_months = months

    all_publications: list[dict] = []
    for m in target_months:
        _logger.info("Crawling %s", m)
        pubs = download_month(m)
        all_publications.extend(pubs)

    _logger.info("Total procurement publications: %d", len(all_publications))
    return all_publications


def transform(records: list[dict]) -> list[dict]:
    """Monitor.py-compatible transform entry point.

    CIGA CKAN data is not directly transformable to pncp_raw_bids schema
    (it has no CNPJ, no structured bid data). Returns an empty list
    to signal that bid-level import is not supported yet.
    """
    # Future: could parse structured metadata from the publication text
    _logger.warning("CIGA CKAN transform() not implemented — entity-coverage only")
    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _progress_bar(month: str, current: int, total: int):
    """Simple progress display."""
    pct = current / total * 100 if total else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total else 0
    bar = "=" * filled + "-" * (bar_len - filled)
    print(f"\r  [{bar}] {month} {current}/{total} ({pct:.0f}%)", end="")
    if current == total:
        print()


def run_month(month_id: str, source: str, within_200km: bool) -> dict:
    """Run the full pipeline for a single DOM-SC month.

    Returns stats dict.
    """
    import psycopg2

    print(f"\n  Downloading {month_id}...")
    pubs = download_month(month_id, progress_cb=_progress_bar)
    print(f"  Procurement publications: {len(pubs)}")

    if not pubs:
        print("  No procurement data found, skipping.")
        return {"month": month_id, "status": "skipped", "publications": 0, "entities": 0, "matched": 0, "inserted": 0}

    # Extract entities
    entities = extract_entities(pubs)
    print(f"  Unique entities: {len(entities)}")

    # Connect to DB and match
    conn = psycopg2.connect(DEFAULT_DSN)
    try:
        db_entities = _load_db_entities(conn, within_200km_only=within_200km)
        print(f"  DB entities loaded: {len(db_entities)}")

        matched = match_entities(entities, db_entities)
        matched_count = sum(1 for e in matched.values() if e["matched_entity_id"] is not None)
        print(f"  Matched: {matched_count}/{len(matched)}")

        # Update coverage
        result = update_coverage(conn, matched, source)
        print(f"  Coverage upserted: {result['inserted']} new, {result['skipped']} skipped")

        # Report current impact
        impact = report_coverage_impact(conn, source)
        print(f"\n  Coverage impact ({source}):")
        print(f"    Source-covered entities: {impact['source_covered']}")
        print(f"    Exclusive to this source: {impact['exclusive_covered']}")
        print(
            f"    Total covered: {impact['total_covered']}/{impact['total_entities_200km']} ({impact['coverage_pct']}%)"
        )
        print(f"    Still uncovered: {impact['total_uncovered']}")

        return {
            "month": month_id,
            "status": "ok",
            "publications": len(pubs),
            "entities": len(entities),
            "matched": matched_count,
            "inserted": result["inserted"],
        }
    finally:
        conn.close()


def run_reports(source: str):
    """Print coverage reports."""
    import psycopg2

    conn = psycopg2.connect(DEFAULT_DSN)
    try:
        # Available months
        months = list_domsc_months()
        print(f"\n  DOM-SC datasets available: {len(months)}")
        print(f"  Range: {months[0]} to {months[-1]}")

        # Coverage impact
        impact = report_coverage_impact(conn, source)
        print(f"\n  Coverage impact ({source}):")
        print(f"    Source-covered entities: {impact['source_covered']}")
        print(f"    Exclusive to this source: {impact['exclusive_covered']}")
        print(
            f"    Total covered: {impact['total_covered']}/{impact['total_entities_200km']} ({impact['coverage_pct']}%)"
        )
        print(f"    Still uncovered: {impact['total_uncovered']}")

        # List uncovered
        cur = conn.cursor()
        cur.execute(
            """SELECT e.razao_social, e.municipio, e.cnpj_8, e.natureza_juridica
               FROM sc_public_entities e
               WHERE e.is_active = TRUE AND e.raio_200km = TRUE
                 AND e.id NOT IN (
                     SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE
                 )
               ORDER BY e.municipio, e.razao_social"""
        )
        uncovered = cur.fetchall()
        if uncovered:
            print(f"\n  Uncovered entities ({len(uncovered)}):")
            for r in uncovered[:10]:
                print(f"    - {r[0][:60]:60s} | {r[1] or 'N/A'}")
            if len(uncovered) > 10:
                print(f"    ... and {len(uncovered) - 10} more")
        cur.close()
    finally:
        conn.close()


def parse_args():
    p = argparse.ArgumentParser(description="CIGA CKAN DOM-SC Coverage Crawler")
    p.add_argument("--month", help="Specific month: MM-YYYY (e.g. 12-2025)")
    p.add_argument("--all-months", action="store_true", help="Crawl all available months")
    p.add_argument("--source", default="ciga_ckan", help="Source tag for entity_coverage")
    p.add_argument("--report", action="store_true", help="Print coverage report and exit")
    p.add_argument(
        "--within-200km", action="store_true", default=True, help="Only match entities within 200km (default: True)"
    )
    p.add_argument("--list", action="store_true", help="List available DOM-SC months and exit")
    return p.parse_args()


def main():
    args = parse_args()
    source = args.source

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 72)
    print("  CIGA CKAN Crawler — DOM-SC Entity Coverage")
    print("  Source: https://dados.ciga.sc.gov.br/")
    print("=" * 72)

    # List mode
    if args.list:
        months = list_domsc_months()
        print(f"\n  DOM-SC datasets: {len(months)}")
        for m in months:
            label = classify_month(m) or "?"
            print(f"    {m:45s} ({label})")
        return 0

    # Report mode
    if args.report:
        run_reports(source)
        return 0

    # Run mode
    months = list_domsc_months()
    if not months:
        print("  ERROR: No DOM-SC datasets found.")
        return 1

    if args.month:
        target = f"domsc-publicacoes-de-{args.month}"
        if target not in months:
            print(f"  ERROR: Month '{target}' not found. Use --list to see available months.")
            return 1
        run_month(target, source, args.within_200km)
    elif args.all_months:
        results = []
        for m in months:
            result = run_month(m, source, args.within_200km)
            results.append(result)
            print()

        # Summary
        total_pubs = sum(r.get("publications", 0) for r in results)
        total_matched = sum(r.get("matched", 0) for r in results)
        total_inserted = sum(r.get("inserted", 0) for r in results)
        failed = [r for r in results if r.get("status") == "failed"]
        print("─" * 50)
        print(f"  TOTAL: {len(months)} months")
        print(f"  Publications: {total_pubs}")
        print(f"  Entity matches: {total_matched}")
        print(f"  Coverage upserts: {total_inserted}")
        if failed:
            print(f"  Failed: {len(failed)} months")
            for f in failed:
                print(f"    - {f['month']}")
    else:
        # Default: run latest month
        latest = months[-1]
        label = classify_month(latest) or "?"
        print(f"\n  Running latest: {latest} ({label})")
        run_month(latest, source, args.within_200km)

    # Final coverage report
    import psycopg2

    conn = psycopg2.connect(DEFAULT_DSN)
    try:
        impact = report_coverage_impact(conn, source)
        print(f"\n{'=' * 50}")
        print(f"  FINAL COVERAGE: {impact['coverage_pct']}%")
        print(f"  ({impact['total_covered']}/{impact['total_entities_200km']})")
        print(f"  {source}: {impact['source_covered']} entities (exclusive: {impact['exclusive_covered']})")
        print(f"  Still uncovered: {impact['total_uncovered']}")
        print(f"{'=' * 50}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
