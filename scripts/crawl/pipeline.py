"""Pipeline engine — fetch → parse → transform → upsert with DLQ routing.

Each stage is isolated: failures in parse/transform/upsert route the record
to the Dead Letter Queue (DLQ) while allowing the pipeline to continue.
Unhandled exceptions (non-DLQ-routable) trigger FAIL_CLOSED — the pipeline
aborts with no partial commit.

The DLQ is abstracted behind ``DLQHandler`` so the implementation can be
in-memory (testing) or database-backed (production, see DF-1B.1).
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ===========================================================================
# Stage definitions
# ===========================================================================


class PipelineStage(StrEnum):
    """Stages in the crawl pipeline."""

    FETCH = auto()
    PARSE = auto()
    TRANSFORM = auto()
    UPSERT = auto()


# ===========================================================================
# DLQ primitives
# ===========================================================================


@dataclass
class DLQRecord:
    """A single record queued for the Dead Letter Queue.

    Parameters
    ----------
    source : str
        Source identifier (e.g. ``"pncp"``, ``"pcp"``).
    run_id : str
        Unique identifier for the pipeline run.
    stage : PipelineStage
        The stage where the error occurred.
    raw_payload : Any
        The raw data that caused the error (may be truncated).
    error_code : str
        Machine-readable error code.
    error_message : str
        Human-readable error description.
    error_traceback : str, optional
        Full traceback for debugging.
    retry_count : int
        Number of retry attempts so far.
    """

    source: str
    run_id: str
    stage: PipelineStage
    raw_payload: Any = None
    error_code: str = ""
    error_message: str = ""
    error_traceback: str = ""
    retry_count: int = 0


class DLQHandler(Protocol):
    """Protocol for Dead Letter Queue implementations.

    Both ``InMemoryDLQ`` and the production ``PgDLQ`` (DF-1B.1) implement this.
    """

    async def push(self, record: DLQRecord) -> None:
        """Push a record to the DLQ."""
        ...

    async def pending_count(self, source: str | None = None) -> int:
        """Return count of pending (unreplayed) records."""
        ...

    async def replay(self, source: str | None = None, limit: int = 100) -> list[DLQRecord]:
        """Replay pending records for reprocessing."""
        ...

    async def purge(self, source: str | None = None) -> int:
        """Purge dead/archived records."""
        ...


class InMemoryDLQ:
    """In-memory DLQ implementation for testing.

    Stores all records in a list. Thread-safe via asyncio lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: list[DLQRecord] = []

    async def push(self, record: DLQRecord) -> None:
        async with self._lock:
            self._records.append(record)
            logger.debug("DLQ push: %s/%s — %s", record.source, record.stage, record.error_code)

    async def pending_count(self, source: str | None = None) -> int:
        async with self._lock:
            if source is None:
                return len(self._records)
            return sum(1 for r in self._records if r.source == source)

    async def replay(self, source: str | None = None, limit: int = 100) -> list[DLQRecord]:
        async with self._lock:
            matching = [r for r in self._records if r.source == (source or r.source)]
            replayable = matching[:limit]
            return replayable

    async def purge(self, source: str | None = None) -> int:
        async with self._lock:
            before = len(self._records)
            if source:
                self._records = [r for r in self._records if r.source != source]
            else:
                self._records.clear()
            return before - len(self._records)

    async def all(self) -> list[DLQRecord]:
        """Return all records (testing helper)."""
        async with self._lock:
            return list(self._records)


# ===========================================================================
# Pipeline context — carries state through one pipeline run
# ===========================================================================


@dataclass
class PipelineContext:
    """Mutable context for a single pipeline run.

    Attributes
    ----------
    source : str
        Source identifier.
    run_id : str
        Unique run identifier (generated at start).
    stage_results : dict
        Accumulated results per stage for logging/audit.
    should_stop : bool
        Set to True to request graceful stop.
    """

    source: str = ""
    run_id: str = ""
    stage_results: dict[str, Any] = field(default_factory=dict)
    should_stop: bool = False


# ===========================================================================
# Pipeline errors
# ===========================================================================


class PipelineError(Exception):
    """Base error for pipeline failures."""


class PipelineFailClosed(PipelineError):
    """Unhandled exception — pipeline aborted, no partial commit."""

    def __init__(self, stage: PipelineStage, message: str, original: Exception | None = None):
        super().__init__(message)
        self.stage = stage
        self.original = original


class StageError(PipelineError):
    """A recoverable error within a pipeline stage — record goes to DLQ."""

    def __init__(
        self,
        stage: PipelineStage,
        error_code: str,
        message: str,
        original: Exception | None = None,
    ):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.original = original


# ===========================================================================
# Stage function type aliases
# ===========================================================================

FetchFunc = Callable[..., Any]
ParseFunc = Callable[[Any], list[dict[str, Any]]]
TransformFunc = Callable[[dict[str, Any]], dict[str, Any] | None]
UpsertFunc = Callable[[list[dict[str, Any]]], int]


