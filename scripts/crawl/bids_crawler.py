"""
DEPRECATED — PNCP Data Lake crawler (BidsCrawler).

**Status:** DEPRECATED since 2026-07-11 (TD-3.2 — Eliminar Codigo Duplicado)
**Reason for deprecation:** Two competing PNCP crawler implementations existed:
the sync adapter (``pncp_crawler_adapter.py``) and this async BidsCrawler.
The sync adapter was chosen as the single implementation because it is simpler,
more testable, and avoids the ``asyncio`` / ``AsyncPNCPClient`` dependency chain
(which required the ``ingestion`` package that overlaps with the new ``scripts.crawl``
architecture).

**Replacement:** ``scripts/crawl/pncp_crawler_adapter.py`` (sync interface consumed
by ``monitor.py`` and ``orchestrator.py``).

**Rollback plan:**
  1. Restore the ``bids_crawler.py`` file and its dependencies:
     - ``pncp_client.py`` (AsyncPNCPClient)
     - ``ingestion._base.crawler`` (BaseCrawler, CrawlerResult, etc.)
     - ``ingestion.loader`` (bulk_upsert)
     - ``ingestion.transformer`` (transform_batch)
     - ``ingestion.checkpoint`` (checkpoint helpers)
     - ``ingestion.metrics`` (Prometheus metrics)
  2. Revert ``pncp_crawler_adapter.py`` to a thin wrapper delegating to BidsCrawler.
  3. Run ``pytest tests/`` to verify no regressions.
  4. Update ``monitor.py`` and ``orchestrator.py`` source mapping if needed.

================================================================================

PNCP Data Lake crawler — BidsCrawler.

Crawls PNCP licitacoes (bids) from ``/consulta/v1/contratacoes/publicacao``
and upserts into ``pncp_raw_bids`` via the ``bulk_upsert`` RPC.

This module replaces the old monolithic ``crawler.py`` and provides both:
  - ``BidsCrawler`` class (based on ``BaseCrawler`` ABC) for new code
  - Module-level backward-compatible functions for existing importers

Orchestrates full and incremental crawls across all configured UFs and
modalidades by reusing AsyncPNCPClient._fetch_page_async() for HTTP calls
(same rate limiting, retry logic, and circuit breaker as the main pipeline).

Full crawl:
  - All UFs x all modalidades x last INGESTION_DATE_RANGE_DAYS days
  - Runs once daily at INGESTION_FULL_CRAWL_HOUR_UTC (default 5 UTC = 2 AM BRT)

Incremental crawl:
  - Each (UF, modalidade) resumes from its last checkpoint
  - Falls back to today - INGESTION_INCREMENTAL_DAYS if no checkpoint
  - Adds 1 day overlap to catch late-arriving records
  - Runs 3x daily at INGESTION_INCREMENTAL_HOURS
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from pncp_client import AsyncPNCPClient

from ingestion._base.crawler import (
    BaseCrawler,
    CrawlerResult,
    accumulate_stats,
    chunk_list,
    empty_run_stats,
)
from ingestion.config import (
    INGESTION_BACKFILL_CHUNK_DAYS,
    INGESTION_BACKFILL_DAYS,
    INGESTION_BATCH_DELAY_S,
    INGESTION_BATCH_SIZE_UFS,
    INGESTION_CONCURRENT_UFS,
    INGESTION_DATE_RANGE_DAYS,
    INGESTION_INCREMENTAL_DAYS,
    INGESTION_MAX_PAGES,
    INGESTION_MODALIDADES,
    INGESTION_PURGE_GRACE_DAYS,
    INGESTION_UFS,
)
from ingestion.transformer import transform_batch
from ingestion.loader import bulk_upsert, purge_old_bids
from ingestion.checkpoint import (
    get_last_checkpoint,
    save_checkpoint,
    mark_checkpoint_failed,
    create_ingestion_run,
    complete_ingestion_run,
)
from ingestion.metrics import (
    INGESTION_RECORDS_FETCHED,
    INGESTION_RECORDS_UPSERTED,
    INGESTION_UFS_PROCESSED,
    INGESTION_UFS_FAILED,
    INGESTION_PAGES_FETCHED,
    INGESTION_RUN_DURATION,
)

_logger = logging.getLogger(__name__)


# ===========================================================================
# BidsCrawler class
# ===========================================================================


class BidsCrawler(BaseCrawler):
    """Crawler for PNCP licitacoes (bids) data.

    Crawls a single (UF, modalidade) combination over a date range,
    transforming raw PNCP API responses into ``pncp_raw_bids`` rows.

    The main entry point is :meth:`run`, which implements the page loop
    with transform, upsert, and checkpoint logic.
    """

    def __init__(
        self,
        client: AsyncPNCPClient,
        uf: str,
        modalidade: int,
        date_start: date,
        date_end: date,
        crawl_batch_id: str,
    ) -> None:
        super().__init__(name=f"bids_{uf}_{modalidade}")
        self.client = client
        self.uf = uf
        self.modalidade = modalidade
        self.date_start = date_start
        self.date_end = date_end
        self.crawl_batch_id = crawl_batch_id

    async def fetch_page(self, page: int) -> list[dict]:
        response = await self.client._fetch_page_async(
            data_inicial=self.date_start.isoformat(),
            data_final=self.date_end.isoformat(),
            modalidade=self.modalidade,
            uf=self.uf,
            pagina=page,
            tamanho=50,
        )
        raw_data: list[dict] = response.get("data") or []
        if raw_data:
            INGESTION_PAGES_FETCHED.labels(
                uf=self.uf, modalidade=str(self.modalidade)
            ).inc()
        # Store the response for has_more checking
        self._last_response = response
        return raw_data

    def _has_more(self) -> bool:
        """Check if more pages are available based on last response."""
        resp = getattr(self, "_last_response", {})
        return bool(
            resp.get("temProximaPagina")
            or int(resp.get("paginasRestantes", 0)) > 0
        )

    async def transform(self, raw: dict) -> dict | None:
        rows = transform_batch(
            [raw],
            source="pncp",
            crawl_batch_id=self.crawl_batch_id,
        )
        return rows[0] if rows else None

    async def upsert_batch(self, rows: list[dict]) -> dict:
        return await bulk_upsert(rows)

    async def checkpoint_advance(self, page: int) -> None:
        await save_checkpoint(
            uf=self.uf,
            modalidade=self.modalidade,
            last_date=self.date_end,
            records_fetched=0,
            crawl_batch_id=self.crawl_batch_id,
        )

    async def run(self, max_pages: int = INGESTION_MAX_PAGES) -> CrawlerResult:
        """Crawl all pages for a single (UF, modalidade) date range.

        Accumulates all transformed items across pages and upserts them
        in a single batch at the end.

        Returns:
            CrawlerResult with aggregated stats.
        """
        stats: dict[str, Any] = {
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "pages": 0,
            "errors": 0,
        }

        try:
            page = 1
            total_items: list[dict] = []

            while page <= max_pages:
                try:
                    raw_data = await self.fetch_page(page)
                except Exception as exc:
                    self.logger.warning(
                        "page fetch error uf=%s mod=%d page=%d — %s: %s",
                        self.uf,
                        self.modalidade,
                        page,
                        type(exc).__name__,
                        exc,
                    )
                    stats["errors"] += 1
                    break

                if not raw_data:
                    self.logger.debug(
                        "uf=%s mod=%d page=%d — empty data, stopping",
                        self.uf,
                        self.modalidade,
                        page,
                    )
                    break

                stats["pages"] += 1

                INGESTION_RECORDS_FETCHED.labels(
                    uf=self.uf, modalidade=str(self.modalidade)
                ).inc(len(raw_data))

                # Transform the page, skip malformed items
                rows = transform_batch(
                    raw_data,
                    source="pncp",
                    crawl_batch_id=self.crawl_batch_id,
                )
                total_items.extend(rows)

                # Check if there are more pages
                if not self._has_more():
                    break

                page += 1

            # Upsert the full batch collected across all pages
            if total_items:
                counts = await bulk_upsert(total_items)
                stats["fetched"] = len(total_items)
                stats["inserted"] = counts.get("inserted", 0)
                stats["updated"] = counts.get("updated", 0)
                stats["unchanged"] = counts.get("unchanged", 0)

                INGESTION_RECORDS_UPSERTED.labels(
                    uf=self.uf,
                    modalidade=str(self.modalidade),
                    action="inserted",
                ).inc(stats["inserted"])
                INGESTION_RECORDS_UPSERTED.labels(
                    uf=self.uf,
                    modalidade=str(self.modalidade),
                    action="updated",
                ).inc(stats["updated"])

            # Save checkpoint on success
            await save_checkpoint(
                uf=self.uf,
                modalidade=self.modalidade,
                last_date=self.date_end,
                records_fetched=stats["fetched"],
                crawl_batch_id=self.crawl_batch_id,
            )

            INGESTION_UFS_PROCESSED.labels(modalidade=str(self.modalidade)).inc()

            self.logger.info(
                "uf=%s mod=%d pages=%d fetched=%d "
                "inserted=%d updated=%d unchanged=%d",
                self.uf,
                self.modalidade,
                stats["pages"],
                stats["fetched"],
                stats["inserted"],
                stats["updated"],
                stats["unchanged"],
            )

        except Exception as exc:
            stats["errors"] += 1
            error_msg = f"{type(exc).__name__}: {exc}"
            self.logger.error(
                "uf=%s mod=%d FAILED — %s",
                self.uf,
                self.modalidade,
                error_msg,
            )
            await mark_checkpoint_failed(
                uf=self.uf,
                modalidade=self.modalidade,
                crawl_batch_id=self.crawl_batch_id,
                error_message=error_msg,
            )
            INGESTION_UFS_FAILED.labels(modalidade=str(self.modalidade)).inc()

        return CrawlerResult.from_stats_dict(stats)


# ===========================================================================
# Module-level helpers (shared between full / incremental / backfill)
# ===========================================================================


async def _crawl_uf_all_modalidades(
    *,
    client: AsyncPNCPClient,
    uf: str,
    modalidades: list[int],
    date_start: date,
    date_end: date,
    crawl_batch_id: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Crawl all modalidades for a single UF (full crawl variant)."""
    uf_totals = empty_run_stats()

    async with semaphore:
        for modalidade in modalidades:
            crawler = BidsCrawler(
                client=client,
                uf=uf,
                modalidade=modalidade,
                date_start=date_start,
                date_end=date_end,
                crawl_batch_id=crawl_batch_id,
            )
            result = await crawler.run()
            stats = result.to_dict()
            accumulate_stats(uf_totals, stats)
            if stats.get("errors", 0) > 0:
                uf_totals["ufs_failed"] += 1
            else:
                uf_totals["ufs_crawled"] += 1

    return uf_totals


