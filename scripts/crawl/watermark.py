"""Watermark manager for resilient crawl resumption.

Provides:
- ``WatermarkManager``: Commit and query watermarks per source/page.
- Automatic overlap on resume (last committed page - 1).
- Stalled watermark detection (>2h in_progress).

Typical usage::

    wm = WatermarkManager(pool)
    await wm.commit("pncp", "page", "42", run_id="r1")
    last = await wm.get_last("pncp")  # Returns "42"
    next_page = await wm.get_next_page("pncp", overlap=1)  # Returns 41
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.crawl.metrics import WATERMARK_COMMITS_TOTAL

logger = logging.getLogger(__name__)


STALLED_THRESHOLD_SECONDS = 7200  # 2 hours


class WatermarkManager:
    """PostgreSQL-backed watermark manager for crawl progress tracking.

    Parameters
    ----------
    conn_string : str
        PostgreSQL connection string.
    pool : Any, optional
        Connection pool.
    """

    def __init__(
        self,
        conn_string: str | None = None,
        pool: Any | None = None,
    ):
        self._conn_string = conn_string
        self._pool = pool

    def _get_conn(self):
        if self._pool:
            return self._pool.getconn()
        if self._conn_string:
            return psycopg2.connect(self._conn_string)
        raise ValueError("No connection string or pool provided")

    def _put_conn(self, conn) -> None:
        if self._pool:
            self._pool.putconn(conn)
        else:
            conn.close()

    async def commit(
        self,
        source: str,
        watermark_type: str,
        watermark_value: str,
        run_id: str,
        scope_key: str = "default",
    ) -> int:
        """Commit a watermark progress marker.

        Parameters
        ----------
        source : str
            Source identifier.
        watermark_type : str
            Type of watermark ('page', 'date', 'entity', 'chunk').
        watermark_value : str
            The value (e.g., page number as string).
        run_id : str
            Run identifier.
        scope_key : str
            Scope within source (default 'default').

        Returns
        -------
        int
            The watermark ID.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT commit_watermark(%s, %s, %s, %s, %s)
                    """,
                    (source, scope_key, watermark_type, watermark_value, run_id),
                )
                wm_id = cur.fetchone()[0]
            conn.commit()
            WATERMARK_COMMITS_TOTAL.labels(source=source).inc()
            logger.debug(
                "Watermark committed: %s/%s=%s (run=%s)",
                source, watermark_type, watermark_value, run_id,
            )
            return wm_id
        except Exception as e:
            conn.rollback()
            logger.error("Watermark commit failed: %s", e)
            raise
        finally:
            self._put_conn(conn)

    async def get_last(
        self,
        source: str,
        watermark_type: str = "page",
        scope_key: str = "default",
    ) -> str | None:
        """Get the last committed watermark value for a source.

        Parameters
        ----------
        source : str
            Source identifier.
        watermark_type : str
            Type of watermark.
        scope_key : str
            Scope key.

        Returns
        -------
        str or None
            The last committed watermark value, or None if none exists.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT watermark_value FROM pipeline_watermarks
                    WHERE source = %s AND scope_key = %s
                      AND watermark_type = %s AND status = 'committed'
                    ORDER BY committed_at DESC
                    LIMIT 1
                    """,
                    (source, scope_key, watermark_type),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self._put_conn(conn)

    async def get_next_page(
        self,
        source: str,
        overlap: int = 1,
        scope_key: str = "default",
    ) -> int:
        """Get the next page number to crawl, with overlap.

        The overlap ensures no records are missed between runs:
        next_page = last_page - overlap, or 1 if no previous watermark.

        Parameters
        ----------
        source : str
            Source identifier.
        overlap : int
            Number of pages to overlap (default 1).
        scope_key : str
            Scope key.

        Returns
        -------
        int
            The page number to start from.
        """
        last = await self.get_last(source, watermark_type="page", scope_key=scope_key)
        if last is None:
            return 1
        try:
            last_page = int(last)
            return max(1, last_page - overlap)
        except (ValueError, TypeError):
            return 1

    async def mark_in_progress(
        self,
        source: str,
        run_id: str,
        watermark_type: str = "page",
        watermark_value: str = "0",
        scope_key: str = "default",
    ) -> None:
        """Mark a watermark as in_progress (crawl actively running)."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_watermarks
                        (source, scope_key, watermark_type, watermark_value, run_id, status)
                    VALUES (%s, %s, %s, %s, %s, 'in_progress')
                    ON CONFLICT (source, scope_key, watermark_type, watermark_value)
                    DO UPDATE SET status = 'in_progress', run_id = EXCLUDED.run_id
                    """,
                    (source, scope_key, watermark_type, watermark_value, run_id),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("Watermark mark_in_progress failed: %s", e)
            raise
        finally:
            self._put_conn(conn)

    async def check_stalled(self, source: str | None = None) -> list[dict]:
        """Find watermarks that have been 'in_progress' for >2 hours.

        Returns a list of stalled watermark dicts.
        """
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if source:
                    cur.execute(
                        """
                        SELECT source, scope_key, watermark_type, watermark_value, run_id, committed_at
                        FROM pipeline_watermarks
                        WHERE source = %s AND status = 'in_progress'
                          AND EXTRACT(EPOCH FROM (NOW() - committed_at)) > %s
                        """,
                        (source, STALLED_THRESHOLD_SECONDS),
                    )
                else:
                    cur.execute(
                        """
                        SELECT source, scope_key, watermark_type, watermark_value, run_id, committed_at
                        FROM pipeline_watermarks
                        WHERE status = 'in_progress'
                          AND EXTRACT(EPOCH FROM (NOW() - committed_at)) > %s
                        """,
                        (STALLED_THRESHOLD_SECONDS,),
                    )
                rows = cur.fetchall()
                stalled = [dict(r) for r in rows]
                if stalled:
                    logger.warning("Found %d stalled watermarks", len(stalled))
                return stalled
        finally:
            self._put_conn(conn)

    async def mark_stalled(self, source: str) -> int:
        """Mark in_progress watermarks as stalled for the given source.

        Returns the number of watermarks marked.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_watermarks
                    SET status = 'stalled'
                    WHERE source = %s AND status = 'in_progress'
                      AND EXTRACT(EPOCH FROM (NOW() - committed_at)) > %s
                    """,
                    (source, STALLED_THRESHOLD_SECONDS),
                )
                marked = cur.rowcount
            conn.commit()
            return marked
        except Exception as e:
            conn.rollback()
            logger.error("Watermark mark_stalled failed: %s", e)
            raise
        finally:
            self._put_conn(conn)
