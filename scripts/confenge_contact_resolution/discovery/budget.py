"""Per-company discovery budget and investigation outcomes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InvestigationOutcome(StrEnum):
    """Why investigation stopped for a company (not commercial discard)."""

    CONTACT_FOUND = "CONTACT_FOUND"
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ERROR = "ERROR"
    NO_CONTACT_YET = "NO_CONTACT_YET"
    RETRY_LATER = "RETRY_LATER"


@dataclass
class DiscoveryBudget:
    """Configurable operational budget per company."""

    max_search_queries: int = 6
    max_pages: int = 8
    max_total_requests: int = 16
    max_seconds: float = 45.0
    max_bytes_per_page: int = 512_000
    max_pages_per_domain: int = 8

    @classmethod
    def from_env_or_defaults(cls, **overrides: Any) -> DiscoveryBudget:
        import os

        def _i(key: str, default: int) -> int:
            raw = os.environ.get(key)
            if raw is None or raw == "":
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _f(key: str, default: float) -> float:
            raw = os.environ.get(key)
            if raw is None or raw == "":
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        base = cls(
            max_search_queries=_i("MAX_SEARCH_QUERIES_PER_COMPANY", 6),
            max_pages=_i("MAX_PAGES_PER_COMPANY", 8),
            max_total_requests=_i("MAX_TOTAL_REQUESTS_PER_COMPANY", 16),
            max_seconds=_f("MAX_SECONDS_PER_COMPANY", 45.0),
            max_bytes_per_page=_i("MAX_BYTES_PER_PAGE", 512_000),
            max_pages_per_domain=_i("MAX_PAGES_PER_DOMAIN", 8),
        )
        for k, v in overrides.items():
            if hasattr(base, k) and v is not None:
                setattr(base, k, v)
        return base


@dataclass
class DiscoveryStats:
    """Mutable counters for one company investigation."""

    search_queries: int = 0
    pages_fetched: int = 0
    total_requests: int = 0
    cache_hits: int = 0
    http_429: int = 0
    timeouts: int = 0
    errors: int = 0
    retries: int = 0
    started_at: float = field(default_factory=time.monotonic)
    outcome: str = InvestigationOutcome.NO_CONTACT_YET.value
    stop_reason: str = ""

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def budget_exhausted(self, budget: DiscoveryBudget) -> bool:
        # A limit of 0 means "this channel is disabled", not "already exhausted".
        if budget.max_search_queries > 0 and self.search_queries >= budget.max_search_queries:
            return True
        if budget.max_pages > 0 and self.pages_fetched >= budget.max_pages:
            return True
        if budget.max_total_requests > 0 and self.total_requests >= budget.max_total_requests:
            return True
        if budget.max_seconds > 0 and self.elapsed() >= budget.max_seconds:
            return True
        return False

    def mark_budget(self, budget: DiscoveryBudget) -> None:
        if budget.max_search_queries > 0 and self.search_queries >= budget.max_search_queries:
            self.stop_reason = "max_search_queries"
        elif budget.max_pages > 0 and self.pages_fetched >= budget.max_pages:
            self.stop_reason = "max_pages"
        elif budget.max_total_requests > 0 and self.total_requests >= budget.max_total_requests:
            self.stop_reason = "max_total_requests"
        elif budget.max_seconds > 0 and self.elapsed() >= budget.max_seconds:
            self.stop_reason = "max_seconds"
        self.outcome = InvestigationOutcome.BUDGET_EXHAUSTED.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "search_queries": self.search_queries,
            "pages_fetched": self.pages_fetched,
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "http_429": self.http_429,
            "timeouts": self.timeouts,
            "errors": self.errors,
            "retries": self.retries,
            "elapsed_seconds": round(self.elapsed(), 3),
            "outcome": self.outcome,
            "stop_reason": self.stop_reason,
        }
