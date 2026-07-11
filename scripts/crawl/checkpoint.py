"""Checkpoint management for PNCP ingestion pipeline.

Checkpoints track progress so that incremental crawls can resume where they
left off without re-fetching data that has not changed.

This module provides TWO APIs:

  1. **Synchronous (psycopg2)** — used by ``orchestrator.py`` (TD-5.2).
     Functions work with the ``ingestion_checkpoints`` table using
     ``(source, scope_key)`` as the primary key.

  2. **Asynchronous (Supabase)** — used by ``bids_crawler.py`` (deprecated
     ``ingestion.*`` package). Functions work with an older schema using
     ``(uf, modalidade_id, crawl_batch_id)`` as the key.

Tables used:
  - ingestion_checkpoints  — source-level resume records (migration 004)
  - ingestion_runs         — per-batch run metadata and final statistics
"""

import logging
from datetime import date
from typing import Any

from supabase_client import get_supabase, sb_execute

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synchronous API (psycopg2) — used by orchestrator.py (TD-5.2)
#
# These functions operate on ``ingestion_checkpoints`` with the PK
# ``(source, scope_key)``.  The orchestrator always uses
# ``scope_key="default"`` for source-level checkpoints.
# ---------------------------------------------------------------------------


def is_crawl_completed_today(
    conn: Any,
    source: str,
    scope_key: str = "default",
) -> bool:
    """Return True if *source* already has a successful checkpoint today.

    Args:
        conn: psycopg2 connection.
        source: Data source tag (``pncp``, ``dom_sc``, ...).
        scope_key: Scope identifier (default ``"default"``).

    Returns:
        ``True`` if a checkpoint with ``last_date = CURRENT_DATE`` exists
        for the given ``(source, scope_key)`` pair.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM ingestion_checkpoints "
            "WHERE source = %s AND scope_key = %s AND last_date = CURRENT_DATE",
            (source, scope_key),
        )
        return cur.fetchone() is not None
    except Exception as exc:
        logger.warning(
            "is_crawl_completed_today: source=%s scope=%s — %s: %s",
            source,
            scope_key,
            type(exc).__name__,
            exc,
        )
        return False
    finally:
        cur.close()


def save_checkpoint(
    conn: Any,
    source: str,
    scope_key: str = "default",
    last_date: date | None = None,
    records_fetched: int = 0,
) -> None:
    """Upsert a checkpoint for *source* using a synchronous psycopg2 connection.

    If a row already exists for ``(source, scope_key)`` its ``last_date``,
    ``records_fetched`` and ``updated_at`` are updated; otherwise a new row
    is inserted.

    Args:
        conn: psycopg2 connection.
        source: Data source tag.
        scope_key: Scope identifier (default ``"default"``).
        last_date: Date to record (defaults to ``date.today()``).
        records_fetched: Number of records fetched in this run.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO ingestion_checkpoints "
            "(source, scope_key, last_date, records_fetched, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW()) "
            "ON CONFLICT (source, scope_key) DO UPDATE SET "
            "  last_date = EXCLUDED.last_date, "
            "  records_fetched = EXCLUDED.records_fetched, "
            "  updated_at = NOW()",
            (source, scope_key, last_date or date.today(), records_fetched),
        )
        conn.commit()
        logger.debug(
            "save_checkpoint (sync): source=%s scope=%s last_date=%s records=%d",
            source,
            scope_key,
            last_date or date.today(),
            records_fetched,
        )
    except Exception as exc:
        logger.error(
            "save_checkpoint (sync): source=%s scope=%s — %s: %s",
            source,
            scope_key,
            type(exc).__name__,
            exc,
        )
        raise
    finally:
        cur.close()


