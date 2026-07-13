"""Base crawler contract — Protocol, CrawlerResult, and purpose markers.

All crawler modules MUST implement:
    crawl(mode: str) -> list[dict]
    transform(records: list[dict]) -> list[dict]

The CrawlerResult dataclass is the canonical structured result used by
monitor.py and backfill_multi_source.py for integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Source purpose markers
# ---------------------------------------------------------------------------


class SourcePurpose:
    """Marker constants for crawler module ``SOURCE_PURPOSE`` attribute."""

    BIDS: Literal["bids"] = "bids"
    """Source extracts and persists bid records."""

    COVERAGE_ONLY: Literal["coverage_only"] = "coverage_only"
    """Source only updates entity_coverage, no bid data to persist."""

    HYBRID: Literal["hybrid"] = "hybrid"
    """Source does both bid extraction and standalone coverage updates."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CrawlerProtocol(Protocol):
    """Protocol that every crawler module must satisfy.

    Crawler modules are expected to be plain modules (not classes) with
    these two top-level functions.  The protocol is checked at import time
    by ``_load_crawler()`` in monitor.py and by the conformance test suite.
    """

    def crawl(self, mode: str = "full") -> list[dict]:
        """Fetch raw records from the external source.

        Args:
            mode: One of ``"full"``, ``"incremental"``, ``"dry-run"``,
                  ``"template"``, ``"selenium"``, ``"detect"``, or
                  ``"backfill"``.  Not every crawler supports every mode;
                  unsupported modes should return an empty list and log a
                  warning.

        Returns:
            List of raw dicts from the source.  May be empty.
        """
        ...

    def transform(self, records: list[dict]) -> list[dict]:
        """Normalize raw records to the canonical pncp_raw_bids schema.

        Args:
            records: Raw records returned by ``crawl()``.

        Returns:
            List of normalized dicts ready for PostgreSQL upsert.
            May be empty (e.g. for coverage-only sources).
        """
        ...


# ---------------------------------------------------------------------------
# Structured request
# ---------------------------------------------------------------------------


@dataclass
class CrawlRequest:
    """Canonical request contract for crawler ``crawl()`` calls.

    Crawlers should accept either a plain ``mode: str`` (backward-compatible)
    or a ``CrawlRequest`` instance with full date/target/limit parameters.
    """

    mode: str
    """Crawl mode: ``"full"``, ``"incremental"``, ``"backfill"``, etc."""

    date_from: date | None = None
    """Start date for date-range queries (inclusive)."""

    date_to: date | None = None
    """End date for date-range queries (inclusive)."""

    target: str | None = None
    """Limit to a single target (portal slug, IBGE code, municipio name)."""

    limit: int | None = None
    """Maximum number of records/pages/portals to process."""


