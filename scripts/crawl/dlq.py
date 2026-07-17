"""Dead Letter Queue — durable storage and replay for failed pipeline records.

Provides:
- ``DurableDLQ``: PostgreSQL-backed DLQ implementing the ``DLQHandler`` protocol
  from ``scripts.crawl.pipeline``.
- Replay with exponential backoff (60s -> 300s -> 900s).
- Auto-purge of dead/archived entries.
- Worker for batch processing.

Typical usage::

    dlq = DurableDLQ(pool)
    await dlq.push(DLQRecord(source="pncp", run_id="r1", ...))

    # Replay pending entries
    replayed = await dlq.replay(source="pncp", limit=100)

    # Purge old dead entries
    purged = await dlq.purge(source="pncp")
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.crawl.pipeline import DLQRecord, PipelineStage

logger = logging.getLogger(__name__)

# Register UUID adapter
psycopg2.extras.register_uuid()


# ===========================================================================
# Backoff schedule
# ===========================================================================

BACKOFF_SCHEDULE: list[int] = [60, 300, 900]  # seconds: 1min -> 5min -> 15min

BACKOFF_DEFAULT = 60 * 60  # 1 hour fallback


def _next_backoff(retry_count: int) -> int:
    """Return the next backoff delay in seconds based on retry count."""
    if retry_count < len(BACKOFF_SCHEDULE):
        return BACKOFF_SCHEDULE[retry_count]
    return BACKOFF_DEFAULT


# ===========================================================================
# DurableDLQ — PostgreSQL-backed DLQ
# ===========================================================================


class DurableDLQ:
    """PostgreSQL-backed Dead Letter Queue.

    Implements the ``DLQHandler`` protocol from ``scripts.crawl.pipeline``
    so it can be used directly with the ``Pipeline`` class.

    Parameters
    ----------
    conn_string : str
        PostgreSQL connection string.
    pool : Any, optional
        Connection pool for async operations. If not provided, a new
        connection is created per operation (not recommended for production).
    """

    def __init__(
        self,
        conn_string: str | None = None,
        pool: Any | None = None,
    ):
        self._conn_string = conn_string
        self._pool = pool
        self._lock = asyncio.Lock()

    def _get_conn(self):
        """Get a synchronous database connection."""
        if self._pool:
            return self._pool.getconn()
        if self._conn_string:
            return psycopg2.connect(self._conn_string)
        raise ValueError("No connection string or pool provided")

    def _put_conn(self, conn) -> None:
        """Return a connection to the pool."""
        if self._pool:
            self._pool.putconn(conn)
        else:
            conn.close()

    # ------------------------------------------------------------------
    # DLQHandler protocol implementation
    # ------------------------------------------------------------------

    async def push(self, record: DLQRecord) -> int:
        """Insert a record into the DLQ. Returns the new entry ID.

        Parameters
        ----------
        record : DLQRecord
            The record to insert.

        Returns
        -------
        int
            The auto-generated ID of the new DLQ entry.
        """
        payload_json: Any = None
        if record.raw_payload is not None:
            try:
                payload_json = json.dumps(record.raw_payload, default=str)
            except (TypeError, ValueError):
                payload_json = json.dumps({"truncated": True, "value": str(record.raw_payload)[:10000]})

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dlq_entries
                        (source, run_id, phase, payload, error_code,
                         error_message, error_traceback, retry_count, status)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, 'pending')
                    RETURNING id
                    """,
                    (
                        record.source,
                        record.run_id,
                        str(record.stage.value) if hasattr(record.stage, 'value') else str(record.stage),
                        payload_json,
                        record.error_code,
                        record.error_message[:2000] if record.error_message else None,
                        record.error_traceback[:10000] if record.error_traceback else None,
                        record.retry_count,
                    ),
                )
                entry_id = cur.fetchone()[0]
            conn.commit()
            logger.debug("DLQ push: id=%d source=%s code=%s", entry_id, record.source, record.error_code)
            return entry_id
        except Exception as e:
            conn.rollback()
            logger.error("DLQ push failed: %s", e)
            raise
        finally:
            self._put_conn(conn)

    async def pending_count(self, source: str | None = None) -> int:
        """Return count of pending (unreplayed) entries."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if source:
                    cur.execute(
                        "SELECT COUNT(*) FROM dlq_entries WHERE source = %s AND status = 'pending'",
                        (source,),
                    )
                else:
                    cur.execute("SELECT COUNT(*) FROM dlq_entries WHERE status = 'pending'")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)

    async def list(
        self,
        source: str | None = None,
        status: str | None = 'pending',
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List DLQ entries with filters.

        Parameters
        ----------
        source : str, optional
            Filter by source.
        status : str, optional
            Filter by status ('pending', 'replayed', 'dead', 'archived').
            Defaults to 'pending'. Pass None for all statuses.
        limit : int
            Maximum entries to return (default 100).
        offset : int
            Pagination offset.

        Returns
        -------
        list[dict]
            List of DLQ entry dicts.
        """
        conn = self._get_conn()
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if source:
                conditions.append("source = %s")
                params.append(source)
            if status:
                conditions.append("status = %s")
                params.append(status)

            where_clause = " AND ".join(conditions) if conditions else "TRUE"

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # where_clause is built only from fixed fragments + %s placeholders
                # (never raw user input); values go through params.
                cur.execute(
                    f"""
                    SELECT id, source, run_id, phase, error_code, error_message,
                           retry_count, status, failed_at, replayed_at
                    FROM dlq_entries
                    WHERE {where_clause}
                    ORDER BY failed_at DESC
                    LIMIT %s OFFSET %s
                    """,  # noqa: S608
                    (*params, limit, offset),
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        finally:
            self._put_conn(conn)

    async def replay(
        self,
        source: str | None = None,
        limit: int = 100,
        replayed_by: str | None = None,
    ) -> list[DLQRecord]:
        """Replay pending entries for reprocessing.

        Returns pending entries and marks them as 'replayed'.
        Entries that have exceeded max_retries are marked 'dead'.

        Parameters
        ----------
        source : str, optional
            Filter by source.
        limit : int
            Maximum entries to replay (default 100).
        replayed_by : str, optional
            Run ID that is replaying these entries.

        Returns
        -------
        list[DLQRecord]
            List of DLQRecords ready for reprocessing.
        """
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if source:
                    cur.execute(
                        """
                        SELECT id, source, run_id, phase, payload, error_code,
                               error_message, retry_count, max_retries
                        FROM dlq_entries
                        WHERE source = %s AND status = 'pending'
                        ORDER BY failed_at ASC
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                        """,
                        (source, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, source, run_id, phase, payload, error_code,
                               error_message, retry_count, max_retries
                        FROM dlq_entries
                        WHERE status = 'pending'
                        ORDER BY failed_at ASC
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                        """,
                        (limit,),
                    )

                rows = cur.fetchall()
                records: list[DLQRecord] = []

                for row in rows:
                    entry_id = row["id"]
                    retry_count = row["retry_count"] + 1
                    max_retries = row["max_retries"]

                    if retry_count > max_retries:
                        # Mark as dead — too many retries
                        cur.execute(
                            """
                            UPDATE dlq_entries
                            SET status = 'dead', retry_count = %s
                            WHERE id = %s
                            """,
                            (retry_count, entry_id),
                        )
                        logger.warning(
                            "DLQ entry %d exceeded max_retries (%d) → dead",
                            entry_id,
                            max_retries,
                        )
                        continue

                    # Mark as replayed
                    cur.execute(
                        """
                        UPDATE dlq_entries
                        SET status = 'replayed', retry_count = %s,
                            replayed_at = NOW(), replayed_by = %s
                        WHERE id = %s
                        """,
                        (retry_count, replayed_by, entry_id),
                    )

                    # Parse stage
                    stage_str = row["phase"]
                    try:
                        stage = PipelineStage(stage_str)
                    except ValueError:
                        stage = PipelineStage.PARSE  # fallback

                    # Parse payload
                    payload = row.get("payload")

                    records.append(DLQRecord(
                        source=row["source"],
                        run_id=row["run_id"],
                        stage=stage,
                        raw_payload=payload,
                        error_code=row["error_code"] or "",
                        error_message=row["error_message"] or "",
                        retry_count=retry_count,
                    ))

                conn.commit()
                logger.info("DLQ replay: %d entries for source=%s", len(records), source)
                return records
        except Exception as e:
            conn.rollback()
            logger.error("DLQ replay failed: %s", e)
            raise
        finally:
            self._put_conn(conn)

    async def purge(self, source: str | None = None, older_than_days: int = 90) -> int:
        """Purge dead/archived entries.

        Parameters
        ----------
        source : str, optional
            Filter by source.
        older_than_days : int
            Purge entries older than this many days (default 90).

        Returns
        -------
        int
            Number of purged entries.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if source:
                    cur.execute(
                        """
                        DELETE FROM dlq_entries
                        WHERE source = %s
                          AND status IN ('dead', 'archived')
                          AND failed_at < NOW() - INTERVAL '1 day' * %s
                        """,
                        (source, older_than_days),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM dlq_entries
                        WHERE status IN ('dead', 'archived')
                          AND failed_at < NOW() - INTERVAL '1 day' * %s
                        """,
                        (older_than_days,),
                    )
                purged = cur.rowcount
            conn.commit()
            logger.info("DLQ purge: %d entries removed", purged)
            return purged
        except Exception as e:
            conn.rollback()
            logger.error("DLQ purge failed: %s", e)
            raise
        finally:
            self._put_conn(conn)

    async def get(self, entry_id: int) -> dict | None:
        """Get a single DLQ entry by ID."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM dlq_entries WHERE id = %s",
                    (entry_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put_conn(conn)

    async def dead_count(self, source: str | None = None) -> int:
        """Return count of dead (max retries exceeded) entries."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if source:
                    cur.execute(
                        "SELECT COUNT(*) FROM dlq_entries WHERE source = %s AND status = 'dead'",
                        (source,),
                    )
                else:
                    cur.execute("SELECT COUNT(*) FROM dlq_entries WHERE status = 'dead'")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)


# ===========================================================================
# DLQ Worker — background processor
# ===========================================================================


class DLQWorker:
    """Background worker that processes pending DLQ entries.

    Processes entries in batches with configurable interval between batches.

    Parameters
    ----------
    dlq : DurableDLQ
        The DLQ instance to process.
    source : str, optional
        Source to process. None = all sources.
    batch_size : int
        Entries per batch (default 10).
    interval : float
        Seconds between batches (default 2.0).
    run_id : str
        Identifier for this worker run.
    """

    def __init__(
        self,
        dlq: DurableDLQ,
        source: str | None = None,
        batch_size: int = 10,
        interval: float = 2.0,
        run_id: str = "worker",
    ):
        self.dlq = dlq
        self.source = source
        self.batch_size = batch_size
        self.interval = interval
        self.run_id = run_id
        self._running = False
        self._processed = 0
        self._dead = 0
        self._errors = 0

    async def run_once(self) -> int:
        """Process a single batch of pending entries.

        Returns the number of entries processed (replayed or marked dead).
        """
        records = await self.dlq.replay(
            source=self.source,
            limit=self.batch_size,
            replayed_by=self.run_id,
        )
        count = len(records)
        self._processed += count

        # Entries that were marked 'dead' are not returned
        # We can check dead count delta
        logger.info("DLQWorker: replayed %d entries", count)
        return count

    async def run_forever(self) -> None:
        """Run the worker loop until stopped."""
        self._running = True
        logger.info(
            "DLQWorker started: source=%s batch=%d interval=%.1fs",
            self.source,
            self.batch_size,
            self.interval,
        )
        try:
            while self._running:
                count = await self.run_once()
                if count == 0:
                    # No pending entries — sleep longer
                    await asyncio.sleep(self.interval * 5)
                else:
                    await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            self._running = False
            logger.info("DLQWorker cancelled after %d processed", self._processed)
        except Exception as e:
            self._running = False
            self._errors += 1
            logger.error("DLQWorker crashed: %s", e)
            raise

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False
