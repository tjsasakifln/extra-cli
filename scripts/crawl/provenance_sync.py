"""Sync wrapper for ProvenanceTracker — bridges async tracker to sync adapters.

Provides sync entry points:

    provenance_start(source, mode, params=None)
    provenance_complete(run_id, records_fetched, records_upserted, error_count)
    provenance_fail(run_id, error_message)

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
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures
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
    source: str,
    mode: str = "full",
    params: dict[str, Any] | None = None,
) -> str | None:
    """Start a provenance run. Returns run_id string or None on failure."""
    try:
        tracker = _get_tracker()
        run_id = f"{source}-{int(time.time())}"
        _run_async(tracker.start_run(run_id, source, mode=mode, params=params))
        logger.debug("provenance started: source=%s run_id=%s", source, run_id)
        return run_id
    except Exception as e:
        logger.error("provenance_start failed for source=%s: %s", source, e)
        return None


def provenance_complete(
    run_id: str,
    source: str,
    records_fetched: int = 0,
    records_upserted: int = 0,
    error_count: int = 0,
) -> bool:
    """Mark a provenance run as completed successfully."""
    try:
        tracker = _get_tracker()
        _run_async(tracker.complete_run(run_id, source, records_fetched, records_upserted, error_count))
        return True
    except Exception as e:
        logger.error("provenance_complete failed for run=%s: %s", run_id, e)
        return False


def provenance_fail(
    run_id: str,
    source: str,
    error_message: str = "",
    records_fetched: int = 0,
) -> bool:
    """Mark a provenance run as failed."""
    try:
        tracker = _get_tracker()
        _run_async(tracker.fail_run(run_id, source, error_message, records_fetched))
        return True
    except Exception as e:
        logger.error("provenance_fail failed for run=%s: %s", run_id, e)
        return False
