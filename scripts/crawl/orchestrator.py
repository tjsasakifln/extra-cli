"""
DEPRECATED: Use scripts.crawl.monitor instead.
This module is kept for reference only. Do not use in new code.

The registry at scripts.crawl.registry is the single source of truth
for all data sources — orchestrator's hardcoded SOURCES list and
module_map are obsolete and may be removed in a future release.

Original docstring:
    Crawl orchestrator module — loop principal e scheduling.
    Gerencia o pipeline completo de ingestao por source:
        Crawl -> Transform -> Upsert -> Entity Match -> Coverage Update
    Cada source e um modulo de crawler independente que fornece:
        crawl(mode) -> list[dict]
        transform(records) -> list[dict]
"""

# NOTE: from __future__ must be first per PEP 563
from __future__ import annotations  # noqa: E402

import warnings

warnings.warn(
    "scripts.crawl.orchestrator is deprecated, use scripts.crawl.monitor",
    DeprecationWarning,
    stacklevel=2,
)

import importlib  # noqa: E402 — deprecation warning before imports is intentional
import json  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

from config.logging_config import get_logger  # noqa: E402
from config.settings import DEFAULT_DSN  # noqa: E402 — single source of truth (TD-3.2)
from scripts.crawl.checkpoint import is_crawl_completed_today, save_checkpoint  # noqa: E402

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------

# DEFAULT_DSN imported from config.settings — do NOT redefine here.

