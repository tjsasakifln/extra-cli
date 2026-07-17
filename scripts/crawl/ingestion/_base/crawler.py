"""Canonical source-adapter contract and legacy crawler compatibility.

The operational path implements ADR-021::

    SourceAdapter.fetch(request) -> FetchResult
    SourceAdapter.normalize(raw) -> list[CanonicalRecord]
    SourceAdapter.health() -> SourceHealth

The CrawlerResult dataclass is the canonical structured result used by
monitor.py and backfill_multi_source.py for integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol, runtime_checkable

type FetchStatus = Literal[
    "success",
    "empty_confirmed",
    "partial",
    "rate_limited",
    "auth_blocked",
    "error",
]
type CanonicalRecord = dict[str, Any]

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

    source: str | None = None
    request_scope: str = "default"
    page: int | None = None
    cursor: str | None = None
    run_id: str | None = None


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

    status: FetchStatus | None = None
    """Terminal semantic status. Inferred only for legacy constructors."""

    records: list[dict[str, Any]] = field(default_factory=list)
    """Raw records returned by the fetch (empty if failed or no data)."""

    request_completed: bool = False
    """True if the HTTP request completed successfully (regardless of data)."""

    http_status: int | None = None
    """HTTP status code if applicable (None for non-HTTP sources)."""

    http_statuses: list[int] = field(default_factory=list)
    """Every observed terminal HTTP status across pages/attempts."""

    empty_confirmed: bool = False
    """True only when the source responded correctly AND confirmed no records."""

    pages_fetched: int = 0
    pages_expected: int | None = None
    resume_token: str | None = None
    checkpoint: dict[str, Any] | None = None

    errors: list[str] = field(default_factory=list)
    """Non-empty when the fetch encountered errors (connectivity, HTTP, JSON)."""

    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce fail-closed invariants while adapting legacy callers."""
        if self.http_status is not None and self.http_status not in self.http_statuses:
            self.http_statuses.append(self.http_status)
        if not self.pages_fetched:
            value = self.metadata.get("pages_fetched")
            if isinstance(value, int) and value >= 0:
                self.pages_fetched = value
        if self.pages_expected is None:
            value = self.metadata.get("pages_expected")
            if isinstance(value, int) and value >= 0:
                self.pages_expected = value
        if not self.provenance and isinstance(self.metadata.get("provenance"), dict):
            self.provenance = dict(self.metadata["provenance"])

        if self.status is None:
            self.status = self._infer_legacy_status()

        if self.errors and self.status in {"success", "empty_confirmed"}:
            if self.http_status == 429:
                self.status = "rate_limited"
            elif self.http_status in {401, 403}:
                self.status = "auth_blocked"
            else:
                self.status = "partial" if self.records else "error"

        if self.status == "success" and not self.records:
            self.status = "partial"
            self.warnings.append("zero_ambiguous")

        if self.pages_expected is not None and self.pages_fetched < self.pages_expected:
            if self.status in {"success", "empty_confirmed"}:
                self.status = "partial"
                self.empty_confirmed = False
                self.warnings.append("pages_fetched_lt_pages_expected")

        if self.empty_confirmed:
            valid_empty = (
                self.status == "empty_confirmed"
                and self.request_completed
                and not self.records
                and not self.errors
                and (self.pages_expected is None or self.pages_fetched >= self.pages_expected)
            )
            if not valid_empty:
                raise ValueError("empty_confirmed exige request e paginacao completas, zero records e zero errors")

        if self.status in {"partial", "rate_limited", "auth_blocked", "error"}:
            self.empty_confirmed = False

    def _infer_legacy_status(self) -> FetchStatus:
        if self.http_status == 429:
            return "rate_limited"
        if self.http_status in {401, 403}:
            return "auth_blocked"
        if self.errors:
            return "partial" if self.records else "error"
        if not self.request_completed:
            return "error"
        if self.empty_confirmed and not self.records:
            return "empty_confirmed"
        if self.records:
            return "success"
        return "partial" if self.request_completed else "error"

    @property
    def coverage_satisfactory(self) -> bool:
        """True only when this result can support operational evidence."""
        complete = self.pages_expected is None or self.pages_fetched >= self.pages_expected
        return bool(
            self.status in {"success", "empty_confirmed"}
            and self.request_completed
            and complete
            and not self.errors
            and self.provenance
            and (self.status != "success" or bool(self.records))
            and (self.status != "empty_confirmed" or self.empty_confirmed)
        )


@dataclass
class SourceHealth:
    """Health returned by a source adapter without mutating crawl state."""

    source: str
    status: Literal["healthy", "degraded", "blocked", "unknown"] = "unknown"
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_attempt: str | None = None
    last_success: str | None = None
    freshness_hours: float | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    """ADR-021 source adapter used by the resilient operational path."""

    source_id: str

    def fetch(self, request: CrawlRequest) -> FetchResult:
        """Fetch raw data only and return a semantic result."""
        ...

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        """Pure normalization. Network I/O is forbidden."""
        ...

    def health(self) -> SourceHealth:
        """Return current locally-observable health."""
        ...


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

    status: Literal[
        "success", "empty_confirmed", "partial", "rate_limited", "auth_blocked", "error",
        "degraded", "failed", "skipped", "empty",
    ] = "success"
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
    "CanonicalRecord",
    "CrawlRequest",
    "CrawlerProtocol",
    "CrawlerResult",
    "FetchResult",
    "FetchStatus",
    "SourceAdapter",
    "SourceHealth",
    "SourcePurpose",
    "accumulate_stats",
    "chunk_list",
    "determine_status",
    "empty_run_stats",
]
