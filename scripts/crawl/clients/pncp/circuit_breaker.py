"""STUB: PNCP circuit breaker singleton.

Minimal definitions to enable imports from clients.pncp.circuit_breaker.
Full implementation lives in scripts/crawl/circuit_breaker.py.
"""

from __future__ import annotations


class _StubCircuitBreaker:
    """STUB: Minimal circuit breaker for PNCP.

    Full implementation in scripts/crawl/circuit_breaker.py.
    """

    is_degraded: bool = False

    async def record_success(self) -> None:
        pass

    async def record_failure(self) -> None:
        pass

    async def try_recover(self) -> None:
        pass


_circuit_breaker = _StubCircuitBreaker()


__all__ = [
    "_StubCircuitBreaker",
    "_circuit_breaker",
]