# ---------------------------------------------------------------------------
# Structured fetch result
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Structured result from a single fetch operation.

    Distinguishes "source returned empty data" from "source failed".
    Crawlers should return this instead of silently swallowing errors
    and returning ``[]``.
    """

    records: list[dict] = field(default_factory=list)
    """Raw records returned by the fetch (empty if failed or no data)."""

    request_completed: bool = False
    """True if the HTTP request completed successfully (regardless of data)."""

    http_status: int | None = None
    """HTTP status code if applicable (None for non-HTTP sources)."""

    empty_confirmed: bool = False
    """True only when the source responded correctly AND confirmed no records."""

    errors: list[str] = field(default_factory=list)
    """Non-empty when the fetch encountered errors (connectivity, HTTP, JSON)."""

    metadata: dict = field(default_factory=dict)
    """Additional context (URL called, retry count, etc.)."""


# ---------------------------------------------------------------------------
# Structured result (CrawlerResult)
# ---------------------------------------------------------------------------


@dataclass
class CrawlerResult:
    """Canonical structured result produced by a single source crawl.

    All fields are optional and default to sensible zero/empty values so
    callers can incrementally populate the result across pipeline phases.
    """

    source: str = ""
    """Normalised source key (e.g. ``"pncp"``, ``"transparencia"``)."""

    status: Literal["success", "degraded", "failed", "skipped", "empty"] = "success"
    """Execution status with strict semantics (see :func:`_determine_status`)."""

    # Counters
    fetched: int = 0
    """Raw records returned by ``crawl()``."""

    transformed: int = 0
    """Records produced by ``transform()`` (before dedup)."""

    inserted: int = 0
    """New rows inserted by the upsert RPC."""

    updated: int = 0
    """Existing rows updated by the upsert RPC."""

    duplicates: int = 0
    """Records skipped because content_hash already existed."""

    matched: int = 0
    """Bids matched to an entity (all methods)."""

    unmatched: int = 0
    """Bids that could not be matched to any entity."""

    ambiguous: int = 0
    """Bids where matching produced multiple candidates."""

    new_entities_covered: int = 0
    """Net-new entity_ids that gained coverage this run."""

    classified_engineering: int = 0
    engineering_confirmed: int = 0
    engineering_probable: int = 0
    engineering_review_required: int = 0
    false_positive_discarded: int = 0
    within_200km: int = 0
    remaining_sc: int = 0
    location_unconfirmed: int = 0
    opportunities_persisted: int = 0
    external_failures: int = 0

    # Timing
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    # Errors & warnings
    error_code: str | None = None
    error_message: str | None = None
    dependencies_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (for ``--output-json``)."""
        return {
            "source": self.source,
            "status": self.status,
            "fetched": self.fetched,
            "transformed": self.transformed,
            "inserted": self.inserted,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "new_entities_covered": self.new_entities_covered,
            "classified_engineering": self.classified_engineering,
            "engineering_confirmed": self.engineering_confirmed,
            "engineering_probable": self.engineering_probable,
            "engineering_review_required": self.engineering_review_required,
            "false_positive_discarded": self.false_positive_discarded,
            "within_200km": self.within_200km,
            "remaining_sc": self.remaining_sc,
            "location_unconfirmed": self.location_unconfirmed,
            "opportunities_persisted": self.opportunities_persisted,
            "external_failures": self.external_failures,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "dependencies_missing": self.dependencies_missing,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def determine_status(
    fetched: int,
    transformed: int,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    purpose: str = "bids",
    entities_covered: int | None = None,
) -> str:
    """Compute canonical status from pipeline phase results.

    Rules (in priority order):
        1. Any error → ``"failed"``
        2. ``fetched > 0`` and ``transformed == 0``:
           - ``purpose="coverage_only"`` WITH entities_covered > 0 → ``"success"``
           - ``purpose="coverage_only"`` WITHOUT coverage evidence → ``"degraded"``
           - otherwise → ``"degraded"`` (bug or mode mismatch)
        3. ``fetched == 0`` and no errors → ``"empty"``
        4. Warnings present but data flowed → ``"degraded"``
        5. Everything OK → ``"success"``
    """
    if errors:
        return "failed"
    if fetched > 0 and transformed == 0:
        if purpose == "coverage_only":
            if entities_covered is not None and entities_covered > 0:
                return "success"
            return "degraded"  # no evidence of coverage update
        return "degraded"
    if fetched == 0:
        return "empty"
    if warnings:
        return "degraded"
    return "success"


# ---------------------------------------------------------------------------
# Utility functions (preserved from original stub)
# ---------------------------------------------------------------------------


def accumulate_stats(stats: list[CrawlerResult]) -> CrawlerResult:
    """Accumulate multiple CrawlerResults into one (sums counters)."""
    total = CrawlerResult(source="aggregate")
    for s in stats:
        total.fetched += s.fetched
        total.transformed += s.transformed
        total.inserted += s.inserted
        total.updated += s.updated
        total.duplicates += s.duplicates
        total.matched += s.matched
        total.unmatched += s.unmatched
        total.ambiguous += s.ambiguous
        total.new_entities_covered += s.new_entities_covered
        total.duration_seconds += s.duration_seconds
        if s.error_code:
            total.error_code = s.error_code
        if s.error_message:
            total.error_message = s.error_message
        total.dependencies_missing.extend(s.dependencies_missing)
        total.warnings.extend(s.warnings)
    return total


def chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of size *chunk_size*."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def empty_run_stats() -> CrawlerResult:
    """Return a zeroed CrawlerResult."""
    return CrawlerResult()


# Backward-compatible alias for modules that still import BaseCrawler
BaseCrawler = CrawlerProtocol

__all__ = [
    "BaseCrawler",
    "CrawlRequest",
    "CrawlerProtocol",
    "CrawlerResult",
    "SourcePurpose",
    "accumulate_stats",
    "chunk_list",
    "determine_status",
    "empty_run_stats",
]