def get_checkpoint(
    conn: Any,
    source: str,
    scope_key: str = "default",
) -> dict[str, Any] | None:
    """Return the full checkpoint row for *(source, scope_key)*, or ``None``.

    Args:
        conn: psycopg2 connection.
        source: Data source tag.
        scope_key: Scope identifier.

    Returns:
        A dict with keys matching the ``ingestion_checkpoints`` columns, or
        ``None`` if no checkpoint exists for the given pair.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT source, scope_key, last_page, last_date, last_id, "
            "       records_fetched, updated_at "
            "FROM ingestion_checkpoints "
            "WHERE source = %s AND scope_key = %s",
            (source, scope_key),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "source": row[0],
            "scope_key": row[1],
            "last_page": row[2],
            "last_date": row[3],
            "last_id": row[4],
            "records_fetched": row[5],
            "updated_at": row[6],
        }
    except Exception as exc:
        logger.warning(
            "get_checkpoint: source=%s scope=%s — %s: %s",
            source,
            scope_key,
            type(exc).__name__,
            exc,
        )
        return None
    finally:
        cur.close()


def delete_checkpoint(
    conn: Any,
    source: str,
    scope_key: str = "default",
) -> bool:
    """Remove the checkpoint for *(source, scope_key)*.

    Args:
        conn: psycopg2 connection.
        source: Data source tag.
        scope_key: Scope identifier.

    Returns:
        ``True`` if a row was deleted, ``False`` if it did not exist.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM ingestion_checkpoints "
            "WHERE source = %s AND scope_key = %s",
            (source, scope_key),
        )
        conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            logger.debug(
                "delete_checkpoint: source=%s scope=%s — deleted", source, scope_key
            )
        return deleted
    except Exception as exc:
        logger.warning(
            "delete_checkpoint: source=%s scope=%s — %s: %s",
            source,
            scope_key,
            type(exc).__name__,
            exc,
        )
        return False
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Checkpoint reads (async — Supabase, used by bids_crawler.py)
# ---------------------------------------------------------------------------


