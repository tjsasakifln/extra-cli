"""Sync wrapper for ProvenanceTracker — bridges async tracker to sync adapters.

Provides sync entry points:

    provenance_start(source=source, mode=mode, params=None)
    provenance_complete(run_id=run_id, source=source, records_fetched=count)
    provenance_fail(run_id=run_id, source=source, error_message=message)

Uses ``config.settings.DEFAULT_DSN`` for DB connection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from config.settings import DEFAULT_DSN
from scripts.crawl.provenance import ProvenanceTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton tracker instance (lazy)
# ---------------------------------------------------------------------------

_tracker: ProvenanceTracker | None = None


def _get_tracker() -> ProvenanceTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProvenanceTracker(conn_string=DEFAULT_DSN)
    return _tracker


def _run_async(coro):
    """Execute a coroutine synchronously."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

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


def provenance_start(
    *,
    source: str,
    mode: str = "full",
    params: dict[str, Any] | None = None,
) -> str:
    """Start a provenance run or raise if the running row cannot be persisted."""
    tracker = _get_tracker()
    run_id = f"{source}-{time.time_ns()}"
    _run_async(tracker.start_run(run_id, source, mode=mode, params=params))
    logger.debug("provenance started: source=%s run_id=%s", source, run_id)
    return run_id


def provenance_complete(
    *,
    run_id: str,
    source: str,
    records_fetched: int = 0,
    records_deduplicated: int = 0,
    records_upserted: int = 0,
    records_dlq: int = 0,
    records_failed: int = 0,
    pages_planned: int = 0,
    pages_completed: int = 0,
    watermarks_committed: int = 0,
    duration_ms: int = 0,
) -> None:
    """Persist a successful terminal state or propagate the persistence error."""
    tracker = _get_tracker()
    _run_async(
        tracker.complete_run(
            run_id,
            source=source,
            records_fetched=records_fetched,
            records_deduplicated=records_deduplicated,
            records_upserted=records_upserted,
            records_dlq=records_dlq,
            records_failed=records_failed,
            pages_planned=pages_planned,
            pages_completed=pages_completed,
            watermarks_committed=watermarks_committed,
            duration_ms=duration_ms,
        )
    )


def provenance_fail(
    *,
    run_id: str,
    source: str,
    error_message: str,
    records_fetched: int = 0,
    records_deduplicated: int = 0,
    records_upserted: int = 0,
    records_dlq: int = 0,
    records_failed: int = 0,
    pages_planned: int = 0,
    pages_completed: int = 0,
    watermarks_committed: int = 0,
    duration_ms: int = 0,
) -> None:
    """Persist a failed terminal state or propagate the persistence error."""
    tracker = _get_tracker()
    _run_async(
        tracker.fail_run(
            run_id,
            source=source,
            error_message=error_message,
            records_fetched=records_fetched,
            records_deduplicated=records_deduplicated,
            records_upserted=records_upserted,
            records_dlq=records_dlq,
            records_failed=records_failed,
            pages_planned=pages_planned,
            pages_completed=pages_completed,
            watermarks_committed=watermarks_committed,
            duration_ms=duration_ms,
        )
    )
