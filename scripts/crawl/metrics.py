"""STUB: Prometheus metrics for circuit breaker.

Minimal definitions to enable imports from metrics.
Full implementation deferred.
"""

from __future__ import annotations

# Circuit breaker open duration metric
CB_OPEN_DURATION = None

# Circuit breaker state gauge (0=closed, 1=open)
CB_STATE_GAUGE = None

# Circuit breaker state enum
CIRCUIT_BREAKER_STATE = None


__all__ = [
    "CB_OPEN_DURATION",
    "CB_STATE_GAUGE",
    "CIRCUIT_BREAKER_STATE",
]