async def get_last_checkpoint(
    uf: str,
    modalidade: int,
    source: str = "pncp",
) -> date | None:
    """Return the last successfully crawled date for (uf, modalidade, source).

    Queries ingestion_checkpoints for the most recent row with
    status='completed' and returns its ``last_date`` as a Python date.

    Returns None if no checkpoint exists yet.
    """
    supabase = get_supabase()
    try:
        result = await sb_execute(
            supabase
            .table("ingestion_checkpoints")
            .select("last_date")
            .eq("uf", uf)
            .eq("modalidade_id", modalidade)
            .eq("source", source)
            .eq("status", "completed")
            .order("last_date", desc=True)
            .limit(1)
        )
        rows = result.data or []
        if rows:
            raw_date = rows[0].get("last_date")
            if raw_date:
                return _parse_date(raw_date)
        return None
    except Exception as exc:
        logger.warning(
            "get_last_checkpoint: uf=%s modalidade=%s — %s: %s",
            uf,
            modalidade,
            type(exc).__name__,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Checkpoint writes (async — Supabase, used by bids_crawler.py)
#
# NOTE: The async ``save_checkpoint`` is NOT defined here to avoid a
# name collision with the sync version (which is what ``orchestrator.py``
# imports). The ``bids_crawler.py`` obtains its async checkpoint functions
# from ``ingestion.checkpoint`` (deprecated ingestion package), NOT from
# ``scripts.crawl.checkpoint``.
# ---------------------------------------------------------------------------


async def mark_checkpoint_failed(
    uf: str,
    modalidade: int,
    crawl_batch_id: str,
    error_message: str,
    source: str = "pncp",
) -> None:
    """Mark the checkpoint for (uf, modalidade) as failed.

    Does not overwrite ``last_date`` — keeps the last known good date intact
    so that the next incremental crawl can recover from the right starting point.
    """
    supabase = get_supabase()
    try:
        payload: dict[str, Any] = {
            "uf": uf,
            "modalidade_id": modalidade,
            "source": source,
            "crawl_batch_id": crawl_batch_id,
            "status": "failed",
            "error_message": error_message[:2000],  # Truncate for column limit
        }
        await sb_execute(
            supabase
            .table("ingestion_checkpoints")
            .upsert(payload, on_conflict="source,uf,modalidade_id,crawl_batch_id"),
            category="write",
        )
        logger.warning(
            "mark_checkpoint_failed: uf=%s modalidade=%s batch=%s",
            uf,
            modalidade,
            crawl_batch_id,
        )
    except Exception as exc:
        logger.error(
            "mark_checkpoint_failed: uf=%s modalidade=%s — could not write failure record: %s: %s",
            uf,
            modalidade,
            type(exc).__name__,
            exc,
        )


# ---------------------------------------------------------------------------
# Ingestion run lifecycle (async — Supabase, used by bids_crawler.py)
# ---------------------------------------------------------------------------


async def create_ingestion_run(
    crawl_batch_id: str,
    run_type: str,
) -> None:
    """Insert a new ingestion_runs row at the start of a crawl.

    Args:
        crawl_batch_id: Unique identifier for this run (e.g. "full_20260325_050000").
        run_type: "full" or "incremental".
    """
    supabase = get_supabase()
    try:
        payload: dict[str, Any] = {
            "crawl_batch_id": crawl_batch_id,
            "run_type": run_type,
            "status": "running",
        }
        await sb_execute(
            supabase
            .table("ingestion_runs")
            .insert(payload),
            category="write",
        )
        logger.info(
            "create_ingestion_run: batch_id=%s type=%s — run started",
            crawl_batch_id,
            run_type,
        )
    except Exception as exc:
        # Non-fatal: monitoring is best-effort; crawl should proceed regardless
        logger.warning(
            "create_ingestion_run: could not insert run record — %s: %s",
            type(exc).__name__,
            exc,
        )


async def complete_ingestion_run(
    crawl_batch_id: str,
    *,
    status: str = "completed",
    total_fetched: int = 0,
    inserted: int = 0,
    updated: int = 0,
    unchanged: int = 0,
    ufs_completed: list[str] | None = None,
    ufs_failed: list[str] | None = None,
    error_message: str | None = None,
) -> None:
    """Update ingestion_runs with final statistics after a crawl completes.

    Args:
        crawl_batch_id: Run identifier to update.
        status: Final status — "completed", "failed", or "partial".
        total_fetched: Total raw records received from the API.
        inserted: New rows inserted into pncp_raw_bids.
        updated: Existing rows updated (content_hash changed).
        unchanged: Rows with no change (deduplicated).
        ufs_completed: List of UF codes successfully processed.
        ufs_failed: List of UF codes that encountered errors.
        error_message: Optional error string for failed/partial runs.
    """
    supabase = get_supabase()
    try:
        payload: dict[str, Any] = {
            "status": status,
            "total_fetched": total_fetched,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "ufs_completed": ufs_completed or [],
            "ufs_failed": ufs_failed or [],
        }
        if error_message:
            payload["error_message"] = error_message[:2000]

        await sb_execute(
            supabase
            .table("ingestion_runs")
            .update(payload)
            .eq("crawl_batch_id", crawl_batch_id),
            category="write",
        )
        logger.info(
            "complete_ingestion_run: batch_id=%s status=%s "
            "fetched=%d inserted=%d updated=%d unchanged=%d "
            "ufs_ok=%s ufs_fail=%s",
            crawl_batch_id,
            status,
            total_fetched,
            inserted,
            updated,
            unchanged,
            ufs_completed or [],
            ufs_failed or [],
        )
    except Exception as exc:
        logger.warning(
            "complete_ingestion_run: could not update run record — %s: %s",
            type(exc).__name__,
            exc,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_date(raw: Any) -> date | None:
    """Parse a date value from Supabase (string or date object)."""
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            # Handle "2026-03-25" or "2026-03-25T00:00:00"
            return date.fromisoformat(raw[:10])
        except ValueError:
            logger.warning("_parse_date: could not parse '%s' as a date", raw)
    return None
