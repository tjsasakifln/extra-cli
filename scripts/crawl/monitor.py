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
from typing import Any

_logger = logging.getLogger(__name__)

# Force project root to the front of sys.path.
# When this file is executed as a script, Python prepends scripts/crawl/,
# which contains a local config.py that would shadow the top-level
# config/ package (error: "config is not a package").
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_root = str(_PROJECT_ROOT)
if _root in sys.path:
    sys.path.remove(_root)
sys.path.insert(0, _root)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SOURCES loaded from central registry — single source of truth
from scripts.crawl.registry import iter_sources
from scripts.crawl.registry import lookup as _registry_lookup
from scripts.crawl.registry import resolve_name as _registry_resolve

SOURCES = [s.name for s in iter_sources()]

from datetime import UTC

from config.settings import DEFAULT_DSN  # single source of truth (TD-3.2)

COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _resolve_dsn(explicit: str | None = None) -> str:
    """Resolve DSN from CLI override, module global, or environment.

    Avoids silent fallback to Unix socket when DEFAULT_DSN is empty/None.
    """
    candidates = [
        explicit,
        DEFAULT_DSN,
        os.getenv("DATABASE_URL"),
        os.getenv("LOCAL_DATALAKE_DSN"),
        "postgresql://test:test@127.0.0.1:5433/pncp_datalake",
    ]
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    raise RuntimeError(
        "No PostgreSQL DSN: pass --dsn or set DATABASE_URL / LOCAL_DATALAKE_DSN"
    )


def _get_conn(dsn: str | None = None) -> Any:
    import psycopg2

    return psycopg2.connect(_resolve_dsn(dsn))


def _load_entities(conn: Any, within_200km_only: bool = False) -> list[dict[str, Any]]:
    """Load all active SC public entities."""
    cur = conn.cursor()
    sql = (
        "SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica, "
        "latitude, longitude, raio_200km FROM sc_public_entities WHERE is_active = TRUE"
    )
    if within_200km_only:
        sql += " AND raio_200km = TRUE"
    sql += " ORDER BY id"
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    entities = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return entities


# NOTE: match_entity is imported from matching/entity_matcher (TD-027 unified)


def _start_ingestion_run(conn: Any, source: str, mode: str = "incremental") -> int:
    """Insert a new ingestion_runs row, returning its id.

    Auto-detects whether the schema has crawl_batch_id/run_type (v2)
    or the simpler v1 schema, and inserts accordingly.

    Maps non-standard modes (backfill, selenium, detect, etc.) to 'full'
    for the run_type column in v2 schemas.
    """
    import json as _json
    import uuid

    # Map mode to valid run_type for DB constraint compatibility
    _VALID_RUN_TYPES = {"full", "incremental", "dry-run"}  # noqa: N806
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
    return run_id  # type: ignore[no-any-return]


def _finish_ingestion_run(
    conn: Any, run_id: int, fetched: int, upserted: int, covered: int, status: str = "completed", error: str = ""
) -> None:
    """Update ingestion_runs row at end of crawl. Auto-detects schema version."""
    cur = conn.cursor()
    db_status = status
    if status in {"success", "degraded", "empty", "skipped"}:
        db_status = "completed"
    elif status not in {"completed", "failed", "running"}:
        db_status = "completed"

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
            (fetched, upserted, 0, db_status, error or "", run_id),
        )
    else:
        # v1 schema: use records_fetched, records_upserted, entities_covered
        cur.execute(
            """UPDATE ingestion_runs
               SET finished_at = NOW(), records_fetched = %s,
                   records_upserted = %s, entities_covered = %s,
                   status = %s, error_message = %s
               WHERE id = %s""",
            (fetched, upserted, covered, db_status, error or "", run_id),
        )
    conn.commit()
    cur.close()


# TD-027: Unificado — entity matching agora em scripts/matching/entity_matcher.py
from scripts.matching.entity_matcher import (
    match_entities_cascade as _match_entities_cascade,
)

# ---------------------------------------------------------------------------
# Coverage Reporting
# ---------------------------------------------------------------------------


def report_coverage(conn: Any) -> dict[str, Any]:
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

    result: dict[str, Any] = {"groups": [], "total_entities": 0, "total_covered": 0, "total_uncovered": 0}
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
# PNCP helpers
# ---------------------------------------------------------------------------


def _upsert_raw_records(conn: Any, records: list[dict[str, Any]], upsert_fn: str) -> tuple[int, int, int]:
    import json

    from psycopg2.sql import SQL, Identifier

    cur = conn.cursor()
    try:
        cur.execute(
            SQL("SELECT * FROM {} (%s)").format(Identifier(upsert_fn)),
            (json.dumps(records),),
        )
        rows = cur.fetchall()
        conn.commit()
    finally:
        cur.close()

    if not rows:
        return 0, 0, 0

    first = rows[0]
    if len(rows) == 1 and len(first) >= 3 and all(isinstance(v, int) for v in first[:3]):
        inserted, updated, unchanged = first[:3]
        return inserted, updated, unchanged

    inserted = sum(1 for row in rows if row and row[0] == "inserted")
    updated = sum(1 for row in rows if row and row[0] == "updated")
    unchanged = sum(1 for row in rows if row and row[0] in {"skipped", "unchanged"})
    return inserted, updated, unchanged