# ===========================================================================
# Pipeline
# ===========================================================================


class Pipeline:
    """Generic crawl pipeline with per-stage DLQ routing.

    Typical usage::

        pipeline = Pipeline(source="pncp", run_id="run-001")
        pipeline.set_stages(
            fetch=my_fetch_function,
            parse=my_parse_function,
            transform=my_transform,
            upsert=my_upsert_batch,
        )
        result = await pipeline.run(dlq=InMemoryDLQ(), params={"page": 1})

    Each record that fails parse/transform/upsert is pushed to the DLQ.
    Unhandled exceptions raise ``PipelineFailClosed``.
    """

    def __init__(
        self,
        source: str,
        run_id: str,
        ctx: PipelineContext | None = None,
    ):
        self.source = source
        self.run_id = run_id
        self.ctx = ctx or PipelineContext(source=source, run_id=run_id)
        self._fetch_fn: FetchFunc | None = None
        self._parse_fn: ParseFunc | None = None
        self._transform_fn: TransformFunc | None = None
        self._upsert_fn: UpsertFunc | None = None
        self._stats: dict[str, int] = {
            "fetched": 0,
            "parsed": 0,
            "transformed": 0,
            "upserted": 0,
            "dlq_routed": 0,
        }

    def set_stages(
        self,
        fetch: FetchFunc | None = None,
        parse: ParseFunc | None = None,
        transform: TransformFunc | None = None,
        upsert: UpsertFunc | None = None,
    ) -> None:
        """Register stage functions for this pipeline run."""
        if fetch is not None:
            self._fetch_fn = fetch
        if parse is not None:
            self._parse_fn = parse
        if transform is not None:
            self._transform_fn = transform
        if upsert is not None:
            self._upsert_fn = upsert

    # ------------------------------------------------------------------
    # Per-stage execution with DLQ routing
    # ------------------------------------------------------------------

    async def _run_fetch(self, dlq: DLQHandler, params: dict[str, Any]) -> Any:
        """Execute the fetch stage.

        Catches network/connection errors and routes to DLQ.
        Unhandled exceptions → FAIL_CLOSED.
        """
        if self._fetch_fn is None:
            raise PipelineFailClosed(PipelineStage.FETCH, "No fetch function registered")

        logger.info("Pipeline [%s] FETCH starting", self.source)
        try:
            result = await self._fetch_fn(**params) if asyncio.iscoroutinefunction(self._fetch_fn) else self._fetch_fn(**params)
            self._stats["fetched"] += 1
            self.ctx.stage_results["fetch"] = {"status": "ok"}
            return result
        except StageError:
            raise  # Already a DLQ-routable error
        except Exception as exc:
            logger.error("Pipeline [%s] FETCH unhandled: %s", self.source, exc)
            raise PipelineFailClosed(PipelineStage.FETCH, f"Fetch failed: {exc}", original=exc) from exc

    async def _run_parse(self, dlq: DLQHandler, raw_data: Any) -> list[dict[str, Any]]:
        """Parse raw data into records. Invalid records → DLQ."""
        if self._parse_fn is None:
            raise PipelineFailClosed(PipelineStage.PARSE, "No parse function registered")

        records: list[dict[str, Any]] = []
        raw_items = raw_data if isinstance(raw_data, list) else [raw_data]

        for item in raw_items:
            try:
                parsed = (
                    await self._parse_fn(item)
                    if asyncio.iscoroutinefunction(self._parse_fn)
                    else self._parse_fn(item)
                )
                if parsed is not None:
                    if isinstance(parsed, list):
                        records.extend(parsed)
                    else:
                        records.append(parsed)
            except StageError:
                raise  # Preserve explicit stage errors
            except Exception as exc:
                tb = traceback.format_exc()
                dlq_record = DLQRecord(
                    source=self.source,
                    run_id=self.run_id,
                    stage=PipelineStage.PARSE,
                    raw_payload=_truncate_payload(item),
                    error_code="parse_failed",
                    error_message=str(exc),
                    error_traceback=tb,
                )
                await dlq.push(dlq_record)
                self._stats["dlq_routed"] += 1
                logger.warning(
                    "Pipeline [%s] PARSE error → DLQ: %s",
                    self.source,
                    exc,
                )

        self._stats["parsed"] = len(records)
        self.ctx.stage_results["parse"] = {"total": len(records), "dlq": self._stats["dlq_routed"]}
        return records

    async def _run_transform(
        self,
        dlq: DLQHandler,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Transform each record. Missing-required-field → DLQ."""
        if self._transform_fn is None:
            raise PipelineFailClosed(PipelineStage.TRANSFORM, "No transform function registered")

        transformed: list[dict[str, Any]] = []
        for record in records:
            try:
                result = (
                    await self._transform_fn(record)
                    if asyncio.iscoroutinefunction(self._transform_fn)
                    else self._transform_fn(record)
                )
                if result is not None:
                    transformed.append(result)
            except StageError as e:
                dlq_record = DLQRecord(
                    source=self.source,
                    run_id=self.run_id,
                    stage=PipelineStage.TRANSFORM,
                    raw_payload=_truncate_payload(record),
                    error_code=e.error_code,
                    error_message=str(e),
                )
                await dlq.push(dlq_record)
                self._stats["dlq_routed"] += 1
            except Exception as exc:
                tb = traceback.format_exc()
                dlq_record = DLQRecord(
                    source=self.source,
                    run_id=self.run_id,
                    stage=PipelineStage.TRANSFORM,
                    raw_payload=_truncate_payload(record),
                    error_code="transform_failed",
                    error_message=str(exc),
                    error_traceback=tb,
                )
                await dlq.push(dlq_record)
                self._stats["dlq_routed"] += 1
                logger.warning("Pipeline [%s] TRANSFORM error → DLQ: %s", self.source, exc)

        self._stats["transformed"] = len(transformed)
        self.ctx.stage_results["transform"] = {"total": len(transformed), "dlq": self._stats["dlq_routed"]}
        return transformed

    async def _run_upsert(
        self,
        dlq: DLQHandler,
        records: list[dict[str, Any]],
    ) -> int:
        """Upsert records in batch. Constraint violations → DLQ."""
        if self._upsert_fn is None:
            raise PipelineFailClosed(PipelineStage.UPSERT, "No upsert function registered")

        # Process in batches for resilience
        upserted = 0
        for record in records:
            try:
                count = (
                    await self._upsert_fn([record])
                    if asyncio.iscoroutinefunction(self._upsert_fn)
                    else self._upsert_fn([record])
                )
                upserted += count
            except StageError as e:
                dlq_record = DLQRecord(
                    source=self.source,
                    run_id=self.run_id,
                    stage=PipelineStage.UPSERT,
                    raw_payload=_truncate_payload(record),
                    error_code=e.error_code,
                    error_message=str(e),
                )
                await dlq.push(dlq_record)
                self._stats["dlq_routed"] += 1
            except Exception as exc:
                tb = traceback.format_exc()
                dlq_record = DLQRecord(
                    source=self.source,
                    run_id=self.run_id,
                    stage=PipelineStage.UPSERT,
                    raw_payload=_truncate_payload(record),
                    error_code="upsert_failed",
                    error_message=str(exc),
                    error_traceback=tb,
                )
                await dlq.push(dlq_record)
                self._stats["dlq_routed"] += 1
                logger.warning("Pipeline [%s] UPSERT error → DLQ: %s", self.source, exc)

        self._stats["upserted"] = upserted
        self.ctx.stage_results["upsert"] = {"total": upserted, "dlq": self._stats["dlq_routed"]}
        return upserted

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(
        self,
        dlq: DLQHandler,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the full pipeline: fetch → parse → transform → upsert.

        Returns a result dict with stats and stage results.

        Raises
        ------
        PipelineFailClosed
            If any stage has an unhandled exception.
        """
        params = params or {}
        logger.info("Pipeline [%s] run=%s starting", self.source, self.run_id)

        try:
            # 1. FETCH
            raw_data = await self._run_fetch(dlq, params)

            # 2. PARSE
            if raw_data is None:
                logger.info("Pipeline [%s] fetch returned None — nothing to process", self.source)
                return self._get_result()

            records = await self._run_parse(dlq, raw_data)
            if not records:
                logger.info("Pipeline [%s] no records after parse", self.source)
                return self._get_result()

            # 3. TRANSFORM
            transformed = await self._run_transform(dlq, records)
            if not transformed:
                logger.info("Pipeline [%s] no records after transform", self.source)
                return self._get_result()

            # 4. UPSERT
            await self._run_upsert(dlq, transformed)

        except PipelineFailClosed:
            raise
        except Exception as exc:
            raise PipelineFailClosed(
                PipelineStage.FETCH,
                f"Pipeline unhandled error: {exc}",
                original=exc,
            ) from exc

        return self._get_result()

    def _get_result(self) -> dict[str, Any]:
        """Return pipeline execution result with stats."""
        return {
            "source": self.source,
            "run_id": self.run_id,
            "stats": dict(self._stats),
            "stage_results": dict(self.ctx.stage_results),
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


def _truncate_payload(payload: Any, max_bytes: int = 102400) -> Any:
    """Truncate payload to max_bytes for DLQ storage."""
    if payload is None:
        return None
    import json as _json

    try:
        serialized = _json.dumps(payload, default=str)
        if len(serialized.encode("utf-8")) > max_bytes:
            truncated = serialized[:max_bytes]
            return _json.loads(truncated)
        return payload
    except (TypeError, ValueError):
        return str(payload)[:max_bytes]
