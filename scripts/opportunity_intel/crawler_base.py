"""Base crawler for opportunity intelligence sources.

Provides retry/backoff, rate limiting, checkpoint resume,
timeout handling, and distinction between empty results and failures.

Reuses patterns from:
    scripts/crawl/pncp_crawler_adapter.py
    scripts/crawl/contracts_crawler.py
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.crawl.security import USER_AGENT
from scripts.opportunity_intel.models import CrawlRequest, FetchResult
from scripts.opportunity_intel.transformer import normalize_record

_logger = logging.getLogger(__name__)

# Defaults — override via env
DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)
DEFAULT_TIMEOUT = int(os.getenv("OI_READ_TIMEOUT", "30"))
DEFAULT_MAX_RETRIES = int(os.getenv("OI_MAX_RETRIES", "3"))
DEFAULT_REQUEST_DELAY = float(os.getenv("OI_REQUEST_DELAY", "0.5"))
DEFAULT_PAGE_SIZE = int(os.getenv("OI_PAGE_SIZE", "500"))
DEFAULT_MAX_PAGES = int(os.getenv("OI_MAX_PAGES", "200"))


class BaseOpportunityCrawler(ABC):
    """Abstract base crawler for opportunity sources.

    Subclasses implement:
    - build_url(request, page) → str
    - parse_response(raw_data: list[dict]) → list[OpportunityRecord]
    """

    def __init__(
        self,
        source_name: str,
        dsn: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ):
        self.source_name = source_name
        self.dsn = dsn or DEFAULT_DSN
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.page_size = page_size
        self.max_pages = max_pages
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def build_url(self, request: CrawlRequest, page: int) -> str:
        """Build the HTTP URL for a given page."""

    @abstractmethod
    def parse_response(self, raw_data: Any) -> list[dict[str, Any]]:
        """Extract record list from raw API response body."""

    def extract_pagination(self, raw_data: Any) -> tuple[int | None, int | None]:
        """Extract total pages/records without relying on mutable parser state."""
        if not isinstance(raw_data, dict):
            return None, None
        total_pages = raw_data.get("totalPaginas")
        total_records = raw_data.get("totalRegistros")
        return (
            int(total_pages) if isinstance(total_pages, int | float) else None,
            int(total_records) if isinstance(total_records, int | float) else None,
        )

    # ------------------------------------------------------------------
    # HTTP fetch with retry/backoff
    # ------------------------------------------------------------------

    def fetch_page(self, url: str, page: int) -> FetchResult:
        """Fetch a single page with retry/backoff.

        Returns FetchResult with status, raw_data, and metadata.
        Distinguishes between:
        - 200 with data (success)
        - 200 with empty array (success_zero)
        - 204 No Content (success_zero)
        - 4xx client error (error)
        - 5xx server error (retry)
        - Timeout/connection error (retry)
        """
        metadata: dict[str, Any] = {"url": url, "page": page, "retries": 0}
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            return FetchResult(
                status=0,
                error="Blocked URL: opportunity crawlers require an absolute HTTPS endpoint",
                page=page,
                metadata=metadata,
            )

        for attempt in range(self.max_retries + 1):
            metadata["retries"] = attempt
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                    },
                )
                # URL scheme and hostname are fail-closed above.
                with urllib.request.urlopen(req, timeout=self.timeout) as response:  # nosec B310
                    status = response.status
                    raw_body = response.read()

                if status == 204:
                    return FetchResult(
                        status=204,
                        page=page,
                        page_size=self.page_size,
                        completion_rule="http_204_complete",
                        metadata=metadata,
                    )

                if status == 200:
                    try:
                        data = json.loads(raw_body)
                    except json.JSONDecodeError:
                        return FetchResult(
                            status=status,
                            error=f"JSON decode failed for {url}",
                            page=page,
                            metadata=metadata,
                        )
                    total_pages, total_records = self.extract_pagination(data)
                    records = self.parse_response(data)
                    completion_rule = None
                    if total_pages is not None and page >= total_pages:
                        completion_rule = "reported_total_pages"
                    elif len(records) < self.page_size:
                        completion_rule = "short_page_without_total"
                    return FetchResult(
                        status=200,
                        raw_data=records if records else [],
                        page=page,
                        total_pages=total_pages,
                        total_records=total_records,
                        page_size=self.page_size,
                        completion_rule=completion_rule,
                        metadata=metadata,
                    )

                # Non-200 status
                if 400 <= status < 500:
                    return FetchResult(
                        status=status,
                        error=f"Client error {status} for {url}",
                        page=page,
                        metadata=metadata,
                    )
                if status >= 500:
                    if attempt < self.max_retries:
                        wait = 2**attempt
                        _logger.warning(
                            "Server error %s for %s, retry %d/%d in %ds",
                            status,
                            url,
                            attempt + 1,
                            self.max_retries,
                            wait,
                        )
                        time.sleep(wait)
                        continue
                    return FetchResult(
                        status=status,
                        error=f"Server error {status} after {self.max_retries} retries",
                        page=page,
                        metadata=metadata,
                    )

            except urllib.error.HTTPError as e:
                if attempt < self.max_retries and e.code >= 500:
                    wait = 2**attempt
                    _logger.warning("HTTP %s, retry %d/%d", e.code, attempt + 1, self.max_retries)
                    time.sleep(wait)
                    continue
                return FetchResult(
                    status=e.code,
                    error=f"HTTP {e.code}: {e.reason}",
                    page=page,
                    metadata=metadata,
                )
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < self.max_retries:
                    wait = 2**attempt
                    _logger.warning(
                        "Network error for %s: %s, retry %d/%d",
                        url,
                        e,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(wait)
                    continue
                return FetchResult(
                    status=0,
                    error=f"Network error: {e}",
                    page=page,
                    metadata=metadata,
                )
            except Exception as e:
                _logger.error("Unexpected error fetching %s: %s", url, e)
                return FetchResult(
                    status=0,
                    error=f"Unexpected: {e}",
                    page=page,
                    metadata=metadata,
                )

        return FetchResult(
            status=0,
            error=f"Max retries ({self.max_retries}) exceeded",
            page=page,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Pagination loop
    # ------------------------------------------------------------------

    def crawl(self, request: CrawlRequest) -> list[FetchResult]:
        """Execute full crawl with pagination.

        Loads checkpoints, iterates pages until exhausted or max_pages,
        saves checkpoints after each page.

        Args:
            request: CrawlRequest with source, dates, mode, limit.

        Returns:
            List of FetchResult per page.
        """
        results: list[FetchResult] = []
        start_page = 1
        fetched_records = 0
        effective_max_pages = request.max_pages or self.max_pages
        effective_max_records = request.max_records if request.max_records is not None else request.limit

        if request.mode == "full":
            self._delete_checkpoint(request)

        # Load checkpoint if incremental
        if request.mode == "incremental":
            start_page = self._load_checkpoint(request)

        for page in range(start_page, effective_max_pages + 1):
            if effective_max_records is not None and fetched_records >= effective_max_records:
                _logger.info("Record limit %d reached before page %d", effective_max_records, page)
                break

            url = self.build_url(request, page)
            _logger.debug("Fetching page %d: %s", page, url)

            result = self.fetch_page(url, page)
            results.append(result)

            if result.error:
                _logger.error("Page %d failed: %s", page, result.error)
                break

            fetched_records += len(result.raw_data)

            # Save actual record count, never number of pages.
            if request.mode != "dry-run":
                self._save_checkpoint(request, page, len(result.raw_data), result)

            # Check if last page
            if result.empty or result.is_last_page:
                _logger.info("Last page reached at %d (empty=%s)", page, result.empty)
                break

            # Rate limit
            if self.request_delay > 0:
                time.sleep(self.request_delay)

        return results

    # ------------------------------------------------------------------
    # Normalize and persist
    # ------------------------------------------------------------------

    def process_results(
        self,
        results: list[FetchResult],
        run_id: int,
        crawl_batch_id: str | None = None,
    ) -> dict[str, int]:
        """Transform and upsert all records from crawl results.

        Args:
            results: FetchResult list from crawl().
            run_id: opportunity_runs.id for audit trail.
            crawl_batch_id: Batch identifier.

        Returns:
            Dict with counts: fetched, normalized, inserted, updated, errors.
        """
        counts = {"fetched": 0, "normalized": 0, "inserted": 0, "updated": 0, "errors": 0}

        batch: list[dict[str, Any]] = []

        for result in results:
            if not result.success:
                counts["errors"] += 1
                continue

            for raw in result.raw_data:
                counts["fetched"] += 1
                try:
                    record = normalize_record(raw, self.source_name)
                    record.run_id = run_id
                    record.crawl_batch_id = crawl_batch_id
                    batch.append(record.to_db_dict())
                    counts["normalized"] += 1
                except Exception as e:
                    _logger.warning("Normalization failed: %s", e)
                    counts["errors"] += 1

        # Bulk upsert
        if batch:
            inserted, updated = self._bulk_upsert(batch)
            counts["inserted"] = inserted
            counts["updated"] = updated

        return counts

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> Any:
        """Lazy connection with autocommit."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True
        return self._conn

    def _start_run(self, request: CrawlRequest) -> int:
        """Insert into opportunity_runs, return run_id."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO opportunity_runs (source, scope_key, status, metadata)
                   VALUES (%s, %s, 'running', %s)
                   RETURNING id""",
                (
                    self.source_name,
                    request.target or "default",
                    json.dumps(
                        {
                            "date_from": str(request.date_from) if request.date_from else None,
                            "date_to": str(request.date_to) if request.date_to else None,
                            "mode": request.mode,
                            "page_size": request.page_size,
                        }
                    ),
                ),
            )
            return cur.fetchone()[0]

    def _finish_run(self, run_id: int, status: str, counts: dict[str, int], error: str | None = None):
        """Update opportunity_runs with final status."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE opportunity_runs
                   SET finished_at = NOW(),
                       status = %s,
                       records_fetched = %s,
                       records_new = %s,
                       records_updated = %s,
                       error_message = %s
                   WHERE id = %s""",
                (
                    status,
                    counts.get("fetched", 0),
                    counts.get("inserted", 0),
                    counts.get("updated", 0),
                    error,
                    run_id,
                ),
            )

    def _load_checkpoint(self, request: CrawlRequest) -> int:
        """Load last page from opportunity_checkpoints."""
        conn = self._get_conn()
        scope = request.target or "default"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_page FROM opportunity_checkpoints WHERE source = %s AND scope_key = %s",
                (self.source_name, scope),
            )
            row = cur.fetchone()
            if row and row[0]:
                _logger.info("Resuming from checkpoint: page %d", row[0] + 1)
                return row[0] + 1
        return 1

    def _save_checkpoint(
        self,
        request: CrawlRequest,
        page: int,
        page_records: int,
        result: FetchResult,
    ) -> None:
        """Save pagination checkpoint."""
        conn = self._get_conn()
        scope = request.target or "default"
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO opportunity_checkpoints (
                       source, scope_key, last_page, records_fetched, pages_expected,
                       scope_complete, completion_reason, updated_at
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (source, scope_key)
                   DO UPDATE SET last_page = EXCLUDED.last_page,
                                 records_fetched = opportunity_checkpoints.records_fetched + EXCLUDED.records_fetched,
                                 pages_expected = EXCLUDED.pages_expected,
                                 scope_complete = EXCLUDED.scope_complete,
                                 completion_reason = EXCLUDED.completion_reason,
                                 updated_at = NOW()""",
                (
                    self.source_name,
                    scope,
                    page,
                    page_records,
                    result.total_pages,
                    result.is_last_page,
                    result.completion_rule,
                ),
            )

    def _delete_checkpoint(self, request: CrawlRequest) -> None:
        """Reset one full-crawl scope while leaving other scopes untouched."""
        conn = self._get_conn()
        scope = request.target or "default"
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM opportunity_checkpoints WHERE source = %s AND scope_key = %s",
                (self.source_name, scope),
            )

    def _bulk_upsert(self, batch: list[dict[str, Any]]) -> tuple[int, int]:
        """Execute upsert_opportunity_intel RPC, return (inserted, updated) counts."""
        conn = self._get_conn()
        inserted = 0
        updated = 0
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM upsert_opportunity_intel(%s::jsonb)",
                (json.dumps(batch, default=str),),
            )
            for row in cur.fetchall():
                action = row[0]
                if action == "insert":
                    inserted += 1
                elif action == "update":
                    updated += 1
        return inserted, updated

    # ------------------------------------------------------------------
    # High-level entry point
    # ------------------------------------------------------------------

    def run(self, request: CrawlRequest | None = None) -> dict[str, Any]:
        """Execute full crawl → normalize → persist pipeline.

        Args:
            request: Crawl parameters. Defaults to full mode, last 30 days.

        Returns:
            Dict with run_id, status, counts, error.
        """
        if request is None:
            request = CrawlRequest(
                source=self.source_name,
                date_from=date.today(),
                date_to=date.today(),
                mode="full",
            )

        run_id = self._start_run(request)
        _logger.info("Run %d started for %s (mode=%s)", run_id, self.source_name, request.mode)

        try:
            results = self.crawl(request)
            counts = self.process_results(results, run_id)

            pages_processed = len(results)
            pages_expected = next((item.total_pages for item in results if item.total_pages is not None), None)
            scope_complete = bool(results) and all(item.success for item in results) and results[-1].is_last_page
            stopped_by_limit = (request.max_records or request.limit) is not None and counts["fetched"] >= int(
                request.max_records or request.limit or 0
            )
            stopped_by_max_pages = bool(results) and len(results) >= (request.max_pages or self.max_pages)

            # Determine final status from scope completion, not error ratio.
            if counts["errors"] > 0 and counts["fetched"] == 0:
                status = "failed"
            elif scope_complete and counts["fetched"] == 0:
                status = "completed_zero"
            elif scope_complete and not stopped_by_limit and not stopped_by_max_pages:
                status = "completed"
            else:
                status = "partial"

            self._finish_run(run_id, status, counts)
            with self._get_conn().cursor() as cur:
                cur.execute(
                    """
                    UPDATE opportunity_runs
                    SET pages_processed = %s,
                        pages_expected = %s,
                        records_expected = %s,
                        scope_complete = %s,
                        completion_reason = %s,
                        metadata = metadata || %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        pages_processed,
                        pages_expected,
                        next((item.total_records for item in results if item.total_records is not None), None),
                        scope_complete and not stopped_by_limit and not stopped_by_max_pages,
                        results[-1].completion_rule if results else "no_pages",
                        json.dumps(
                            {
                                "stopped_by_record_limit": stopped_by_limit,
                                "stopped_by_max_pages": stopped_by_max_pages,
                            }
                        ),
                        run_id,
                    ),
                )
            _logger.info(
                "Run %d finished: status=%s, fetched=%d, inserted=%d, updated=%d",
                run_id,
                status,
                counts["fetched"],
                counts["inserted"],
                counts["updated"],
            )

            return {
                "run_id": run_id,
                "status": status,
                "counts": counts,
                "error": None,
            }

        except Exception as e:
            _logger.error("Run %d failed: %s", run_id, e, exc_info=True)
            self._finish_run(run_id, "failed", {}, str(e))
            return {
                "run_id": run_id,
                "status": "failed",
                "counts": {},
                "error": str(e),
            }

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()


# stdlib import for socket.timeout
