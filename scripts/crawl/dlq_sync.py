"""Sync wrapper for DLQ operations — bridges async DurableDLQ to sync adapters.

Provides three entry points that sync adapters (pncp_crawler_adapter,
pcp_crawler, compras_gov_crawler, etc.) can call without needing
asyncio knowledge:

    dlq_write(source, run_id, stage, error, payload=None)
    dlq_count(source=None)
    dlq_list(source=None, limit=50)

Uses ``config.settings.DEFAULT_DSN`` for DB connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config.settings import DEFAULT_DSN
from scripts.crawl.dlq import DurableDLQ
from scripts.crawl.pipeline import DLQRecord, PipelineStage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton DLQ instance (lazy, reuses connection per process)
# ---------------------------------------------------------------------------

_dlq: DurableDLQ | None = None


def _get_dlq() -> DurableDLQ:
    global _dlq
    if _dlq is None:
        _dlq = DurableDLQ(conn_string=DEFAULT_DSN)
    return _dlq


def _run_async(coro):
    """Execute a coroutine synchronously using the running or new event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Already in an async context — use a new loop in a separate thread
    import threading

    result: list[Any] = []
    exc: list[BaseException] = []

    def _run():
        try:
            r = asyncio.run(coro)
            result.append(r)
        except BaseException as e:
            exc.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()
    if exc:
        raise exc[0]
    return result[0]


def dlq_write(
    source: str,
    run_id: str | None = None,
    stage: str = "fetch",
    error_code: str = "",
    error_message: str = "",
    error_traceback: str = "",
    payload: Any = None,
) -> int | None:
    """Write a failed record to the Dead Letter Queue.

    Returns the DLQ entry ID, or None on failure.
    """
    try:
        dlq = _get_dlq()
        record = DLQRecord(
            source=source,
            run_id=run_id or "unknown",
            stage=PipelineStage.FETCH if stage == "fetch" else (
                PipelineStage.PARSE if stage == "parse" else
                PipelineStage.TRANSFORM if stage == "transform" else
                PipelineStage.UPSERT if stage == "upsert" else
                PipelineStage.FETCH
            ),
            raw_payload=payload,
            error_code=error_code,
            error_message=error_message[:2000] if error_message else "",
            error_traceback=error_traceback[:10000] if error_traceback else "",
        )
        return _run_async(dlq.push(record))
    except Exception as e:
        logger.error("dlq_write failed for source=%s: %s", source, e)
        return None


def dlq_count(source: str | None = None) -> int:
    """Return count of pending DLQ entries, optionally filtered by source."""
    try:
        dlq = _get_dlq()
        return _run_async(dlq.pending_count(source))
    except Exception as e:
        logger.error("dlq_count failed: %s", e)
        return 0


def dlq_list(source: str | None = None, limit: int = 50) -> list[dict]:
    """List DLQ entries, optionally filtered by source."""
    try:
        dlq = _get_dlq()
        return _run_async(dlq.list(source=source, limit=limit))
    except Exception as e:
        logger.error("dlq_list failed: %s", e)
        return []


def dlq_replay(source: str | None = None, limit: int = 50) -> int:
    """Replay pending DLQ entries."""
    try:
        dlq = _get_dlq()
        return _run_async(dlq.replay(source=source, limit=limit))
    except Exception as e:
        logger.error("dlq_replay failed: %s", e)
        return 0


def dlq_purge(source: str | None = None, older_than_days: int = 90) -> int:
    """Purge dead DLQ entries older than specified days."""
    try:
        dlq = _get_dlq()
        return _run_async(dlq.purge(source=source, older_than_days=older_than_days))
    except Exception as e:
        logger.error("dlq_purge failed: %s", e)
        return 0
