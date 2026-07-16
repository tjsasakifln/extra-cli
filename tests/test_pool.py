"""Tests for ConnectionPool and PoolManager — connection concurrency control."""

from __future__ import annotations

import asyncio

import pytest

from scripts.crawl.pool import ConnectionPool, PoolManager, PoolTimeoutError


class TestConnectionPool:
    """Tests for the per-source connection pool."""

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        """Given pool, when acquire used, then context manager works."""
        pool = ConnectionPool("test", max_size=5)
        async with pool.acquire():
            assert pool.active == 1
            assert pool.waiting == 0
        assert pool.active == 0

    @pytest.mark.asyncio
    async def test_max_size_enforced(self):
        """Given pool with max_size=2, when 3 simultaneous acquires, then third waits."""
        pool = ConnectionPool("test", max_size=2, timeout=2.0)

        acquired = []

        async def grab(pool_obj):
            async with pool_obj.acquire():
                acquired.append(True)
                await asyncio.sleep(0.2)
            acquired.append(False)

        # Start 3 coroutines
        tasks = [asyncio.create_task(grab(pool)) for _ in range(3)]
        await asyncio.sleep(0.05)

        # At most 2 should be active simultaneously
        assert pool.active <= 2

        # Wait for all
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

    @pytest.mark.asyncio
    async def test_pool_timeout(self):
        """Given full pool and short timeout, when slot unavailable, then PoolTimeoutError raised."""
        pool = ConnectionPool("test", max_size=1, timeout=0.1)

        async def slow_task():
            async with pool.acquire():
                await asyncio.sleep(1.0)

        async def timeout_task():
            with pytest.raises(PoolTimeoutError):
                async with pool.acquire():
                    pass  # Should not reach here

        # Start slow task first
        slow = asyncio.create_task(slow_task())
        await asyncio.sleep(0.05)

        # Start timeout task
        await timeout_task()

        slow.cancel()

    @pytest.mark.asyncio
    async def test_active_and_waiting_tracked(self):
        """Given pool, when acquires happen, then active and waiting counts accurate."""
        pool = ConnectionPool("test", max_size=1, timeout=2.0)

        assert pool.active == 0
        assert pool.waiting == 0

        async def occupy():
            async with pool.acquire():
                assert pool.active == 1
                await asyncio.sleep(0.3)
            assert pool.active == 0

        async def wait_occupy(check_event):
            await check_event  # Wait until told to start acquiring
            async with pool.acquire():
                pass

        task1 = asyncio.create_task(occupy())
        await asyncio.sleep(0.05)  # Let task1 acquire

        # Create a task that will wait but we control when it starts acquiring
        ready_to_acquire = asyncio.Event()
        task2 = asyncio.create_task(wait_occupy(ready_to_acquire.wait()))
        await asyncio.sleep(0.05)

        # Tell task2 to start acquiring
        ready_to_acquire.set()
        await asyncio.sleep(0.05)  # Let task2 start waiting

        assert pool.waiting == 1, f"Expected waiting=1, got {pool.waiting}"

        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=2.0)

    @pytest.mark.asyncio
    async def test_utilization(self):
        """Given pool, when used, then utilization reflects usage."""
        pool = ConnectionPool("test", max_size=4)
        assert pool.utilization == 0.0

        async with pool.acquire():
            assert pool.utilization == 1.0 / 4.0
            async with pool.acquire():
                assert pool.utilization == 2.0 / 4.0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Given pool, when stats called, then all keys present."""
        pool = ConnectionPool("test", max_size=3)
        async with pool.acquire():
            stats = await pool.stats()
            assert stats["source"] == "test"
            assert stats["max_size"] == 3
            assert stats["active"] == 1
            assert stats["utilization"] == 1.0 / 3.0


class TestPoolManager:
    """Tests for the multi-source pool manager."""

    @pytest.mark.asyncio
    async def test_get_or_create(self):
        """Given PoolManager, when get called, returns same pool for same source."""
        manager = PoolManager()
        pool1 = manager.get("pncp", max_size=5)
        pool2 = manager.get("pncp", max_size=10)  # max_size ignored for existing
        assert pool1 is pool2
        assert pool1.max_size == 5  # Original config preserved

    @pytest.mark.asyncio
    async def test_separate_pools_per_source(self):
        """Given PoolManager, when different sources requested, they get separate pools."""
        manager = PoolManager()
        pncp_pool = manager.get("pncp")
        pcp_pool = manager.get("pcp")
        assert pncp_pool is not pcp_pool

    @pytest.mark.asyncio
    async def test_stats_all(self):
        """Given PoolManager with pools, when stats_all called, then all stats returned."""
        manager = PoolManager()
        manager.get("pncp")
        manager.get("pcp")
        stats = await manager.stats_all()
        assert "pncp" in stats
        assert "pcp" in stats