def _load_cached_pncp_enrichment(
    conn: Any, pncp_id: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT detail_payload, items_payload, documents_payload
            FROM pncp_enrichment_cache
            WHERE pncp_id = %s
            """,
            (pncp_id,),
        )
        row = cur.fetchone()
    except Exception:
        _logger.exception("Failed to load cached PNCP enrichment for pncp_id=%s", pncp_id)
        # Cache is best-effort, not critical path — degrade gracefully
        return None, [], []
    finally:
        cur.close()

    if not row:
        return None, [], []
    return row[0], row[1] or [], row[2] or []


def _store_cached_pncp_enrichment(
    conn: Any, pncp_id: str, detail: dict[str, Any] | None, items: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> None:
    from psycopg2.extras import Json

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO pncp_enrichment_cache (pncp_id, detail_payload, items_payload, documents_payload, fetched_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (pncp_id) DO UPDATE
            SET detail_payload = EXCLUDED.detail_payload,
                items_payload = EXCLUDED.items_payload,
                documents_payload = EXCLUDED.documents_payload,
                fetched_at = NOW()
            """,
            (pncp_id, Json(detail) if detail is not None else None, Json(items), Json(documents)),
        )
        conn.commit()
    except Exception:
        _logger.exception("Failed to store PNCP enrichment cache for pncp_id=%s", pncp_id)
        conn.rollback()
    finally:
        cur.close()


def _build_pncp_opportunities(
    conn: Any,
    records: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    *,
    target: str | None,
    engineering_only: bool,
    within_200km_only: bool,
) -> tuple[list[dict], dict]:
    from scripts.crawl import pncp_crawler_adapter as pncp
    from scripts.crawl.pncp_contract import parse_target
    from scripts.crawl.pncp_engineering import classify_engineering
    from scripts.crawl.pncp_geo import GeographyResolver

    target_parsed = parse_target(target)
    resolver = GeographyResolver(entities)
    opportunities: list[dict] = []
    stats = {
        "classified_engineering": 0,
        "engineering_confirmed": 0,
        "engineering_probable": 0,
        "engineering_review_required": 0,
        "false_positive_discarded": 0,
        "within_200km": 0,
        "remaining_sc": 0,
        "location_unconfirmed": 0,
        "selected_count": 0,
    }

    for record in records:
        location = resolver.resolve(record)
        quick = classify_engineering(record)

        detail = None
        items: list[dict] = []
        documents: list[dict] = []
        needs_hydration = quick.score < 80 and (
            quick.score >= 35 or target_parsed.kind == "engineering" or engineering_only
        )

        if (
            needs_hydration
            and record.get("orgao_cnpj")
            and record.get("ano_compra")
            and record.get("sequencial_compra")
        ):
            detail, items, documents = _load_cached_pncp_enrichment(conn, record["pncp_id"])
            if not detail and not items and not documents:
                detail_res = pncp.fetch_compra_detail(
                    record["orgao_cnpj"], int(record["ano_compra"]), int(record["sequencial_compra"])
                )
                items_res = pncp.fetch_compra_items(
                    record["orgao_cnpj"], int(record["ano_compra"]), int(record["sequencial_compra"])
                )
                docs_res = pncp.fetch_compra_documents(
                    record["orgao_cnpj"], int(record["ano_compra"]), int(record["sequencial_compra"])
                )
                detail = detail_res.records[0] if detail_res.records else None
                items = items_res.records
                documents = docs_res.records
                _store_cached_pncp_enrichment(conn, record["pncp_id"], detail, items, documents)

        classification = classify_engineering(record, detail=detail, items=items, documents=documents)
        stats["classified_engineering"] += 1
        if classification.confidence == "engenharia_confirmada":
            stats["engineering_confirmed"] += 1
        elif classification.confidence == "engenharia_provavel":
            stats["engineering_probable"] += 1
        elif classification.confidence == "revisao_necessaria":
            stats["engineering_review_required"] += 1
        elif not classification.is_engineering:
            stats["false_positive_discarded"] += 1

        if location.geographic_priority == "PRIORIDADE_1":
            stats["within_200km"] += 1
        elif location.geographic_priority == "PRIORIDADE_2":
            stats["remaining_sc"] += 1
        elif location.geographic_priority == "LOCALIZACAO_NAO_CONFIRMADA":
            stats["location_unconfirmed"] += 1

        selected = True
        if target_parsed.kind == "municipio":
            selected = location.codigo_municipio_ibge == target_parsed.value
        elif target_parsed.kind == "municipio_nome":
            selected = (location.municipio or "").strip().lower() == (target_parsed.value or "").strip().lower()
        elif target_parsed.kind == "cnpj":
            selected = "".join(ch for ch in (record.get("orgao_cnpj") or "") if ch.isdigit()) == (
                target_parsed.value or ""
            )
        elif target_parsed.kind == "within_200km":
            selected = location.within_200km
        elif target_parsed.kind == "engineering":
            selected = classification.score >= 40

        if engineering_only:
            selected = selected and classification.score >= 40
        if within_200km_only:
            selected = selected and location.within_200km
        if selected:
            stats["selected_count"] += 1

        opportunities.append(
            {
                "pncp_id": record["pncp_id"],
                "source": record.get("source") or "pncp",
                "source_id": record.get("source_id") or record["pncp_id"],
                "objeto_compra": record.get("objeto_compra"),
                "orgao_cnpj": record.get("orgao_cnpj"),
                "orgao_razao_social": record.get("orgao_razao_social"),
                "codigo_municipio_ibge": location.codigo_municipio_ibge,
                "municipio": location.municipio,
                "uf": location.uf,
                "modalidade_id": record.get("modalidade_id"),
                "modalidade_nome": record.get("modalidade_nome"),
                "valor_total_estimado": record.get("valor_total_estimado"),
                "data_publicacao": record.get("data_publicacao"),
                "data_abertura": record.get("data_abertura"),
                "data_encerramento": record.get("data_encerramento"),
                "link_pncp": record.get("link_pncp"),
                "link_sistema_origem": record.get("link_sistema_origem"),
                "is_engineering": classification.is_engineering,
                "engineering_score": classification.score,
                "engineering_confidence": classification.confidence,
                "engineering_categories": classification.categories,
                "classification_reasons": classification.reasons,
                "classifier_version": classification.reasons.get("classifier_version"),
                "exclusion_reason": classification.exclusion_reason,
                "distance_from_florianopolis_km": location.distance_from_florianopolis_km,
                "within_200km": location.within_200km,
                "geographic_priority": location.geographic_priority,
                "location_confidence": location.location_confidence,
                "content_hash": record.get("content_hash"),
            }
        )

    return opportunities, stats


