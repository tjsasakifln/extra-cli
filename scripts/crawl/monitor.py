#!/usr/bin/env python3
"""Multi-Source Coverage Monitor — Extra Consultoria.

Orquestrador de coleta multi-source para monitoramento de 100% dos 2.085
órgãos públicos de SC. Cada source é um módulo de crawler independente.

Sources:
    pncp        PNCP API (federal + adesão voluntária)
    dom_sc      DOM-SC (Diário Oficial dos Municípios de SC)
    pcp         PCP v2 (Portal de Compras Públicas)
    compras_gov ComprasGov v3 (compras federais)
    sc_compras  SC Compras

Pipeline por source:
    Crawl → Transform → Entity Match → Upsert → Coverage Update

Usage:
    python scripts/crawl/monitor.py --source pncp --mode full
    python scripts/crawl/monitor.py --source dom_sc --mode full
    python scripts/crawl/monitor.py --source all --mode incremental
    python scripts/crawl/monitor.py --report-coverage
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SOURCES loaded from central registry — single source of truth
from scripts.crawl.registry import iter_sources, lookup as _registry_lookup, resolve_name as _registry_resolve

SOURCES = [s.name for s in iter_sources()]

from config.settings import DEFAULT_DSN  # single source of truth (TD-3.2)

COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_conn():
    import psycopg2

    return psycopg2.connect(DEFAULT_DSN)


def _load_entities(conn, within_200km_only: bool = False) -> list[dict]:
    """Load all active SC public entities."""
    cur = conn.cursor()
    sql = "SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica, raio_200km FROM sc_public_entities WHERE is_active = TRUE"
    if within_200km_only:
        sql += " AND raio_200km = TRUE"
    sql += " ORDER BY id"
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    entities = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return entities


def _match_entity(orgao_cnpj: str, entities: list[dict]) -> dict | None:
    """Match an orgao_cnpj (14 digits) against entity list (cnpj_8 base)."""
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


def _start_ingestion_run(conn, source: str, mode: str = "incremental") -> int:
    """Insert a new ingestion_runs row, returning its id.

    Auto-detects whether the schema has crawl_batch_id/run_type (v2)
    or the simpler v1 schema, and inserts accordingly.

    Maps non-standard modes (backfill, selenium, detect, etc.) to 'full'
    for the run_type column in v2 schemas.
    """
    import json as _json
    import uuid

    # Map mode to valid run_type for DB constraint compatibility
    _VALID_RUN_TYPES = {"full", "incremental", "dry-run"}
    db_run_type = mode if mode in _VALID_RUN_TYPES else "full"

    cur = conn.cursor()

    # Detect schema version by checking if crawl_batch_id column exists
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'ingestion_runs' AND column_name = 'crawl_batch_id')"
    )
    has_v2 = cur.fetchone()[0]

    if has_v2:
        cur.execute(
            "INSERT INTO ingestion_runs (source, status, crawl_batch_id, run_type, metadata) "
            "VALUES (%s, 'running', %s, %s, %s) RETURNING id",
            (source, str(uuid.uuid4()), db_run_type, _json.dumps({"mode": mode})),
        )
    else:
        # v1 schema: simpler table without run_type/crawl_batch_id
        cur.execute(
            "INSERT INTO ingestion_runs (source, status) VALUES (%s, 'running') RETURNING id",
            (source,),
        )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return run_id


def _finish_ingestion_run(
    conn, run_id: int, fetched: int, upserted: int, covered: int, status: str = "completed", error: str = ""
):
    """Update ingestion_runs row at end of crawl. Auto-detects schema version."""
    cur = conn.cursor()

    # Detect schema version
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'ingestion_runs' AND column_name = 'crawl_batch_id')"
    )
    has_v2 = cur.fetchone()[0]

    if has_v2:
        cur.execute(
            """UPDATE ingestion_runs
               SET completed_at = NOW(), total_fetched = %s, inserted = %s,
                   updated = %s, status = %s,
                   errors = CASE WHEN %s <> '' THEN 1 ELSE 0 END
               WHERE id = %s""",
            (fetched, upserted, 0, status, error or "", run_id),
        )
    else:
        # v1 schema: use records_fetched, records_upserted, entities_covered
        cur.execute(
            """UPDATE ingestion_runs
               SET finished_at = NOW(), records_fetched = %s,
                   records_upserted = %s, entities_covered = %s,
                   status = %s, error_message = %s
               WHERE id = %s""",
            (fetched, upserted, covered, status, error or "", run_id),
        )
    conn.commit()
    cur.close()


def _update_matched_entity_full(
    conn,
    pncp_id: str,
    entity_id: int | None,
    match_method: str | None = None,
    match_score: float | None = None,
    match_confidence: str | None = None,
):
    """Set matched_entity_id + match metadata on a bid record."""
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


def _match_entities_cascade(conn, source: str, entities: list[dict]) -> dict:
    """3-level cascade entity matching for a source.

    Strategies (applied in order per bid):
        Level 1 — CNPJ exact match (8-digit base)          [confidence: high]
        Level 2 — Normalized name + municipio constraint   [confidence: high]
        Level 3 — Fuzzy matching (difflib / rapidfuzz)     [confidence: high|medium|low]

    Logs ``match_method``, ``match_score``, ``match_confidence`` to the bid row
    for every bid (including unmatched).

    Args:
        conn: Database connection.
        source: Data source tag (``pncp``, ``dom_sc``, etc.).
        entities: List of entity dicts from ``_load_entities()``.

    Returns:
        Stats dict with keys:
        - ``cnpj``: count matched via Level 1
        - ``name_normalized``: count matched via Level 2
        - ``fuzzy``: count matched via Level 3
        - ``unmatched``: count still unmatched
        - ``total``: total bids processed
    """
    ENTITY_MATCH_FUZZY_THRESHOLD = float(os.getenv("ENTITY_MATCH_FUZZY_THRESHOLD", "0.85"))

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
        return {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 0}

    # Step 2 — build entity lookup structures
    from scripts.lib.name_normalizer import normalize_name

    # CNPJ index: cnpj_8 -> entity
    cnpj_index: dict[str, dict] = {}
    for e in entities:
        cnpj_8 = e.get("cnpj_8")
        if cnpj_8:
            cnpj_index[cnpj_8] = e

    # Name indexes
    name_exact_index: dict[str, dict] = {}  # normalized_name -> entity
    name_muni_index: dict[tuple[str, str], dict] = {}  # (norm_name, codigo_ibge) -> entity
    all_entities_norm: list[dict] = []  # for fuzzy matching

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

        _fuzz_ratio = lambda a, b: _rapidfuzz.ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher

        _fuzz_ratio = lambda a, b: SequenceMatcher(None, a, b).ratio()

    # Step 4 — cascade matching per bid
    stats = {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0}

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

                # Filter candidates by IBGE code if available (avoids cross-municipio)
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

                if best_score >= ENTITY_MATCH_FUZZY_THRESHOLD and best_entity:
                    matched_entity = best_entity
                    match_method = "fuzzy"
                    match_score = round(best_score, 3)
                    if best_score >= 0.95:
                        match_confidence = "high"
                    elif best_score >= ENTITY_MATCH_FUZZY_THRESHOLD:
                        match_confidence = "medium"
                    else:
                        match_confidence = "low"

        # ------------------------------------------------------------------
        # Update bid with result
        # ------------------------------------------------------------------
        if matched_entity:
            _update_matched_entity_full(
                conn,
                pncp_id,
                matched_entity["id"],
                match_method,
                match_score,
                match_confidence,
            )
            stats[match_method] = stats[match_method] + 1  # type: ignore[literal-required]
        else:
            # Mark as unmatched with metadata (helps v_unmatched_bids analysis)
            _update_matched_entity_full(
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
    return stats


# ---------------------------------------------------------------------------
# Coverage Reporting
# ---------------------------------------------------------------------------


def report_coverage(conn) -> dict:
    """Generate coverage report for all entities across all sources."""
    cur = conn.cursor()

    # Overall coverage
    cur.execute(
        """SELECT
            e.raio_200km,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) AS covered,
            COUNT(DISTINCT CASE WHEN NOT ec.is_covered OR ec.is_covered IS NULL THEN e.id END) AS uncovered
         FROM sc_public_entities e
         LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
         WHERE e.is_active = TRUE
         GROUP BY e.raio_200km
         ORDER BY e.raio_200km DESC"""
    )
    rows = cur.fetchall()

    result = {"groups": [], "total_entities": 0, "total_covered": 0, "total_uncovered": 0}
    for raio, total, covered, uncovered in rows:
        group = {
            "within_200km": raio,
            "total": total,
            "covered": covered or 0,
            "uncovered": uncovered or 0,
            "pct": round((covered or 0) / total * 100, 1) if total > 0 else 0,
        }
        result["groups"].append(group)
        result["total_entities"] += total
        result["total_covered"] += covered or 0
        result["total_uncovered"] += uncovered or 0

    result["pct"] = (
        round(result["total_covered"] / result["total_entities"] * 100, 1) if result["total_entities"] > 0 else 0
    )

    # Per-source breakdown
    cur.execute(
        """SELECT source, COUNT(*) AS entity_count, COUNT(*) FILTER (WHERE is_covered) AS covered
           FROM entity_coverage
           WHERE within_200km = TRUE
           GROUP BY source
           ORDER BY source"""
    )
    result["by_source"] = [{"source": r[0], "entities": r[1], "covered": r[2]} for r in cur.fetchall()]

    # Uncovered entities within 200km (critical gap)
    cur.execute(
        """SELECT e.razao_social, e.cnpj_8, e.municipio, e.natureza_juridica
           FROM sc_public_entities e
           WHERE e.is_active = TRUE
             AND e.raio_200km = TRUE
             AND e.id NOT IN (
                 SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE
             )
           ORDER BY e.municipio, e.razao_social"""
    )
    result["uncovered_entities_200km"] = [
        {"razao_social": r[0], "cnpj_8": r[1], "municipio": r[2], "natureza": r[3]} for r in cur.fetchall()
    ]

    cur.close()
    return result


def print_coverage_report(result: dict) -> None:
    """Pretty-print coverage report to terminal."""
    print("\n" + "=" * 72)
    print("  COBERTURA DE MONITORAMENTO — Extra Construtora")
    print("=" * 72)

    for g in result["groups"]:
        label = "Dentro do raio 200km" if g["within_200km"] else "Fora do raio 200km"
        print(f"\n  📍 {label}")
        print(f"     Total: {g['total']} entidades")
        print(f"     Cobertas: {g['covered']} ({g['pct']}%)")
        print(f"     Descobertas: {g['uncovered']}")

    print(
        f"\n  📊 TOTAL: {result['total_entities']} entidades | "
        f"{result['total_covered']} cobertas ({result['pct']}%) | "
        f"{result['total_uncovered']} descobertas"
    )

    print("\n  📡 Por fonte (raio 200km):")
    for s in result["by_source"]:
        pct = round(s["covered"] / s["entities"] * 100, 1) if s["entities"] > 0 else 0
        print(f"     {s['source']:15s}: {s['covered']:4d}/{s['entities']:4d} ({pct}%)")

    uncovered = result.get("uncovered_entities_200km", [])
    if uncovered:
        print(f"\n  🚨 ENTIDADES SEM COBERTURA (raio 200km): {len(uncovered)}")
        for e in uncovered[:20]:
            print(f"     • {e['razao_social'][:50]:50s} | {e['municipio'] or 'N/A'}")
        if len(uncovered) > 20:
            print(f"     ... e mais {len(uncovered) - 20} entidades")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Crawl orchestration
# ---------------------------------------------------------------------------


def crawl_source(
    source: str,
    entities: list[dict],
    mode: str = "full",
    date_from: str | None = None,
    date_to: str | None = None,
    target: str | None = None,
    limit: int | None = None,
) -> CrawlerResult:
    """Run crawl for a specific source, match entities, return CrawlerResult.

    Each source module is expected to provide:
        crawl(mode) -> list[dict]  # raw records from source
        transform(records) -> list[dict]  # normalized to canonical schema

    Sources may optionally declare:
        UPSERT_FUNCTION: str  # RPC name (default: upsert_pncp_raw_bids)
        SOURCE_PURPOSE: str   # "bids" | "coverage_only" | "hybrid"

    Returns:
        CrawlerResult with all counters and status populated.
    """
    from datetime import datetime, timezone

    from scripts.crawl.credential_validator import validate_source_credentials
    from scripts.crawl.ingestion._base.crawler import CrawlRequest, CrawlerResult, determine_status

    started_at = datetime.now(timezone.utc)
    result = CrawlerResult(source=source)

    conn = _get_conn()
    run_id = _start_ingestion_run(conn, source, mode)

    try:
        # ── Load crawler module ───────────────────────────────────────
        crawler = _load_crawler(source)
        if crawler is None:
            error = f"Crawler not implemented: {source}"
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "failed", error)
            conn.close()
            result.status = "failed"
            result.error_code = "crawler_not_implemented"
            result.error_message = error
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(timezone.utc).isoformat()
            return result

        # ── Credential validation ──────────────────────────────────────
        creds_ok, missing_creds = validate_source_credentials(source)
        if not creds_ok:
            msg = f"Missing credentials: {', '.join(missing_creds)}"
            result.dependencies_missing = missing_creds
            result.warnings.append(msg)
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "skipped", msg)
            conn.close()
            result.status = "skipped"
            result.error_code = "missing_credentials"
            result.error_message = msg
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(timezone.utc).isoformat()
            return result

        # ── Phase 1: Crawl ─────────────────────────────────────────────
        print(f"  🔍 Crawling {source} ({mode})...")

        # Build CrawlRequest with all parameters
        from datetime import date as _date
        crawl_req = CrawlRequest(
            mode=mode,
            date_from=_date.fromisoformat(date_from) if date_from else None,
            date_to=_date.fromisoformat(date_to) if date_to else None,
            target=target,
            limit=limit,
        )

        # Accept both CrawlRequest and plain str (backward-compatible)
        try:
            raw_records = crawler.crawl(crawl_req)
        except TypeError:
            # Fallback: crawler only accepts mode: str
            raw_records = crawler.crawl(mode)
        result.fetched = len(raw_records)
        print(f"     Fetched: {result.fetched} records")

        if not raw_records:
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "empty")
            conn.close()
            result.status = "empty"
            result.error_code = "empty_result"
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(timezone.utc).isoformat()
            return result

        # ── Phase 2: Transform ─────────────────────────────────────────
        records = crawler.transform(raw_records)
        result.transformed = len(records)
        records = [{**r, "source": source} for r in records]

        source_purpose = getattr(crawler, "SOURCE_PURPOSE", "bids")

        # Count entity_coverage rows for this source (coverage evidence)
        entities_covered_count: int | None = None
        if source_purpose == "coverage_only":
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM entity_coverage WHERE source = %s AND is_covered = TRUE",
                (source,),
            )
            entities_covered_count = cur.fetchone()[0] or 0
            cur.close()
            result.new_entities_covered = entities_covered_count

        # Detect degraded: crawl returned data but transform discarded all
        if result.fetched > 0 and result.transformed == 0:
            if source_purpose == "coverage_only":
                if entities_covered_count and entities_covered_count > 0:
                    print(f"     ⓘ  Source is coverage-only — {entities_covered_count} entities covered")
                else:
                    msg = (
                        f"coverage-only source fetched {result.fetched} records "
                        f"but entity_coverage has 0 covered rows. No evidence of coverage update."
                    )
                    result.warnings.append(msg)
                    _logger.warning(msg)
            else:
                msg = (
                    f"crawl() returned {result.fetched} records but transform() "
                    f"produced 0. This may indicate a mode mismatch or transform bug."
                )
                result.warnings.append(msg)
                _logger.warning(msg)
                _finish_ingestion_run(conn, run_id, result.fetched, 0, 0, "degraded", msg)
                conn.close()
                result.status = "degraded"
                result.started_at = started_at.isoformat()
                result.completed_at = datetime.now(timezone.utc).isoformat()
                return result

        # ── Phase 3: Upsert ────────────────────────────────────────────
        if source_purpose == "coverage_only":
            print("     ⓘ  Source is coverage-only — skipping upsert")
        elif result.transformed > 0:
            import json
            upsert_fn = getattr(crawler, "UPSERT_FUNCTION", "upsert_pncp_raw_bids")
            cur = conn.cursor()
            try:
                cur.execute(
                    f"SELECT * FROM {upsert_fn}(%s)",
                    (json.dumps(records),),
                )
                results_rows = cur.fetchall()
                result.inserted = sum(1 for r in results_rows if r[0] == "inserted")
                result.updated = sum(1 for r in results_rows if r[0] == "updated")
                result.duplicates = result.fetched - result.inserted - result.updated
                conn.commit()
            except Exception as e:
                conn.rollback()
                error = f"Upsert failed: {e}"
                _finish_ingestion_run(conn, run_id, result.fetched, result.transformed, 0, "failed", error)
                conn.close()
                result.status = "failed"
                result.error_message = error
                result.started_at = started_at.isoformat()
                result.completed_at = datetime.now(timezone.utc).isoformat()
                return result
            finally:
                cur.close()

            print(f"     Upserted: {result.inserted} new, {result.updated} updated, {result.duplicates} duplicates")

        # ── Phase 4: Entity matching ────────────────────────────────────
        match_stats = _match_entities_cascade(conn, source, entities)
        result.matched = match_stats["cnpj"] + match_stats["name_normalized"] + match_stats["fuzzy"]
        result.unmatched = match_stats.get("unmatched", 0)
        print(
            f"     Matched: {result.matched} "
            f"(CNPJ: {match_stats['cnpj']}, "
            f"name: {match_stats['name_normalized']}, "
            f"fuzzy: {match_stats['fuzzy']}, "
            f"unmatched: {result.unmatched})"
        )

        # ── Determine final status ──────────────────────────────────────
        result.status = determine_status(
            fetched=result.fetched,
            transformed=result.transformed,
            errors=[result.error_message] if result.error_message else None,
            warnings=result.warnings if result.warnings else None,
            purpose=source_purpose,
            entities_covered=entities_covered_count,
        )

        _finish_ingestion_run(conn, run_id, result.fetched, result.inserted + result.updated, result.matched, result.status)

        # ── Metadata ────────────────────────────────────────────────────
        if date_from:
            result.metadata["date_from"] = date_from
        if date_to:
            result.metadata["date_to"] = date_to

        result.started_at = started_at.isoformat()
        result.completed_at = datetime.now(timezone.utc).isoformat()
        result.duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
        conn.close()
        return result

    except Exception as e:
        error = str(e)
        try:
            _finish_ingestion_run(conn, run_id, result.fetched, result.transformed, result.matched, "failed", error)
        except Exception:
            _logger.exception("Failed to record ingestion run failure")
        try:
            conn.close()
        except Exception:
            pass
        result.status = "failed"
        result.error_code = "runtime_error"
        result.error_message = error
        result.started_at = started_at.isoformat()
        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result


def _load_crawler(source: str):
    """Dynamically load crawler module for a source using the central registry."""
    import importlib

    info = _registry_lookup(source)
    if not info or not info.module:
        return None

    try:
        return importlib.import_module(f"scripts.crawl.{info.module}")
    except ImportError as e:
        print(f"     ⚠️  Cannot import {info.module}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="Multi-Source Coverage Monitor — Extra Construtora")
    from scripts.crawl.registry import iter_choices as _registry_choices

    p.add_argument(
        "--source",
        default="pncp",
        choices=_registry_choices(),
        help="Data source to crawl (default: pncp)",
    )
    p.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental", "dry-run", "template", "selenium", "detect", "backfill"],
        help="Crawl mode (default: full). Sources may support additional modes.",
    )
    p.add_argument(
        "--report-coverage",
        action="store_true",
        help="Print coverage report and exit (no crawl)",
    )
    p.add_argument(
        "--within-200km-only",
        action="store_true",
        help="Only match entities within 200km of Florianópolis",
    )
    p.add_argument(
        "--dsn",
        default=DEFAULT_DSN,
        help="PostgreSQL DSN",
    )
    p.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Write structured result JSON to this path",
    )
    p.add_argument(
        "--date-from",
        type=str,
        default=None,
        help="Start date for backfill mode (YYYY-MM-DD)",
    )
    p.add_argument(
        "--date-to",
        type=str,
        default=None,
        help="End date for backfill mode (YYYY-MM-DD)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero for degraded, unexpected empty, or unexpected skipped",
    )
    p.add_argument(
        "--target",
        type=str,
        default=None,
        help="Limit to a single target (e.g. portal slug, IBGE code, municipio name)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of records/pages/portals to process",
    )
    return p.parse_args()


def main():
    from scripts.crawl.ingestion._base.crawler import CrawlerResult

    args = parse_args()

    global DEFAULT_DSN
    DEFAULT_DSN = args.dsn

    # Coverage report only
    if args.report_coverage:
        conn = _get_conn()
        try:
            result = report_coverage(conn)
            print_coverage_report(result)
            return 0 if result["total_uncovered"] == 0 else 1
        finally:
            conn.close()

    # Load entities
    conn = _get_conn()
    try:
        entities = _load_entities(conn, within_200km_only=args.within_200km_only)
    finally:
        conn.close()

    within = sum(1 for e in entities if e["raio_200km"])
    print(f"\n📋 {len(entities)} entidades carregadas ({within} no raio 200km)")

    # Run crawl
    source_name = _registry_resolve(args.source)  # normalize via central registry
    sources = SOURCES if source_name == "all" else [source_name]

    results: list[CrawlerResult] = []
    for src in sources:
        print("\n─" * 60)
        print(f"📍 Source: {src.upper()} | Mode: {args.mode}")
        print("─" * 60)

        if args.mode == "dry-run":
            print(f"  [DRY RUN] Would crawl {src}")
            results.append(CrawlerResult(source=src, status="skipped"))
            continue

        result = crawl_source(src, entities, args.mode,
                              date_from=args.date_from, date_to=args.date_to,
                              target=args.target, limit=args.limit)
        results.append(result)

        status_icon = {"success": "✅", "degraded": "⚠️", "empty": "📭", "skipped": "⏭️", "failed": "❌"}.get(result.status, "❓")
        print(f"  {status_icon} {result.status}: fetched={result.fetched}, transformed={result.transformed}, "
              f"inserted={result.inserted}, updated={result.updated}, matched={result.matched}")
        if result.warnings:
            for w in result.warnings:
                print(f"     ⚠️  {w}")
        if result.dependencies_missing:
            print(f"     🔑 Missing: {', '.join(result.dependencies_missing)}")

    # Summary
    print(f"\n{'=' * 60}")
    print("  RESUMO")
    print(f"{'=' * 60}")
    total_fetched = sum(r.fetched for r in results)
    total_transformed = sum(r.transformed for r in results)
    total_inserted = sum(r.inserted for r in results)
    total_updated = sum(r.updated for r in results)
    total_matched = sum(r.matched for r in results)
    success = [r for r in results if r.status == "success"]
    degraded = [r for r in results if r.status == "degraded"]
    empty_src = [r for r in results if r.status == "empty"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    print(f"  Success:   {len(success)} sources")
    print(f"  Degraded:  {len(degraded)} sources")
    print(f"  Empty:     {len(empty_src)} sources")
    print(f"  Skipped:   {len(skipped)} sources")
    print(f"  Fetched:   {total_fetched}")
    print(f"  Transformed: {total_transformed}")
    print(f"  Inserted:  {total_inserted}")
    print(f"  Updated:   {total_updated}")
    print(f"  Matched:   {total_matched}")
    if failed:
        print(f"  Failed:    {len(failed)} sources")
        for f in failed:
            print(f"    • {f.source}: {f.error_message or 'unknown'}")

    # Quick coverage after crawl
    conn = _get_conn()
    try:
        cov_result = report_coverage(conn)
        print(f"\n  📊 Coverage: {cov_result['pct']}% ({cov_result['total_covered']}/{cov_result['total_entities']})")
    finally:
        conn.close()

    # ── Output JSON ─────────────────────────────────────────────────────
    if args.output_json:
        import json as _json
        from datetime import datetime as _dt

        output = {
            "results": [r.to_dict() for r in results],
            "summary": {
                "total_fetched": total_fetched,
                "total_transformed": total_transformed,
                "total_inserted": total_inserted,
                "total_updated": total_updated,
                "total_matched": total_matched,
                "sources_success": len(success),
                "sources_degraded": len(degraded),
                "sources_empty": len(empty_src),
                "sources_skipped": len(skipped),
                "sources_failed": len(failed),
                "generated_at": _dt.now().isoformat(),
            },
        }
        with open(args.output_json, "w") as f:
            _json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  📄 Result JSON: {args.output_json}")

    # ── Exit code ───────────────────────────────────────────────────────
    exit_code = 0
    if failed:
        exit_code = 1
    if getattr(args, "strict", False):
        if degraded or empty_src or skipped:
            exit_code = exit_code or 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
