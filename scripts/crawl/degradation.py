"""STUB: Degradation tracking for circuit breakers.

Minimal definitions to enable imports from degradation.
Full implementation deferred.
"""

from __future__ import annotations


def track_degradation(source: str = "", mode: str = "") -> None:
    """STUB: Track a circuit breaker degradation event.

    Args:
        source: The source name (e.g., "cb:pncp").
        mode: The degradation mode (e.g., "circuit_open").
    """
    pass


__all__ = [
    "track_degradation",
]