def _persist_engineering_opportunities(conn: Any, opportunities: list[dict[str, Any]]) -> int:
    import json

    from psycopg2.extras import execute_values

    if not opportunities:
        return 0

    rows = [
        (
            row["pncp_id"],
            row["source"],
            row["source_id"],
            row["objeto_compra"],
            row["orgao_cnpj"],
            row["orgao_razao_social"],
            row["codigo_municipio_ibge"],
            row["municipio"],
            row["uf"],
            row["modalidade_id"],
            row["modalidade_nome"],
            row["valor_total_estimado"],
            row["data_publicacao"],
            row["data_abertura"],
            row["data_encerramento"],
            row["link_pncp"],
            row["link_sistema_origem"],
            row["is_engineering"],
            row["engineering_score"],
            row["engineering_confidence"],
            row["engineering_categories"],
            json.dumps(row["classification_reasons"], ensure_ascii=False),
            row["classifier_version"],
            row["exclusion_reason"],
            row["distance_from_florianopolis_km"],
            row["within_200km"],
            row["geographic_priority"],
            row["location_confidence"],
            row["content_hash"],
        )
        for row in opportunities
    ]

    cur = conn.cursor()
    try:
        execute_values(
            cur,
            """
            INSERT INTO engineering_opportunities (
                pncp_id, source, source_id, objeto_compra, orgao_cnpj, orgao_razao_social,
                codigo_municipio_ibge, municipio, uf, modalidade_id, modalidade_nome,
                valor_total_estimado, data_publicacao, data_abertura, data_encerramento,
                link_pncp, link_sistema_origem, is_engineering, engineering_score,
                engineering_confidence, engineering_categories, classification_reasons,
                classifier_version, exclusion_reason, distance_from_florianopolis_km,
                within_200km, geographic_priority, location_confidence, content_hash,
                first_seen_at, last_seen_at
            ) VALUES %s
            ON CONFLICT (pncp_id) DO UPDATE
            SET
                source = EXCLUDED.source,
                source_id = EXCLUDED.source_id,
                objeto_compra = EXCLUDED.objeto_compra,
                orgao_cnpj = EXCLUDED.orgao_cnpj,
                orgao_razao_social = EXCLUDED.orgao_razao_social,
                codigo_municipio_ibge = EXCLUDED.codigo_municipio_ibge,
                municipio = EXCLUDED.municipio,
                uf = EXCLUDED.uf,
                modalidade_id = EXCLUDED.modalidade_id,
                modalidade_nome = EXCLUDED.modalidade_nome,
                valor_total_estimado = EXCLUDED.valor_total_estimado,
                data_publicacao = EXCLUDED.data_publicacao,
                data_abertura = EXCLUDED.data_abertura,
                data_encerramento = EXCLUDED.data_encerramento,
                link_pncp = EXCLUDED.link_pncp,
                link_sistema_origem = EXCLUDED.link_sistema_origem,
                is_engineering = EXCLUDED.is_engineering,
                engineering_score = EXCLUDED.engineering_score,
                engineering_confidence = EXCLUDED.engineering_confidence,
                engineering_categories = EXCLUDED.engineering_categories,
                classification_reasons = EXCLUDED.classification_reasons,
                classifier_version = EXCLUDED.classifier_version,
                exclusion_reason = EXCLUDED.exclusion_reason,
                distance_from_florianopolis_km = EXCLUDED.distance_from_florianopolis_km,
                within_200km = EXCLUDED.within_200km,
                geographic_priority = EXCLUDED.geographic_priority,
                location_confidence = EXCLUDED.location_confidence,
                content_hash = EXCLUDED.content_hash,
                last_seen_at = NOW()
            """,
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::timestamptz,%s::timestamptz,%s::timestamptz,%s,%s,%s,%s,%s,%s::text[],%s::jsonb,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
        )
        conn.commit()
    finally:
        cur.close()
    return len(opportunities)


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
    engineering_only: bool = False,
    within_200km_only: bool = False,
) -> Any:
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
    from datetime import datetime

    from scripts.crawl.credential_validator import validate_source_credentials
    from scripts.crawl.ingestion._base.crawler import (
        CrawlerResult,
        CrawlRequest,
        determine_status,
    )

    started_at = datetime.now(UTC)
    result = CrawlerResult(source=source)

    conn = _get_conn()
    run_id = _start_ingestion_run(conn, source, mode)

    try:
        # ── Load crawler module ───────────────────────────────────────
        crawler = _load_crawler(source)
        if crawler is None:
            error = f"Crawler not implemented: {source}"
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "failed", error)
            _record_evidence(conn, run_id, source, "failed", error_message=error, error_code="crawler_not_implemented")
            conn.close()
            result.status = "failed"
            result.error_code = "crawler_not_implemented"
            result.error_message = error
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(UTC).isoformat()
            return result

        # ── Credential validation ──────────────────────────────────────
        creds_ok, missing_creds = validate_source_credentials(source)
        if not creds_ok:
            msg = f"Missing credentials: {', '.join(missing_creds)}"
            result.dependencies_missing = missing_creds
            result.warnings.append(msg)
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "skipped", msg)
            _record_evidence(conn, run_id, source, "skipped", error_message=msg, error_code="missing_credentials")
            conn.close()
            result.status = "skipped"
            result.error_code = "missing_credentials"
            result.error_message = msg
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(UTC).isoformat()
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
        fetch_result = None
        try:
            raw_response = crawler.crawl(crawl_req)
        except TypeError:
            raw_response = crawler.crawl(mode)

        if hasattr(raw_response, "request_completed") and hasattr(raw_response, "records"):
            fetch_result = raw_response
            raw_records = fetch_result.records
            result.metadata["fetch_result"] = fetch_result.metadata
            result.metadata["fetch_status"] = fetch_result.status
            result.metadata["pages_fetched"] = fetch_result.pages_fetched
            result.metadata["pages_expected"] = fetch_result.pages_expected
            result.metadata["provenance"] = fetch_result.provenance
            if fetch_result.status in {"partial", "rate_limited", "auth_blocked", "error"}:
                result.external_failures = 1
                error = "; ".join(fetch_result.errors) or str(fetch_result.status)
                semantic_status = str(fetch_result.status)
                _finish_ingestion_run(conn, run_id, len(raw_records), 0, 0, semantic_status, error)
                _record_evidence(
                    conn,
                    run_id,
                    source,
                    semantic_status,
                    fetched=len(raw_records),
                    error_message=error,
                    error_code=semantic_status,
                    metadata={
                        "pages_fetched": fetch_result.pages_fetched,
                        "pages_expected": fetch_result.pages_expected,
                        "provenance": fetch_result.provenance,
                    },
                )
                conn.close()
                result.fetched = len(raw_records)
                result.status = semantic_status  # type: ignore[assignment]
                result.error_code = semantic_status
                result.error_message = error
                result.started_at = started_at.isoformat()
                result.completed_at = datetime.now(UTC).isoformat()
                return result
        else:
            raw_records = raw_response

        result.fetched = len(raw_records)
        print(f"     Fetched: {result.fetched} records")

        if not raw_records:
            # Legacy [] cannot prove absence. Only the canonical adapter may
            # emit empty_confirmed after complete pagination and provenance.
            status = "partial"
            if fetch_result is not None:
                status = "empty_confirmed" if fetch_result.coverage_satisfactory and fetch_result.empty_confirmed else str(fetch_result.status)
            _finish_ingestion_run(conn, run_id, 0, 0, 0, status)
            error_code = None if status == "empty_confirmed" else "zero_ambiguous"
            _record_evidence(
                conn, run_id, source, status, error_code=error_code,
                metadata={
                    "pages_fetched": fetch_result.pages_fetched if fetch_result else None,
                    "pages_expected": fetch_result.pages_expected if fetch_result else None,
                    "provenance": fetch_result.provenance if fetch_result else {},
                },
            )
            conn.close()
            result.status = status  # type: ignore[assignment]
            result.error_code = error_code
            result.started_at = started_at.isoformat()
            result.completed_at = datetime.now(UTC).isoformat()
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
                _record_evidence(conn, run_id, source, "degraded", fetched=result.fetched, error_message=msg)
                conn.close()
                result.status = "degraded"
                result.started_at = started_at.isoformat()
                result.completed_at = datetime.now(UTC).isoformat()
                return result

        # ── Phase 3: Upsert ────────────────────────────────────────────
        if source_purpose == "coverage_only":
            print("     ⓘ  Source is coverage-only — skipping upsert")
        elif result.transformed > 0:
            upsert_fn = getattr(crawler, "UPSERT_FUNCTION", "upsert_pncp_raw_bids")
            try:
                result.inserted, result.updated, result.duplicates = _upsert_raw_records(conn, records, upsert_fn)
            except Exception as e:
                conn.rollback()
                error = f"Upsert failed: {e}"
                _finish_ingestion_run(conn, run_id, result.fetched, result.transformed, 0, "failed", error)
                _record_evidence(
                    conn,
                    run_id,
                    source,
                    "failed",
                    fetched=result.fetched,
                    transformed=result.transformed,
                    error_message=error,
                    error_code="persist_failed",
                )
                conn.close()
                result.status = "failed"
                result.error_message = error
                result.started_at = started_at.isoformat()
                result.completed_at = datetime.now(UTC).isoformat()
                return result

            print(f"     Upserted: {result.inserted} new, {result.updated} updated, {result.duplicates} duplicates")

        # ── Phase 4: Entity matching ────────────────────────────────────
        current_pncp_ids = [r.get("pncp_id") for r in records if r.get("pncp_id")]
        match_stats = _match_entities_cascade(conn, source, entities, current_pncp_ids)
        result.matched = match_stats["cnpj"] + match_stats["name_normalized"] + match_stats["fuzzy"]
        result.unmatched = match_stats.get("unmatched", 0)
        print(
            f"     Matched: {result.matched} "
            f"(CNPJ: {match_stats['cnpj']}, "
            f"name: {match_stats['name_normalized']}, "
            f"fuzzy: {match_stats['fuzzy']}, "
            f"unmatched: {result.unmatched})"
        )

        if source == "pncp" and result.transformed > 0:
            opportunities, op_stats = _build_pncp_opportunities(
                conn,
                records,
                entities,
                target=target,
                engineering_only=engineering_only,
                within_200km_only=within_200km_only,
            )
            result.classified_engineering = op_stats["classified_engineering"]
            result.engineering_confirmed = op_stats["engineering_confirmed"]
            result.engineering_probable = op_stats["engineering_probable"]
            result.engineering_review_required = op_stats["engineering_review_required"]
            result.false_positive_discarded = op_stats["false_positive_discarded"]
            result.within_200km = op_stats["within_200km"]
            result.remaining_sc = op_stats["remaining_sc"]
            result.location_unconfirmed = op_stats["location_unconfirmed"]
            result.opportunities_persisted = _persist_engineering_opportunities(conn, opportunities)
            result.metadata["selected_count"] = op_stats["selected_count"]
            print(
                "     Engineering: "
                f"classified={result.classified_engineering}, "
                f"confirmed={result.engineering_confirmed}, "
                f"probable={result.engineering_probable}, "
                f"within_200km={result.within_200km}, "
                f"persisted={result.opportunities_persisted}"
            )

        # ── Determine final status ──────────────────────────────────────
        result.status = determine_status(  # type: ignore[assignment]
            fetched=result.fetched,
            transformed=result.transformed,
            errors=[result.error_message] if result.error_message else None,
            warnings=result.warnings if result.warnings else None,
            purpose=source_purpose,
            entities_covered=entities_covered_count,
        )

        _finish_ingestion_run(
            conn, run_id, result.fetched, result.inserted + result.updated, result.matched, result.status
        )

        # ── Source-level aggregate evidence ─────────────────────────────
        _record_evidence(
            conn,
            run_id,
            source,
            result.status,
            fetched=result.fetched,
            transformed=result.transformed,
            persisted=result.inserted + result.updated,
            date_from=date_from,
            date_to=date_to,
            error_message=result.error_message,
            error_code=result.error_code,
        )

        # ── Entity-level evidence projection (PNCP only) ────────────────
        entity_evidence_stats = None
        if source == "pncp" and entities:
            # fetch_complete: True ONLY when the entire query scope completed
            # without errors. Any error (transient or permanent) means some
            # pages were not fetched → we cannot guarantee that entities
            # without matches are truly absent → must be conservative.
            # Success_zero is legitimate ONLY when fetch_complete=True.
            if fetch_result is not None:
                fetch_complete = fetch_result.coverage_satisfactory
            else:
                fetch_complete = False
            entity_evidence_stats = _project_entity_evidence(
                conn=conn,
                run_id=run_id,
                source=source,
                entities=entities,
                fetch_complete=fetch_complete,
                date_from=date_from,
                date_to=date_to,
                fetch_metadata=fetch_result.metadata if fetch_result else None,
                current_pncp_ids=current_pncp_ids,
            )
            if entity_evidence_stats:
                result.metadata["entity_evidence"] = entity_evidence_stats
                conn.commit()  # Persist entity evidence rows

        # ── Metadata ────────────────────────────────────────────────────
        if date_from:
            result.metadata["date_from"] = date_from
        if date_to:
            result.metadata["date_to"] = date_to
        if target:
            result.metadata["target"] = target
        if engineering_only:
            result.metadata["engineering_only"] = True
        if within_200km_only:
            result.metadata["within_200km_only"] = True

        result.started_at = started_at.isoformat()
        result.completed_at = datetime.now(UTC).isoformat()
        result.duration_seconds = (datetime.now(UTC) - started_at).total_seconds()
        conn.close()
        return result

    except Exception as e:
        error = str(e)
        try:
            _finish_ingestion_run(conn, run_id, result.fetched, result.transformed, result.matched, "failed", error)
            _record_evidence(
                conn,
                run_id,
                source,
                "failed",
                fetched=result.fetched,
                transformed=result.transformed,
                error_message=error,
                error_code="runtime_error",
            )
        except Exception:
            _logger.exception("Failed to record ingestion run failure")
        try:
            conn.close()
        except Exception:
            _logger.warning("Failed to close DB connection after ingestion failure")
        result.status = "failed"
        result.error_code = "runtime_error"
        result.error_message = error
        result.started_at = started_at.isoformat()
        result.completed_at = datetime.now(UTC).isoformat()
        return result


