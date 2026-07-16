"""Sync wrapper for watermark operations — bridges async WatermarkManager to sync adapters.

Provides sync entry points:

    watermark_commit(source, scope_key, value, run_id)
    watermark_read(source, scope_key=None)
    watermark_next_page(source, overlap=1)

Uses ``config.settings.DEFAULT_DSN`` for DB connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config.settings import DEFAULT_DSN
from scripts.crawl.watermark import WatermarkManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton WatermarkManager instance (lazy)
# ---------------------------------------------------------------------------

_wm: WatermarkManager | None = None


def _get_wm() -> WatermarkManager:
    global _wm
    if _wm is None:
        _wm = WatermarkManager(conn_string=DEFAULT_DSN)
    return _wm


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


def watermark_commit(
    source: str,
    scope_key: str = "page",
    value: str = "",
    run_id: str | None = None,
) -> bool:
    """Commit a watermark for a source scope. Returns True on success."""
    try:
        wm = _get_wm()
        _run_async(wm.commit(source, scope_key, value, run_id=run_id))
        logger.debug("watermark committed: source=%s %s=%s", source, scope_key, value)
        return True
    except Exception as e:
        logger.error("watermark_commit failed for source=%s: %s", source, e)
        return False


def watermark_read(
    source: str,
    scope_key: str = "page",
) -> str | None:
    """Read the last committed watermark value for a source scope."""
    try:
        wm = _get_wm()
        return _run_async(wm.get_last(source, scope_key=scope_key))
    except Exception as e:
        logger.error("watermark_read failed for source=%s: %s", source, e)
        return None


def watermark_next_page(source: str, overlap: int = 1) -> int:
    """Return the next page to crawl (0 = start from beginning)."""
    last = watermark_read(source, scope_key="page")
    if last is None:
        return 0
    try:
        return max(0, int(last) - overlap)
    except (ValueError, TypeError):
        return 0


def watermark_reset(source: str) -> bool:
    """Reset watermark for a source (for restart)."""
    try:
        wm = _get_wm()
        _run_async(wm.reset(source))
        return True
    except Exception as e:
        logger.error("watermark_reset failed for source=%s: %s", source, e)
        return False
