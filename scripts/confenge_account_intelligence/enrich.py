"""Optional external enrichment provider interface.

Core and tests must never depend on network. Default provider is a no-op.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EnrichProvider(Protocol):
    """Optional enrichment of a company record from external sources."""

    def enrich(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return a (possibly augmented) record. Must not mutate input."""
        ...


class NoOpEnrichProvider:
    """Default provider: returns a shallow copy, no network, no invention."""

    def enrich(self, record: dict[str, Any]) -> dict[str, Any]:
        return dict(record)


def get_default_provider() -> EnrichProvider:
    return NoOpEnrichProvider()
