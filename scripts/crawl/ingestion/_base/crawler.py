"""STUB: Base crawler classes.

Minimal definitions to enable imports from ingestion._base.crawler.
Full implementation deferred to future epic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CrawlerResult:
    """Result of a crawler run."""

    records_upserted: int = 0
    records_fetched: int = 0
    pages_fetched: int = 0
    errors: int = 0
    truncated: bool = False
    duration_s: float = 0.0


class BaseCrawler:
    """STUB: Base class for crawlers.

    Full implementation deferred.
    """

    name: str = "base_crawler"

    async def run(self, *args: Any, **kwargs: Any) -> CrawlerResult:
        raise NotImplementedError


def accumulate_stats(stats: list[CrawlerResult]) -> CrawlerResult:
    """Accumulate multiple CrawlerResults into one."""
    total = CrawlerResult()
    for s in stats:
        total.records_upserted += s.records_upserted
        total.records_fetched += s.records_fetched
        total.pages_fetched += s.pages_fetched
        total.errors += s.errors
        total.truncated = total.truncated or s.truncated
        total.duration_s += s.duration_s
    return total


def chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of size chunk_size."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def empty_run_stats() -> CrawlerResult:
    """Return a zeroed CrawlerResult."""
    return CrawlerResult()


__all__ = [
    "BaseCrawler",
    "CrawlerResult",
    "accumulate_stats",
    "chunk_list",
    "empty_run_stats",
]
