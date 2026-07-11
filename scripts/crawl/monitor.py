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
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCES = ["pncp", "dom_sc", "pcp", "compras_gov", "sc_compras", "contracts", "transparencia", "tce_sc"]

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres@127.0.0.1:5433/pncp_datalake",
)

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


def _start_ingestion_run(conn, source: str) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ingestion_runs (source, status) VALUES (%s, 'running') RETURNING id",
        (source,),
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return run_id


def _finish_ingestion_run(conn, run_id: int, fetched: int, upserted: int,
                          covered: int, status: str = "completed", error: str = ""):
    cur = conn.cursor()
    cur.execute(
        """UPDATE ingestion_runs
           SET finished_at = NOW(), records_fetched = %s, records_upserted = %s,
               entities_covered = %s, status = %s, error_message = %s
           WHERE id = %s""",
        (fetched, upserted, covered, status, error or None, run_id),
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
    ENTITY_MATCH_FUZZY_THRESHOLD = float(
        os.getenv("ENTITY_MATCH_FUZZY_THRESHOLD", "0.85")
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
    name_exact_index: dict[str, dict] = {}         # normalized_name -> entity
    name_muni_index: dict[tuple[str, str], dict] = {}  # (norm_name, codigo_ibge) -> entity
    all_entities_norm: list[dict] = []             # for fuzzy matching

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
                    candidates = [
                        e for e in all_entities_norm
                        if e.get("codigo_ibge") == codigo_ibge
                    ]

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
                conn, pncp_id, None, "unmatched", 0.0, None,
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
        result["total_covered"] += (covered or 0)
        result["total_uncovered"] += (uncovered or 0)

    result["pct"] = round(
        result["total_covered"] / result["total_entities"] * 100, 1
    ) if result["total_entities"] > 0 else 0

    # Per-source breakdown
    cur.execute(
        """SELECT source, COUNT(*) AS entity_count, COUNT(*) FILTER (WHERE is_covered) AS covered
           FROM entity_coverage
           WHERE within_200km = TRUE
           GROUP BY source
           ORDER BY source"""
    )
    result["by_source"] = [
        {"source": r[0], "entities": r[1], "covered": r[2]} for r in cur.fetchall()
    ]

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
        {"razao_social": r[0], "cnpj_8": r[1], "municipio": r[2], "natureza": r[3]}
        for r in cur.fetchall()
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

    print(f"\n  📊 TOTAL: {result['total_entities']} entidades | "
          f"{result['total_covered']} cobertas ({result['pct']}%) | "
          f"{result['total_uncovered']} descobertas")

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

def crawl_source(source: str, entities: list[dict], mode: str = "full") -> dict:
    """Run crawl for a specific source, match entities, return stats.

    Each source module is expected to provide:
        crawl(mode) → list[dict]  # raw records from source
        transform(records) → list[dict]  # normalized to pncp_raw_bids schema
    """
    conn = _get_conn()
    run_id = _start_ingestion_run(conn, source)
    fetched = 0
    upserted = 0
    matched = 0
    error = ""

    try:
        # Try to import source-specific crawler
        crawler = _load_crawler(source)
        if crawler is None:
            error = f"Crawler not implemented: {source}"
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "failed", error)
            conn.close()
            return {"source": source, "status": "skipped", "error": error}

        # Phase 1: Crawl
        print(f"  🔍 Crawling {source} ({mode})...")
        raw_records = crawler.crawl(mode)
        fetched = len(raw_records)
        print(f"     Fetched: {fetched} records")

        if not raw_records:
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "completed")
            conn.close()
            return {"source": source, "status": "ok", "fetched": 0, "upserted": 0, "matched": 0}

        # Phase 2: Transform to unified schema
        records = crawler.transform(raw_records)
        records = [{**r, "source": source} for r in records]

        # Phase 3: Upsert via RPC
        import json
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s)",
                (json.dumps(records),),
            )
            results = cur.fetchall()
            upserted = sum(1 for r in results if r[0] == "inserted")
            conn.commit()
        except Exception as e:
            conn.rollback()
            error = f"Upsert failed: {e}"
            _finish_ingestion_run(conn, run_id, fetched, 0, 0, "failed", error)
            conn.close()
            return {"source": source, "status": "failed", "error": error}
        finally:
            cur.close()

        print(f"     Upserted: {upserted} new, {fetched - upserted} duplicates")

        # Phase 4: Entity matching (3-level cascade: CNPJ → name → fuzzy)
        match_stats = _match_entities_cascade(conn, source, entities)
        matched = match_stats["cnpj"] + match_stats["name_normalized"] + match_stats["fuzzy"]
        print(f"     Matched: {matched} "
              f"(CNPJ: {match_stats['cnpj']}, "
              f"name: {match_stats['name_normalized']}, "
              f"fuzzy: {match_stats['fuzzy']}, "
              f"unmatched: {match_stats['unmatched']})")

        _finish_ingestion_run(conn, run_id, fetched, upserted, matched, "completed")
        conn.close()

        return {
            "source": source,
            "status": "ok",
            "fetched": fetched,
            "upserted": upserted,
            "matched": matched,
        }

    except Exception as e:
        error = str(e)
        try:
            _finish_ingestion_run(conn, run_id, fetched, upserted, matched, "failed", error)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"source": source, "status": "failed", "error": error}


