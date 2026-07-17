"""Adaptive rate pacing for HTTP crawlers.

Monitors P95 latency and adjusts request rate automatically.
When latency exceeds thresholds, the pacers reduce throughput
to prevent overwhelming the source API or being rate-limited.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class AdaptivePacer:
    """Adjusts request rate based on observed P95 latency.

    The pacer maintains a sliding window of recent response times
    and computes percentile latency. When P95 exceeds a threshold,
    the allowed rate is reduced proportionally.

    Parameters
    ----------
    initial_rps : float
        Starting requests per second (default 10.0).
    min_rps : float
        Minimum allowed rate (default 1.0).
    max_rps : float
        Maximum allowed rate (default 50.0).
    latency_p95_threshold : float
        P95 latency in seconds that triggers rate reduction (default 2.0).
    window_size : int
        Number of recent response times to track (default 100).
    reduction_factor : float
        Multiplier for rate reduction when threshold exceeded (default 0.8).
    recovery_factor : float
        Multiplier for rate recovery when below threshold (default 1.05).
    cooldown_seconds : float
        Minimum time between rate adjustments to avoid oscillation (default 5.0).
    """

    def __init__(
        self,
        initial_rps: float = 10.0,
        min_rps: float = 1.0,
        max_rps: float = 50.0,
        latency_p95_threshold: float = 2.0,
        window_size: int = 100,
        reduction_factor: float = 0.8,
        recovery_factor: float = 1.05,
        cooldown_seconds: float = 5.0,
    ):
        self._current_rps = initial_rps
        self._min_rps = min_rps
        self._max_rps = max_rps
        self._latency_threshold = latency_p95_threshold
        self._window_size = window_size
        self._reduction_factor = reduction_factor
        self._recovery_factor = recovery_factor
        self._cooldown = cooldown_seconds

        self._latencies: list[float] = []
        self._last_adjustment: float = 0.0
        self._total_requests: int = 0
        self._lock = asyncio.Lock()

    @property
    def current_rps(self) -> float:
        """Current allowed requests per second."""
        return self._current_rps

    @property
    def p95_latency(self) -> float | None:
        """P95 latency in seconds, or None if insufficient data."""
        if len(self._latencies) < 10:
            return None
        sorted_lats = sorted(self._latencies)
        idx = min(int(len(sorted_lats) * 0.95), len(sorted_lats) - 1)
        return sorted_lats[idx]

    async def record_response_time(self, seconds: float) -> None:
        """Record a response time observation.

        May trigger adaptive rate adjustment if enough data accumulated
        and cooldown period has elapsed.
        """
        async with self._lock:
            self._latencies.append(seconds)
            self._total_requests += 1
            if len(self._latencies) > self._window_size:
                self._latencies.pop(0)

            now = time.time()
            if now - self._last_adjustment < self._cooldown:
                return

            p95 = self.p95_latency
            if p95 is None:
                return

            if p95 > self._latency_threshold:
                # Reduce rate
                new_rps = max(self._current_rps * self._reduction_factor, self._min_rps)
                logger.info(
                    "Pacer [P95=%.2fs > %.2fs] reducing rate: %.1f → %.1f RPS",
                    p95,
                    self._latency_threshold,
                    self._current_rps,
                    new_rps,
                )
                self._current_rps = new_rps
                self._last_adjustment = now
            elif p95 < self._latency_threshold * 0.5 and self._current_rps < self._max_rps:
                # Recover rate (only if P95 is comfortably below threshold)
                new_rps = min(self._current_rps * self._recovery_factor, self._max_rps)
                logger.info(
                    "Pacer [P95=%.2fs] recovering rate: %.1f → %.1f RPS",
                    p95,
                    self._current_rps,
                    new_rps,
                )
                self._current_rps = new_rps
                self._last_adjustment = now

    async def wait_if_needed(self) -> float:
        """Block until the next request is allowed, return the wait time."""
        async with self._lock:
            interval = 1.0 / self._current_rps if self._current_rps > 0 else 1.0
        await asyncio.sleep(interval)
        return interval

    async def reset(self) -> None:
        """Reset pacer to initial state."""
        async with self._lock:
            self._current_rps = self._min_rps
            self._latencies.clear()
            self._last_adjustment = 0.0
            self._total_requests = 0

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def stats(self) -> dict:
        """Return current stats for monitoring."""
        return {
            "current_rps": self._current_rps,
            "min_rps": self._min_rps,
            "max_rps": self._max_rps,
            "p95_latency": self.p95_latency,
            "window_filled": len(self._latencies),
            "window_size": self._window_size,
            "total_requests": self._total_requests,
        }
