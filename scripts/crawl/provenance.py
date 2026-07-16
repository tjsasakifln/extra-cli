"""Provenance tracker for crawl pipeline runs.

Provides:
- ``ProvenanceTracker``: Start, complete, and fail pipeline runs.
-``FreshnessChecker``: Evaluate source freshness based on last run time.
- ``DedupChecker``: Content-hash based dedup.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.crawl.metrics import CRAWL_RECORDS_TOTAL, CRAWL_ERRORS_TOTAL, CRAWL_DURATION

logger = logging.getLogger(__name__)

# SLA definitions in hours per source
DEFAULT_SLA_HOURS = 48
SOURCE_SLA: dict[str, int] = {
    "pncp": 24,
    "pcp": 48,
    "compras_gov": 48,
    "ciga_ckan": 168,  # weekly
    "tce_sc": 72,
    "doe_sc": 72,
    "dom_sc": 72,
    "sc_compras": 48,
    "contracts": 48,
    "transparencia": 72,
    "mides_bigquery": 168,  # weekly
}


class ProvenanceTracker:
    """Tracks crawl pipeline runs with full provenance.

    Parameters
    ----------
    conn_string : str
        PostgreSQL connection string.
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

    async def start_run(
        self,
        run_id: str,
        source: str,
        mode: str = "full",
        params: dict[str, Any] | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> None:
        """Record the start of a pipeline run."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_runs
                        (run_id, source, mode, params, started_at, status, period_start, period_end)
                    VALUES (%s, %s, %s, %s::jsonb, NOW(), 'running', %s::date, %s::date)
                    """,
                    (
                        run_id,
                        source,
                        mode,
                        json.dumps(params) if params else None,
                        period_start,
                        period_end,
                    ),
                )
            conn.commit()
            logger.info("Run started: %s source=%s mode=%s", run_id, source, mode)
        except Exception as e:
            conn.rollback()
            logger.error("Failed to start run %s: %s", run_id, e)
            raise
        finally:
            self._put_conn(conn)

    async def complete_run(
        self,
        run_id: str,
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
        """Mark a pipeline run as completed with execution stats."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'completed',
                        completed_at = NOW(),
                        records_fetched = %s,
                        records_deduplicated = %s,
                        records_upserted = %s,
                        records_dlq = %s,
                        records_failed = %s,
                        pages_planned = %s,
                        pages_completed = %s,
                        watermarks_committed = %s,
                        duration_ms = %s
                    WHERE run_id = %s
                    """,
                    (
                        records_fetched,
                        records_deduplicated,
                        records_upserted,
                        records_dlq,
                        records_failed,
                        pages_planned,
                        pages_completed,
                        watermarks_committed,
                        duration_ms,
                        run_id,
                    ),
                )
            conn.commit()
            logger.info(
                "Run completed: %s fetched=%d upserted=%d dlq=%d in %dms",
                run_id, records_fetched, records_upserted, records_dlq, duration_ms,
            )
        except Exception as e:
            conn.rollback()
            logger.error("Failed to complete run %s: %s", run_id, e)
            raise
        finally:
            self._put_conn(conn)

    async def fail_run(
        self,
        run_id: str,
        error_message: str,
        records_fetched: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """Mark a pipeline run as failed."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = %s,
                        records_fetched = %s,
                        duration_ms = %s
                    WHERE run_id = %s
                    """,
                    (error_message[:2000], records_fetched, duration_ms, run_id),
                )
            conn.commit()
            logger.error("Run failed: %s — %s", run_id, error_message[:200])
        except Exception as e:
            conn.rollback()
            logger.error("Failed to record failure for run %s: %s", run_id, e)
            raise
        finally:
            self._put_conn(conn)

    async def get_run(self, run_id: str) -> dict | None:
        """Get details of a specific run."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pipeline_runs WHERE run_id = %s",
                    (run_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put_conn(conn)

    async def get_latest_run(self, source: str) -> dict | None:
        """Get the most recent completed or failed run for a source."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM pipeline_runs
                    WHERE source = %s
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (source,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put_conn(conn)


class DedupChecker:
    """Content-hash based dedup.

    Usage::

        dedup = DedupChecker(conn_string)
        is_dup = await dedup.is_duplicate(content_hash)
        if not is_dup:
            await dedup.record(content_hash, source, run_id)
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

    @staticmethod
    def compute_hash(data: dict[str, Any]) -> str:
        """Compute a deterministic content hash for a record.

        Uses SHA-256 of sorted JSON.
        """
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def is_duplicate(self, content_hash: str) -> bool:
        """Check if a content hash already exists."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM record_hashes WHERE content_hash = %s",
                    (content_hash,),
                )
                return cur.fetchone() is not None
        finally:
            self._put_conn(conn)

    async def record(self, content_hash: str, source: str, run_id: str) -> bool:
        """Record a content hash. Returns True if inserted, False if duplicate."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO record_hashes (content_hash, source, run_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (content_hash)
                    DO UPDATE SET
                        last_seen_at = NOW(),
                        seen_count = record_hashes.seen_count + 1
                    RETURNING seen_count
                    """,
                    (content_hash, source, run_id),
                )
                seen_count = cur.fetchone()[0]
            conn.commit()
            return seen_count == 1  # True if first time
        except Exception as e:
            conn.rollback()
            logger.error("Failed to record hash: %s", e)
            raise
        finally:
            self._put_conn(conn)


class FreshnessChecker:
    """Check and evaluate source freshness.

    Uses the SOURCE_SLA dictionary to determine acceptable freshness windows.
    """

    def __init__(
        self,
        tracker: ProvenanceTracker,
    ):
        self._tracker = tracker

    def get_sla_hours(self, source: str) -> int:
        """Get SLA in hours for a source."""
        return SOURCE_SLA.get(source, DEFAULT_SLA_HOURS)

    async def is_fresh(self, source: str) -> tuple[bool, dict | None]:
        """Check if a source's latest run is within SLA.

        Returns
        -------
        tuple[bool, dict | None]
            (is_fresh, latest_run_info)
        """
        latest = await self._tracker.get_latest_run(source)
        if latest is None:
            return False, None

        sla_hours = self.get_sla_hours(source)
        completed_at = latest.get("completed_at")
        if completed_at is None:
            return False, latest

        now = datetime.now(timezone.utc)
        age_hours = (now - completed_at).total_seconds() / 3600
        return age_hours <= sla_hours, latest

    async def get_freshness_report(self, sources: list[str] | None = None) -> dict[str, dict]:
        """Get freshness report for multiple sources.

        Returns dict mapping source name to freshness status.
        """
        check_sources = sources or list(SOURCE_SLA.keys())
        report = {}
        for source in check_sources:
            is_fresh, latest = await self.is_fresh(source)
            sla_hours = self.get_sla_hours(source)
            report[source] = {
                "fresh": is_fresh,
                "sla_hours": sla_hours,
                "latest_run": latest["run_id"] if latest else None,
                "latest_completed_at": str(latest["completed_at"]) if latest and latest.get("completed_at") else None,
                "status": "fresh" if is_fresh else "stale" if latest else "never_crawled",
            }
        return report