SOURCES = [
    "pncp",
    "dom_sc",
    "doe_sc",
    "pcp",
    "pcp_v2",
    "compras_gov",
    "sc_compras",
    "contracts",
    "transparencia",
    "tce_sc",
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_conn() -> Any:
    """Create a database connection using DEFAULT_DSN."""
    import psycopg2

    return psycopg2.connect(DEFAULT_DSN)


def _start_ingestion_run(conn: Any, source: str) -> int:
    """Record the start of an ingestion run and return its ID."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ingestion_runs (source, status) VALUES (%s, 'running') RETURNING id",
        (source,),
    )
    run_id = int(cur.fetchone()[0])
    conn.commit()
    cur.close()
    return run_id


def _finish_ingestion_run(
    conn: Any,
    run_id: int,
    fetched: int,
    upserted: int,
    covered: int,
    status: str = "completed",
    error: str = "",
) -> None:
    """Record the completion of an ingestion run with stats."""
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


def load_entities(conn: Any, within_200km_only: bool = False) -> list[dict[str, Any]]:
    """Load all active SC public entities from the database.

    Args:
        conn: Database connection.
        within_200km_only: If True, only load entities within 200km radius.

    Returns:
        List of entity dicts with keys ``id``, ``razao_social``, ``cnpj_8``,
        ``municipio``, ``codigo_ibge``, ``natureza_juridica``, ``raio_200km``.
    """
    cur = conn.cursor()
    sql = (
        "SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, "
        "natureza_juridica, raio_200km FROM sc_public_entities WHERE is_active = TRUE"
    )
    if within_200km_only:
        sql += " AND raio_200km = TRUE"
    sql += " ORDER BY id"
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    entities = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return entities


# ---------------------------------------------------------------------------
# Crawler loading
# ---------------------------------------------------------------------------


def load_crawler(source: str) -> Any | None:
    """Dynamically load crawler module for a source.

    Args:
        source: Data source tag (``pncp``, ``dom_sc``, etc.).

    Returns:
        Crawler module with ``crawl(mode)`` and ``transform(records)``,
        or ``None`` if the source is not implemented.
    """
    module_map = {
        "pncp": "pncp_crawler_adapter",
        "dom_sc": "dom_sc_crawler",
        "doe_sc": "doe_sc_crawler",
        "pcp": "pcp_crawler",
        "pcp_v2": "pcp_crawler",
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
        return importlib.import_module(f"scripts.crawl.{mod_name}")
    except ImportError as e:
        logger.warning("Cannot import %s: %s", mod_name, e)
        return None


# ---------------------------------------------------------------------------
# Main crawl orchestration
# ---------------------------------------------------------------------------


def crawl_source(
    source: str,
    entities: list[dict[str, Any]],
    mode: str = "full",
    dsn: str | None = None,
) -> dict[str, Any]:
    """Run full crawl pipeline for a single source.

    Pipeline phases:
        1. Crawl — fetch raw records from source
        2. Transform — normalize to unified schema
        3. Upsert — insert/update via database RPC
        4. Entity Match — associate bids with entities (non-contracts only)

    Args:
        source: Data source tag.
        entities: List of entity dicts from ``load_entities()``.
        mode: Crawl mode (``full``, ``incremental``, ``dry-run``).
        dsn: Optional DSN override (defaults to ``DEFAULT_DSN``).

    Returns:
        Dict with keys ``source``, ``status``, ``fetched``, ``upserted``,
        ``matched``, and optionally ``error``.
    """
    global DEFAULT_DSN
    if dsn:
        DEFAULT_DSN = dsn

    conn = _get_conn()

    # --- Checkpoint check (TD-5.2) ---
    # In incremental mode, skip source if already completed today
    if mode == "incremental":
        if is_crawl_completed_today(conn, source):
            conn.close()
            logger.info("crawl_source: %s — checkpoint OK (already completed today), skipping", source)
            return {
                "source": source,
                "status": "ok",
                "fetched": 0,
                "upserted": 0,
                "matched": 0,
                "skipped_by_checkpoint": True,
            }

    run_id = _start_ingestion_run(conn, source)
    fetched = 0
    upserted = 0
    matched = 0
    error = ""

    try:
        # Try to import source-specific crawler
        crawler = load_crawler(source)
        if crawler is None:
            error = f"Crawler not implemented: {source}"
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "failed", error)
            conn.close()
            return {"source": source, "status": "skipped", "error": error}

        # Phase 1: Crawl
        logger.info("Crawling %s (%s)...", source, mode)
        raw_records = crawler.crawl(mode)
        fetched = len(raw_records)
        logger.info("Fetched: %d records", fetched)

        if not raw_records:
            _finish_ingestion_run(conn, run_id, 0, 0, 0, "completed")
            save_checkpoint(conn, source, last_date=date.today(), records_fetched=0)
            conn.close()
            return {"source": source, "status": "ok", "fetched": 0, "upserted": 0, "matched": 0}

        # Phase 2: Transform to unified schema
        db_source = "pncp_contracts" if source == "contracts" else source
        records = crawler.transform(raw_records)
        records = [{**r, "source": db_source} for r in records]

        # Phase 3: Upsert via RPC
        cur = conn.cursor()
        try:
            if source == "contracts":
                cur.execute(
                    "SELECT * FROM upsert_pncp_supplier_contracts(%s)",
                    (json.dumps(records),),
                )
            else:
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

        logger.info(
            "Upserted: %d new, %d duplicates",
            upserted,
            fetched - upserted,
        )

        # Phase 4: Entity matching (only for pncp_raw_bids sources)
        matched = 0
        if source != "contracts":
            from scripts.matching.entity_matcher import match_entities_cascade

            match_stats = match_entities_cascade(conn, source, entities)
            matched = match_stats["cnpj"] + match_stats["name_normalized"] + match_stats["fuzzy"]
            logger.info(
                "Matched: %d (CNPJ: %d, name: %d, fuzzy: %d, unmatched: %d)",
                matched,
                match_stats["cnpj"],
                match_stats["name_normalized"],
                match_stats["fuzzy"],
                match_stats["unmatched"],
            )
        else:
            logger.info("Entity matching skipped (contracts source uses pncp_supplier_contracts)")

        _finish_ingestion_run(conn, run_id, fetched, upserted, matched, "completed")
        save_checkpoint(conn, source, last_date=date.today(), records_fetched=fetched)
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
        except Exception:  # noqa: S110  # Best-effort: ingestion run reporting in error handler
            pass
        try:
            conn.close()
        except Exception:  # noqa: S110  # Best-effort: connection cleanup in error handler
            pass
        return {"source": source, "status": "failed", "error": error}
