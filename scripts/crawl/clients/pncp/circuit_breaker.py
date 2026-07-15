"""PNCP circuit breaker — delegates to real implementation.

Wraps the real ``PNCPCircuitBreaker`` from ``scripts.crawl.circuit_breaker``
with the sync interface expected by existing crawler callers.

CM-06 AC-4: Circuit breaker abre após 5 falhas consecutivas, registra evento.
"""

from __future__ import annotations

import asyncio
import logging

_logger = logging.getLogger(__name__)


class _RealCircuitBreaker:
    """Thin sync wrapper around the async PNCPCircuitBreaker.

    Provides the same ``is_degraded`` / ``record_success`` / ``record_failure``
    / ``try_recover`` surface as the old stub, but delegates to the real
    implementation in ``scripts.crawl.circuit_breaker``.
    """

    def __init__(self) -> None:
        self._breaker = None
        self._loop = None

    def _ensure_breaker(self) -> None:
        if self._breaker is not None:
            return
        try:
            from scripts.crawl.circuit_breaker import get_circuit_breaker

            self._breaker = get_circuit_breaker("pncp")
        except Exception:
            _logger.warning("Real circuit breaker unavailable; using stub.", exc_info=True)
            self._breaker = _StubCircuitBreaker()

    @property
    def is_degraded(self) -> bool:
        self._ensure_breaker()
        return self._breaker.is_degraded

    def record_success(self) -> None:
        self._ensure_breaker()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._breaker.record_success())
            else:
                loop.run_until_complete(self._breaker.record_success())
        except Exception:
            _logger.debug("record_success failed", exc_info=True)

    def record_failure(self) -> None:
        self._ensure_breaker()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._breaker.record_failure())
            else:
                loop.run_until_complete(self._breaker.record_failure())
        except Exception:
            _logger.debug("record_failure failed", exc_info=True)

    def try_recover(self) -> None:
        self._ensure_breaker()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._breaker.try_recover())
            else:
                loop.run_until_complete(self._breaker.try_recover())
        except Exception:
            _logger.debug("try_recover failed", exc_info=True)


class _StubCircuitBreaker:
    """Minimal stub used when the real breaker cannot be imported."""

    is_degraded: bool = False

    async def record_success(self) -> None:
        pass

    async def record_failure(self) -> None:
        pass

    async def try_recover(self) -> None:
        pass


_circuit_breaker = _RealCircuitBreaker()


__all__ = [
    "_circuit_breaker",
    "_RealCircuitBreaker",
    "_StubCircuitBreaker",
]