def _load_crawler(source: str):
    """Dynamically load crawler module for a source."""
    # All crawler modules live in scripts/crawl/
    module_map = {
        "pncp": "pncp_crawler_adapter",   # simplified sync adapter
        "dom_sc": "dom_sc_crawler",
        "pcp": "pcp_crawler",
        "compras_gov": "compras_gov_crawler",
        "sc_compras": "sc_compras_crawler",
        "contracts": "contracts_crawler",
        "transparencia": "transparencia_crawler",
        "tce_sc": "tce_sc_crawler",
    }
    mod_name = module_map.get(source)
    if not mod_name:
        return None

    try:
        import importlib
        return importlib.import_module(f"scripts.crawl.{mod_name}")
    except ImportError as e:
        print(f"     ⚠️  Cannot import {mod_name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Multi-Source Coverage Monitor — Extra Construtora"
    )
    p.add_argument(
        "--source",
        default="pncp",
        choices=["pncp", "dom_sc", "pcp", "compras_gov", "sc_compras", "contracts", "transparencia", "tce_sc", "all"],
        help="Data source to crawl (default: pncp)",
    )
    p.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental", "dry-run"],
        help="Crawl mode (default: full)",
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
    return p.parse_args()


def main():
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
    sources = SOURCES if args.source == "all" else [args.source]

    results = []
    for src in sources:
        print("\n─" * 60)
        print(f"📍 Source: {src.upper()} | Mode: {args.mode}")
        print("─" * 60)

        if args.mode == "dry-run":
            print(f"  [DRY RUN] Would crawl {src}")
            results.append({"source": src, "status": "dry-run"})
            continue

        result = crawl_source(src, entities, args.mode)
        results.append(result)

        status_icon = "✅" if result["status"] == "ok" else "❌"
        print(f"  {status_icon} {result}")

    # Summary
    print(f"\n{'=' * 60}")
    print("  RESUMO")
    print(f"{'=' * 60}")
    total_fetched = sum(r.get("fetched", 0) for r in results)
    total_upserted = sum(r.get("upserted", 0) for r in results)
    total_matched = sum(r.get("matched", 0) for r in results)
    failed = [r for r in results if r["status"] == "failed"]

    print(f"  Fetched:  {total_fetched}")
    print(f"  Upserted: {total_upserted}")
    print(f"  Matched:  {total_matched}")
    if failed:
        print(f"  Failed:   {len(failed)} sources")
        for f in failed:
            print(f"    • {f['source']}: {f.get('error', 'unknown')}")

    # Quick coverage after crawl
    conn = _get_conn()
    try:
        result = report_coverage(conn)
        print(f"\n  📊 Coverage: {result['pct']}% "
              f"({result['total_covered']}/{result['total_entities']})")
    finally:
        conn.close()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