def _project_entity_evidence(
    conn: Any,
    run_id: int,
    source: str,
    entities: list[dict[str, Any]],
    fetch_complete: bool,
    date_from: str | None = None,
    date_to: str | None = None,
    fetch_metadata: dict[str, Any] | None = None,
    current_pncp_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Project per-entity evidence rows after a crawl run.

    For every applicable entity in the candidate universe, writes one
    evidence row into coverage_evidence with entity-level granularity.

    Rules (never violated):
        - ``success_with_data`` only when the completed run produced records
          matched to that specific entity. Counts are per-entity (queried
          from the DB after matching), never copied from the source total.
        - ``success_zero`` only when the whole relevant query scope and
          pagination completed without errors (fetch_complete=True).
        - ``partial`` when completeness is not proven (errors, incomplete
          pagination, or fetch_complete=False).
        - Never manufactures zero evidence from absence after a failed or
          partial crawl.

    All rows are written atomically (single transaction). The UNIQUE index
    uq_ce_entity_run ensures idempotency — re-running the same run_id is a
    no-op for entity rows.
    """
    import json as _json
    from datetime import date as _date

    try:
        cur = conn.cursor()

        # Check table exists
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'coverage_evidence')")
        if not cur.fetchone()[0]:
            cur.close()
            return None

        q_start = _date.fromisoformat(date_from) if date_from else None
        q_end = _date.fromisoformat(date_to) if date_to else None
        run_id_str = str(run_id)

        # ── Query per-entity matched record counts for THIS run only ─────
        # Only count entities whose bids were matched from the current
        # run's pncp_ids — never include historical matches from other runs.
        entity_counts: dict[int, int] = {}
        if fetch_complete and current_pncp_ids:
            cur.execute(
                """SELECT matched_entity_id, COUNT(DISTINCT pncp_id)
                   FROM pncp_raw_bids
                   WHERE source = %s
                     AND matched_entity_id IS NOT NULL
                     AND pncp_id = ANY(%s)
                   GROUP BY matched_entity_id""",
                (source, current_pncp_ids),
            )
            for row in cur.fetchall():
                entity_counts[row[0]] = row[1]

        # ── Determine candidate universe ──────────────────────────────────
        # Use entities within 200km as the applicable universe.
        # If the passed entities list is already filtered, use it directly.
        # Otherwise, only consider entities with raio_200km = TRUE.
        candidate_entities = [e for e in entities if e.get("raio_200km")]
        if not candidate_entities:
            _logger.warning(
                "_project_entity_evidence: no entities with raio_200km key — "
                "falling back to ALL %d passed entities. Evidence may include "
                "entities outside the intended radius.",
                len(entities),
            )
            candidate_entities = entities

        # ── Build metadata payload ───────────────────────────────────────
        completeness_meta: dict = {}
        if fetch_complete:
            completeness_meta["completeness"] = "full_pagination_completed"
        else:
            completeness_meta["completeness"] = "incomplete_or_errors"
        if fetch_metadata:
            completeness_meta["pages_fetched"] = fetch_metadata.get("pages_fetched")
            completeness_meta["windows"] = fetch_metadata.get("windows")
        if date_from:
            completeness_meta["queried_start"] = date_from
        if date_to:
            completeness_meta["queried_end"] = date_to

        # ── Batch DELETE all old rows for this run (atomic) ─────────────
        candidate_ids = [e["id"] for e in candidate_entities]
        if candidate_ids:
            cur.execute(
                """DELETE FROM coverage_evidence
                   WHERE entity_id = ANY(%s) AND source = %s
                     AND data_type = %s AND run_id = %s""",
                (candidate_ids, source, "bids", run_id_str),
            )

        # ── Write one row per entity ─────────────────────────────────────
        written_success_data = 0
        written_success_zero = 0
        written_partial = 0

        for entity in candidate_entities:
            eid = entity["id"]
            count = entity_counts.get(eid, 0)

            if count > 0:
                state = "success_with_data"
                written_success_data += 1
            elif fetch_complete:
                state = "success_zero"
                written_success_zero += 1
            else:
                state = "partial"
                written_partial += 1

            entity_meta = dict(completeness_meta)
            entity_meta["entity_razao_social"] = entity.get("razao_social", "")

            # INSERT after batch DELETE above — idempotent, no per-row race window.
            cur.execute(
                """INSERT INTO coverage_evidence
                   (entity_id, source, data_type, queried_start, queried_end,
                    run_id, started_at, completed_at,
                    count_obtained, count_transformed, count_persisted,
                    state, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s)""",
                (
                    eid,
                    source,
                    "bids",
                    q_start,
                    q_end,
                    run_id_str,
                    count,
                    count,
                    count,
                    state,
                    _json.dumps(entity_meta, ensure_ascii=False),
                ),
            )

        cur.close()

        stats = {
            "candidate_entities": len(candidate_entities),
            "success_with_data": written_success_data,
            "success_zero": written_success_zero,
            "partial": written_partial,
            "fetch_complete": fetch_complete,
        }
        print(
            f"     Entity evidence: {written_success_data} with_data, "
            f"{written_success_zero} zero, "
            f"{written_partial} partial "
            f"(of {len(candidate_entities)} candidates, "
            f"fetch_complete={fetch_complete})"
        )
        return stats

    except Exception:
        _logger.exception("Failed to project entity evidence for source=%s run_id=%s", source, run_id)
        return None


def _record_evidence(
    conn: Any,
    run_id: int,
    source: str,
    state: str,
    fetched: int = 0,
    transformed: int = 0,
    persisted: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    error_message: str | None = None,
    error_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert one row into coverage_evidence for this source run.

    Maps monitor-level status + error_code → evidence_state enum value.
    Records source-level evidence (entity_id = NULL) for each crawl run.
    Never converts an exception into an empty success.

    This function is exception-safe: failures are logged but never
    propagated, so connection cleanup in the caller is not interrupted.
    """
    import json as _json
    from datetime import date as _date

    try:
        # Check if coverage_evidence table exists (migration 024 may not be applied)
        cur = conn.cursor()
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'coverage_evidence')")
        if not cur.fetchone()[0]:
            cur.close()
            return  # Table doesn't exist yet — skip silently

        # Map monitor status + error_code → evidence_state
        evidence_state = _map_evidence_state(state, error_code or "", fetched)

        # Parse dates
        q_start = _date.fromisoformat(date_from) if date_from else None
        q_end = _date.fromisoformat(date_to) if date_to else None

        meta = metadata or {}
        if error_message:
            meta["error_message"] = error_message

        # Idempotent upsert: DELETE old source-level aggregate row then INSERT.
        # Partial unique indexes don't reliably support ON CONFLICT across PG versions.
        cur.execute(
            """DELETE FROM coverage_evidence
               WHERE entity_id IS NULL AND source = %s AND data_type = %s AND run_id = %s""",
            (source, "bids", str(run_id)),
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, queried_start, queried_end,
                run_id, started_at, completed_at,
                count_obtained, count_transformed, count_persisted,
                state, error_message, error_code, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s)""",
            (
                None,  # entity_id: NULL = source-level aggregate
                source,
                "bids",
                q_start,
                q_end,
                str(run_id),
                fetched,
                transformed,
                persisted,
                evidence_state,
                error_message,
                error_code,
                _json.dumps(meta, ensure_ascii=False),
            ),
        )
        cur.close()
    except Exception:
        _logger.exception("Failed to record coverage evidence for source=%s run_id=%s", source, run_id)


def _map_evidence_state(monitor_status: str, error_code: str, fetched: int) -> str:
    """Map monitor.py status + error_code → coverage_evidence state enum.

    Rules (priority order):
        1. Explicit error codes map to specific failure states.
        2. monitor status maps to coarse state.
        3. fetched > 0 distinguishes success_with_data from success_zero.
        4. Never returns an empty-string or NULL state.
    """
    # Explicit error codes → specific failure states
    if error_code:
        error_mapping = {
            "crawler_not_implemented": "not_applicable",
            "missing_credentials": "auth_failed",
            "fetch_failed": "connection_failed",
            "persist_failed": "persist_failed",
            "runtime_error": "connection_failed",  # conservative default
            "partial": "partial",
            "rate_limited": "partial",
            "auth_blocked": "auth_failed",
            "error": "connection_failed",
            "zero_ambiguous": "partial",
        }
        if error_code in error_mapping:
            return error_mapping[error_code]

    # Monitor status → evidence state
    status_mapping = {
        "success": "success_with_data" if fetched > 0 else "success_zero",
        "empty_confirmed": "success_zero",
        "partial": "partial",
        "rate_limited": "partial",
        "auth_blocked": "auth_failed",
        "error": "connection_failed",
        "degraded": "partial",
        "failed": "connection_failed",
        "empty": "partial",
        "skipped": "not_investigated",
    }
    return status_mapping.get(monitor_status, "not_investigated")


def _load_crawler(source: str) -> Any:
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


def parse_args() -> argparse.Namespace:
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
        help="Prioritize only opportunities within 200km of Florianópolis in the final selection",
    )
    p.add_argument(
        "--engineering-only",
        action="store_true",
        help="Prioritize only opportunities classified as engineering in the final selection",
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


def main() -> int:
    from scripts.crawl.ingestion._base.crawler import CrawlerResult

    args = parse_args()

    global DEFAULT_DSN
    # Prefer explicit --dsn; never assign empty/None over a good default
    resolved = _resolve_dsn(args.dsn if getattr(args, "dsn", None) else None)
    DEFAULT_DSN = resolved
    args.dsn = resolved

    # Coverage report only
    if args.report_coverage:
        conn = _get_conn(resolved)
        try:
            result = report_coverage(conn)
            print_coverage_report(result)
            return 0 if result["total_uncovered"] == 0 else 1
        finally:
            conn.close()

    # Load entities
    conn = _get_conn(resolved)
    try:
        entities = _load_entities(conn, within_200km_only=False)
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

        result = crawl_source(
            src,
            entities,
            args.mode,
            date_from=args.date_from,
            date_to=args.date_to,
            target=args.target,
            limit=args.limit,
            engineering_only=args.engineering_only,
            within_200km_only=args.within_200km_only,
        )
        results.append(result)

        status_icon = {"success": "✅", "degraded": "⚠️", "empty": "📭", "skipped": "⏭️", "failed": "❌"}.get(
            result.status, "❓"
        )
        print(
            f"  {status_icon} {result.status}: fetched={result.fetched}, transformed={result.transformed}, "
            f"inserted={result.inserted}, updated={result.updated}, matched={result.matched}"
        )
        if src == "pncp":
            print(
                "     engenharia="
                f"{result.engineering_confirmed}/{result.engineering_probable}/"
                f"{result.engineering_review_required} "
                f"within_200km={result.within_200km} restante_sc={result.remaining_sc} "
                f"loc_nao_confirmada={result.location_unconfirmed} "
                f"persisted={result.opportunities_persisted}"
            )
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
    total_classified_engineering = sum(r.classified_engineering for r in results)
    total_engineering_confirmed = sum(r.engineering_confirmed for r in results)
    total_engineering_probable = sum(r.engineering_probable for r in results)
    total_within_200km = sum(r.within_200km for r in results)
    total_remaining_sc = sum(r.remaining_sc for r in results)
    total_location_unconfirmed = sum(r.location_unconfirmed for r in results)
    total_false_positive = sum(r.false_positive_discarded for r in results)
    total_persisted_opportunities = sum(r.opportunities_persisted for r in results)
    total_external_failures = sum(r.external_failures for r in results)
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
    print(f"  Classificados engenharia: {total_classified_engineering}")
    print(f"  Engenharia confirmada: {total_engineering_confirmed}")
    print(f"  Engenharia provavel: {total_engineering_probable}")
    print(f"  Dentro de 200km: {total_within_200km}")
    print(f"  Restante de SC: {total_remaining_sc}")
    print(f"  Localizacao nao confirmada: {total_location_unconfirmed}")
    print(f"  Descartados por falso positivo: {total_false_positive}")
    print(f"  Persistidos: {total_persisted_opportunities}")
    print(f"  Falhas externas: {total_external_failures}")
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
                "total_classified_engineering": total_classified_engineering,
                "total_engineering_confirmed": total_engineering_confirmed,
                "total_engineering_probable": total_engineering_probable,
                "total_within_200km": total_within_200km,
                "total_remaining_sc": total_remaining_sc,
                "total_location_unconfirmed": total_location_unconfirmed,
                "total_false_positive": total_false_positive,
                "total_persisted_opportunities": total_persisted_opportunities,
                "total_external_failures": total_external_failures,
                "sources_success": len(success),
                "sources_degraded": len(degraded),
                "sources_empty": len(empty_src),
                "sources_skipped": len(skipped),
                "sources_failed": len(failed),
                "generated_at": _dt.now().isoformat(),
            },
        }
        with open(args.output_json, "w") as fh:
            _json.dump(output, fh, indent=2, ensure_ascii=False)
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