async def _crawl_uf_incremental(
    *,
    client: AsyncPNCPClient,
    uf: str,
    modalidades: list[int],
    fallback_start: date,
    date_end: date,
    crawl_batch_id: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Crawl all modalidades for a single UF (incremental variant).

    For each modalidade, resolves the start date from the last checkpoint
    with a 1-day overlap to catch late-arriving records.
    """
    uf_totals = empty_run_stats()

    async with semaphore:
        for modalidade in modalidades:
            last_checkpoint = await get_last_checkpoint(uf=uf, modalidade=modalidade)

            if last_checkpoint:
                checkpoint_start = last_checkpoint - timedelta(days=1)
                date_start = max(checkpoint_start, fallback_start)
            else:
                date_start = fallback_start

            crawler = BidsCrawler(
                client=client,
                uf=uf,
                modalidade=modalidade,
                date_start=date_start,
                date_end=date_end,
                crawl_batch_id=crawl_batch_id,
            )
            result = await crawler.run()
            stats = result.to_dict()
            accumulate_stats(uf_totals, stats)
            if stats.get("errors", 0) > 0:
                uf_totals["ufs_failed"] += 1
            else:
                uf_totals["ufs_crawled"] += 1

    return uf_totals


# ===========================================================================
# Backward-compatible public functions
# ===========================================================================


async def crawl_uf_modalidade(
    client: AsyncPNCPClient,
    uf: str,
    modalidade: int,
    date_start: date,
    date_end: date,
    crawl_batch_id: str,
    *,
    max_pages: int = INGESTION_MAX_PAGES,
) -> dict[str, Any]:
    """Crawl all pages for a single (UF, modalidade) date range.

    Backward-compatible wrapper. See ``BidsCrawler.run()``.

    Args:
        client: An initialised AsyncPNCPClient.
        uf: State code (e.g. "SP").
        modalidade: Modalidade code (e.g. 5 for Pregao Eletronico).
        date_start: First day of the crawl window (inclusive).
        date_end: Last day of the crawl window (inclusive).
        crawl_batch_id: Identifier for the parent ingestion run.
        max_pages: Hard page cap per combination (default 50).

    Returns:
        Dict with keys: fetched, inserted, updated, unchanged, pages, errors.
    """
    crawler = BidsCrawler(
        client=client,
        uf=uf,
        modalidade=modalidade,
        date_start=date_start,
        date_end=date_end,
        crawl_batch_id=crawl_batch_id,
    )
    result = await crawler.run(max_pages=max_pages)
    return result.to_dict()


async def crawl_full(
    *,
    date_range_days: int = INGESTION_DATE_RANGE_DAYS,
    crawl_batch_id: str | None = None,
) -> dict[str, Any]:
    """Full crawl: all UFs x all modalidades x last date_range_days days.

    Steps:
    1. Generate a batch ID and create an ingestion_run row.
    2. Build UF batches of size INGESTION_BATCH_SIZE_UFS.
    3. Within each UF batch, run all modalidades per UF sequentially
       (avoids overwhelming PNCP API) with INGESTION_CONCURRENT_UFS
       parallel UFs using asyncio.Semaphore.
    4. Sleep INGESTION_BATCH_DELAY_S between UF batches.
    5. Complete ingestion_run with aggregated stats.
    6. Purge rows older than INGESTION_RETENTION_DAYS.

    Returns:
        Aggregated statistics dict.
    """
    if not crawl_batch_id:
        crawl_batch_id = f"full_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    today = date.today()
    date_start = today - timedelta(days=date_range_days)
    date_end = today

    _logger.info(
        "crawl_full: starting batch_id=%s date_range=%s to %s ufs=%d modalidades=%s",
        crawl_batch_id,
        date_start,
        date_end,
        len(INGESTION_UFS),
        INGESTION_MODALIDADES,
    )

    await create_ingestion_run(crawl_batch_id, run_type="full")

    run_start = datetime.utcnow()
    totals = empty_run_stats()
    ufs_completed_list: list[str] = []
    ufs_failed_list: list[str] = []
    semaphore = asyncio.Semaphore(INGESTION_CONCURRENT_UFS)

    async with AsyncPNCPClient() as client:
        uf_batches = chunk_list(INGESTION_UFS, INGESTION_BATCH_SIZE_UFS)

        for batch_idx, uf_batch in enumerate(uf_batches):
            if batch_idx > 0:
                await asyncio.sleep(INGESTION_BATCH_DELAY_S)

            tasks = [
                _crawl_uf_all_modalidades(
                    client=client,
                    uf=uf,
                    modalidades=INGESTION_MODALIDADES,
                    date_start=date_start,
                    date_end=date_end,
                    crawl_batch_id=crawl_batch_id,
                    semaphore=semaphore,
                )
                for uf in uf_batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=False)

            for uf, result in zip(uf_batch, batch_results):
                accumulate_stats(totals, result)
                if result.get("ufs_failed", 0) > 0 and result.get("ufs_crawled", 0) == 0:
                    ufs_failed_list.append(uf)
                else:
                    ufs_completed_list.append(uf)

    # Purge closed bids
    deleted = await purge_old_bids(INGESTION_PURGE_GRACE_DAYS)
    totals["purged"] = deleted

    # Determine final status
    final_status = "completed"
    if len(ufs_failed_list) > 0 and len(ufs_completed_list) == 0:
        final_status = "failed"
    elif len(ufs_failed_list) > 0:
        final_status = "partial"

    elapsed = (datetime.utcnow() - run_start).total_seconds()
    INGESTION_RUN_DURATION.labels(run_type="full").observe(elapsed)

    await complete_ingestion_run(
        crawl_batch_id,
        status=final_status,
        total_fetched=totals["fetched"],
        inserted=totals["inserted"],
        updated=totals["updated"],
        unchanged=totals["unchanged"],
        ufs_completed=ufs_completed_list,
        ufs_failed=ufs_failed_list,
    )

    _logger.info(
        "crawl_full: DONE batch_id=%s status=%s elapsed=%.1fs "
        "fetched=%d inserted=%d updated=%d unchanged=%d purged=%d "
        "ufs_ok=%d ufs_fail=%d",
        crawl_batch_id,
        final_status,
        elapsed,
        totals["fetched"],
        totals["inserted"],
        totals["updated"],
        totals["unchanged"],
        totals["purged"],
        len(ufs_completed_list),
        len(ufs_failed_list),
    )
    return totals


async def crawl_incremental(
    *,
    date_range_days: int = INGESTION_INCREMENTAL_DAYS,
    crawl_batch_id: str | None = None,
) -> dict[str, Any]:
    """Incremental crawl: per-(UF, modalidade), resume from last checkpoint.

    For each combination:
    - Reads the last checkpoint date.
    - date_start = max(last_checkpoint - 1 day, today - date_range_days)
      (1-day overlap to catch records published just after the last crawl)
    - date_end = today

    Returns:
        Aggregated statistics dict.
    """
    if not crawl_batch_id:
        crawl_batch_id = f"incr_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    today = date.today()
    fallback_start = today - timedelta(days=date_range_days)

    _logger.info(
        "crawl_incremental: starting batch_id=%s fallback_start=%s ufs=%d modalidades=%s",
        crawl_batch_id,
        fallback_start,
        len(INGESTION_UFS),
        INGESTION_MODALIDADES,
    )

    await create_ingestion_run(crawl_batch_id, run_type="incremental")

    run_start = datetime.utcnow()
    totals = empty_run_stats()
    ufs_completed_list: list[str] = []
    ufs_failed_list: list[str] = []
    semaphore = asyncio.Semaphore(INGESTION_CONCURRENT_UFS)

    async with AsyncPNCPClient() as client:
        uf_batches = chunk_list(INGESTION_UFS, INGESTION_BATCH_SIZE_UFS)

        for batch_idx, uf_batch in enumerate(uf_batches):
            if batch_idx > 0:
                await asyncio.sleep(INGESTION_BATCH_DELAY_S)

            tasks = [
                _crawl_uf_incremental(
                    client=client,
                    uf=uf,
                    modalidades=INGESTION_MODALIDADES,
                    fallback_start=fallback_start,
                    date_end=today,
                    crawl_batch_id=crawl_batch_id,
                    semaphore=semaphore,
                )
                for uf in uf_batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=False)

            for uf, result in zip(uf_batch, batch_results):
                accumulate_stats(totals, result)
                if result.get("ufs_failed", 0) > 0 and result.get("ufs_crawled", 0) == 0:
                    ufs_failed_list.append(uf)
                else:
                    ufs_completed_list.append(uf)

    final_status = "completed"
    if len(ufs_failed_list) > 0 and len(ufs_completed_list) == 0:
        final_status = "failed"
    elif len(ufs_failed_list) > 0:
        final_status = "partial"

    elapsed = (datetime.utcnow() - run_start).total_seconds()
    INGESTION_RUN_DURATION.labels(run_type="incremental").observe(elapsed)

    await complete_ingestion_run(
        crawl_batch_id,
        status=final_status,
        total_fetched=totals["fetched"],
        inserted=totals["inserted"],
        updated=totals["updated"],
        unchanged=totals["unchanged"],
        ufs_completed=ufs_completed_list,
        ufs_failed=ufs_failed_list,
    )

    _logger.info(
        "crawl_incremental: DONE batch_id=%s status=%s elapsed=%.1fs "
        "fetched=%d inserted=%d updated=%d unchanged=%d "
        "ufs_ok=%d ufs_fail=%d",
        crawl_batch_id,
        final_status,
        elapsed,
        totals["fetched"],
        totals["inserted"],
        totals["updated"],
        totals["unchanged"],
        len(ufs_completed_list),
        len(ufs_failed_list),
    )
    return totals


async def crawl_backfill(
    *,
    total_days: int = INGESTION_BACKFILL_DAYS,
    chunk_days: int = INGESTION_BACKFILL_CHUNK_DAYS,
    crawl_batch_id: str | None = None,
) -> dict[str, Any]:
    """One-time backfill: crawl historical bids.

    Iterates backward from today in chunk_days windows (default 7 days)
    up to total_days (default 365 — PNCP API max date range).

    Uses reduced concurrency (3 parallel UFs, 3s delay) to avoid
    overwhelming the PNCP API while running alongside normal crawls.

    Does NOT purge at the end — backfill adds data, never removes.

    Returns:
        Aggregated statistics dict with total records across all chunks.
    """
    if not crawl_batch_id:
        crawl_batch_id = f"backfill_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    today = date.today()
    backfill_concurrent_ufs = min(INGESTION_CONCURRENT_UFS, 3)
    backfill_batch_delay = max(INGESTION_BATCH_DELAY_S, 3.0)

    # Build date windows: [today-chunk, today], [today-2*chunk, today-chunk], ...
    windows: list[tuple[date, date]] = []
    offset = 0
    while offset < total_days:
        window_end = today - timedelta(days=offset)
        window_start = today - timedelta(days=min(offset + chunk_days, total_days))
        windows.append((window_start, window_end))
        offset += chunk_days

    _logger.info(
        "crawl_backfill: starting batch_id=%s total_days=%d chunk_days=%d "
        "windows=%d ufs=%d modalidades=%s concurrent=%d",
        crawl_batch_id,
        total_days,
        chunk_days,
        len(windows),
        len(INGESTION_UFS),
        INGESTION_MODALIDADES,
        backfill_concurrent_ufs,
    )

    await create_ingestion_run(crawl_batch_id, run_type="backfill")

    run_start = datetime.utcnow()
    totals = empty_run_stats()
    semaphore = asyncio.Semaphore(backfill_concurrent_ufs)

    async with AsyncPNCPClient() as client:
        for window_idx, (window_start, window_end) in enumerate(windows):
            _logger.info(
                "crawl_backfill: window %d/%d — %s to %s",
                window_idx + 1,
                len(windows),
                window_start,
                window_end,
            )

            uf_batches = chunk_list(INGESTION_UFS, INGESTION_BATCH_SIZE_UFS)

            for batch_idx, uf_batch in enumerate(uf_batches):
                if batch_idx > 0:
                    await asyncio.sleep(backfill_batch_delay)

                tasks = [
                    _crawl_uf_all_modalidades(
                        client=client,
                        uf=uf,
                        modalidades=INGESTION_MODALIDADES,
                        date_start=window_start,
                        date_end=window_end,
                        crawl_batch_id=crawl_batch_id,
                        semaphore=semaphore,
                    )
                    for uf in uf_batch
                ]

                batch_results = await asyncio.gather(*tasks, return_exceptions=False)

                for uf, result in zip(uf_batch, batch_results):
                    accumulate_stats(totals, result)

            _logger.info(
                "crawl_backfill: window %d/%d done — cumulative fetched=%d inserted=%d",
                window_idx + 1,
                len(windows),
                totals["fetched"],
                totals["inserted"],
            )

    final_status = "completed" if totals.get("ufs_failed", 0) == 0 else "partial"

    elapsed = (datetime.utcnow() - run_start).total_seconds()
    INGESTION_RUN_DURATION.labels(run_type="backfill").observe(elapsed)

    await complete_ingestion_run(
        crawl_batch_id,
        status=final_status,
        total_fetched=totals["fetched"],
        inserted=totals["inserted"],
        updated=totals["updated"],
        unchanged=totals["unchanged"],
        ufs_completed=INGESTION_UFS,
        ufs_failed=[],
    )

    _logger.info(
        "crawl_backfill: DONE batch_id=%s status=%s elapsed=%.1fs "
        "fetched=%d inserted=%d updated=%d unchanged=%d windows=%d",
        crawl_batch_id,
        final_status,
        elapsed,
        totals["fetched"],
        totals["inserted"],
        totals["updated"],
        totals["unchanged"],
        len(windows),
    )
    return totals
