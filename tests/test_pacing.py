"""Tests for AdaptivePacer — rate pacing with P95 latency monitoring."""

from __future__ import annotations

import asyncio

import pytest

from scripts.crawl.pacing import AdaptivePacer


class TestAdaptivePacer:
    """Tests for the adaptive rate pacer."""

    @pytest.mark.asyncio
    async def test_initial_rps(self):
        """Given default config, when pacer created, then initial RPS is set."""
        pacer = AdaptivePacer(initial_rps=10.0)
        assert pacer.current_rps == 10.0

    @pytest.mark.asyncio
    async def test_p95_none_with_insufficient_data(self):
        """Given pacer with <10 samples, when p95 queried, then None returned."""
        pacer = AdaptivePacer()
        assert pacer.p95_latency is None
        await pacer.record_response_time(0.5)
        assert pacer.p95_latency is None

    @pytest.mark.asyncio
    async def test_p95_computed_correctly(self):
        """Given pacer with 100 samples, when p95 queried, then correct percentile returned."""
        pacer = AdaptivePacer()
        for _ in range(95):
            await pacer.record_response_time(1.0)
        for _ in range(5):
            await pacer.record_response_time(10.0)
        p95 = pacer.p95_latency
        assert p95 is not None
        assert p95 >= 10.0  # P95 should catch the slow 5%

    @pytest.mark.asyncio
    async def test_rate_reduced_when_latency_high(self):
        """Given P95 > threshold, when adjustment triggered, then RPS reduced."""
        pacer = AdaptivePacer(
            initial_rps=10.0,
            min_rps=1.0,
            max_rps=50.0,
            latency_p95_threshold=2.0,
            window_size=20,
            reduction_factor=0.8,
            cooldown_seconds=0.01,
        )
        # Fill with high latency
        for _ in range(20):
            await pacer.record_response_time(5.0)

        # Need to wait for cooldown
        await asyncio.sleep(0.02)

        # Trigger adjustment
        await pacer.record_response_time(5.0)

        # Rate should have been reduced
        assert pacer.current_rps < 10.0, f"Expected RPS < 10, got {pacer.current_rps}"
        assert pacer.current_rps >= 1.0  # Not below minimum

    @pytest.mark.asyncio
    async def test_rate_recovers_when_latency_low(self):
        """Given P95 well below threshold, when adjustment triggered, then RPS recovers."""
        pacer = AdaptivePacer(
            initial_rps=5.0,
            min_rps=1.0,
            max_rps=50.0,
            latency_p95_threshold=2.0,
            window_size=20,
            recovery_factor=1.05,
            cooldown_seconds=0.01,
        )
        # Fill with low latency
        for _ in range(20):
            await pacer.record_response_time(0.5)

        await asyncio.sleep(0.02)
        current_before = pacer.current_rps

        # Trigger recovery
        await pacer.record_response_time(0.3)

        assert pacer.current_rps > current_before, f"Expected RPS to increase, stayed at {pacer.current_rps}"

    @pytest.mark.asyncio
    async def test_rate_not_below_min_rps(self):
        """Given very high latency, when reduction triggered, then rate stays >= min_rps."""
        pacer = AdaptivePacer(
            initial_rps=2.0,
            min_rps=1.0,
            max_rps=50.0,
            latency_p95_threshold=1.0,
            window_size=5,
            reduction_factor=0.5,
            cooldown_seconds=0.01,
        )
        for _ in range(10):
            await pacer.record_response_time(10.0)
            await asyncio.sleep(0.01)

        assert pacer.current_rps >= 1.0

    @pytest.mark.asyncio
    async def test_rate_not_above_max_rps(self):
        """Given very low latency, when recovery triggered, then rate stays <= max_rps."""
        pacer = AdaptivePacer(
            initial_rps=40.0,
            min_rps=1.0,
            max_rps=50.0,
            latency_p95_threshold=5.0,
            window_size=5,
            recovery_factor=2.0,
            cooldown_seconds=0.01,
        )
        for _ in range(10):
            await pacer.record_response_time(0.1)
            await asyncio.sleep(0.01)

        assert pacer.current_rps <= 50.0

    @pytest.mark.asyncio
    async def test_wait_if_needed_blocks(self):
        """Given pacer with finite RPS, when wait_if_needed called, then it blocks."""
        pacer = AdaptivePacer(initial_rps=100.0)  # High RPS → short wait
        start = asyncio.get_event_loop().time()
        await pacer.wait_if_needed()
        elapsed = asyncio.get_event_loop().time() - start
        # Should have waited ~0.01s (1/100)
        assert elapsed >= 0.005

    @pytest.mark.asyncio
    async def test_wait_interval_depends_on_rps(self):
        """Given different RPS values, when wait called, then interval inversely proportional."""
        fast_pacer = AdaptivePacer(initial_rps=100.0)
        slow_pacer = AdaptivePacer(initial_rps=2.0)

        fast_interval = await fast_pacer.wait_if_needed()
        slow_interval = await slow_pacer.wait_if_needed()

        assert slow_interval > fast_interval, f"Expected slow > fast, got {slow_interval} <= {fast_interval}"

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        """Given pacer with data, when reset called, then state cleared."""
        pacer = AdaptivePacer(initial_rps=10.0)
        for _ in range(20):
            await pacer.record_response_time(5.0)

        await pacer.reset()
        assert pacer.p95_latency is None
        assert pacer.total_requests == 0
        assert pacer.current_rps == pacer._min_rps

    @pytest.mark.asyncio
    async def test_stats_contains_keys(self):
        """Given pacer, when stats requested, then all keys present."""
        pacer = AdaptivePacer()
        stats = pacer.stats
        assert "current_rps" in stats
        assert "p95_latency" in stats
        assert "total_requests" in stats
        assert "min_rps" in stats
        assert "max_rps" in stats

    @pytest.mark.asyncio
    async def test_total_requests_tracked(self):
        """Given response times recorded, when total_requests checked, then count matches."""
        pacer = AdaptivePacer()
        for _ in range(42):
            await pacer.record_response_time(0.5)
        assert pacer.total_requests == 42
