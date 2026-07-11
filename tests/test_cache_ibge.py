"""Unit tests for the IBGEMunicipioCache class in scripts/crawl/enricher.py.

Covers cache behavior, TTL expiry, concurrent access safety, and
functional equivalence with the old module-level cache approach.
"""

import asyncio
import time

import pytest

from scripts.crawl.enricher import _ibge_cache, _IBGEMunicipioCache

# ---------------------------------------------------------------------------
# _IBGEMunicipioCache unit tests
# ---------------------------------------------------------------------------


class TestIBGEMunicipioCacheInit:
    """Tests for cache initialization."""

    def test_default_ttl_is_7_days(self):
        """Default TTL should be 7 days (604800 seconds)."""
        cache = _IBGEMunicipioCache()
        assert cache._ttl == 7 * 24 * 3600

    def test_starts_empty(self):
        """Cache should start with no data."""
        cache = _IBGEMunicipioCache()
        assert cache.size == 0
        assert not cache.is_cached

    def test_custom_ttl(self):
        """Custom TTL should be accepted."""
        cache = _IBGEMunicipioCache(ttl=3600)
        assert cache._ttl == 3600


class TestIBGEMunicipioCacheIsFresh:
    """Tests for the _is_fresh internal method."""

    def test_empty_cache_not_fresh(self):
        """Empty cache should never be fresh."""
        cache = _IBGEMunicipioCache()
        assert not cache._is_fresh()

    def test_fresh_after_set(self):
        """Cache should be fresh right after data is set."""
        cache = _IBGEMunicipioCache()
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic()
        assert cache._is_fresh()

    def test_expired_cache(self):
        """Cache beyond TTL should not be fresh."""
        cache = _IBGEMunicipioCache(ttl=0.01)  # 10ms TTL
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic() - 1  # 1 second ago (past TTL)
        assert not cache._is_fresh()

    def test_fresh_with_explicit_now(self):
        """Explicit 'now' parameter should override time.monotonic()."""
        cache = _IBGEMunicipioCache(ttl=100)
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = 1000
        assert cache._is_fresh(now=1050)   # 50s < 100s TTL
        assert not cache._is_fresh(now=1101)  # 101s > 100s TTL


class TestIBGEMunicipioCacheGetOrFetch:
    """Tests for the get_or_fetch async method."""

    @pytest.mark.asyncio
    async def test_fetch_on_empty_cache(self):
        """Should call fetch_func when cache is empty."""
        cache = _IBGEMunicipioCache()
        called = False

        async def fetch() -> dict[tuple[str, str], str]:
            nonlocal called
            called = True
            return {("sao-paulo", "SP"): "3550308"}

        result = await cache.get_or_fetch(fetch)
        assert called
        assert result == {("sao-paulo", "SP"): "3550308"}

    @pytest.mark.asyncio
    async def test_returns_cached_data(self):
        """Should return cached data without calling fetch_func."""
        cache = _IBGEMunicipioCache()
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic()
        call_count = 0

        async def fetch() -> dict[tuple[str, str], str]:
            nonlocal call_count
            call_count += 1
            return {("rio-de-janeiro", "RJ"): "3304557"}

        result = await cache.get_or_fetch(fetch)
        assert call_count == 0  # fetch_func should NOT be called
        assert result == {("sao-paulo", "SP"): "3550308"}

    @pytest.mark.asyncio
    async def test_replaces_expired_data(self):
        """Should call fetch_func when cache is expired."""
        cache = _IBGEMunicipioCache(ttl=0.01)
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic() - 1  # expired
        call_count = 0

        async def fetch() -> dict[tuple[str, str], str]:
            nonlocal call_count
            call_count += 1
            return {("florianopolis", "SC"): "4205407"}

        result = await cache.get_or_fetch(fetch)
        assert call_count == 1
        assert result == {("florianopolis", "SC"): "4205407"}
        assert cache.size == 1

    @pytest.mark.asyncio
    async def test_fallback_to_stale_on_fetch_failure(self):
        """Should return stale cache when fetch_func raises."""
        cache = _IBGEMunicipioCache()
        stale_data = {("sao-paulo", "SP"): "3550308"}
        cache._data = stale_data
        cache._ts = time.monotonic()

        async def fetch() -> dict[tuple[str, str], str]:
            raise RuntimeError("API unavailable")

        # Force expiry so it tries to fetch
        cache._ts = time.monotonic() - 1  # past TTL
        cache._ttl = 0.01

        result = await cache.get_or_fetch(fetch)
        assert result == stale_data  # stale data returned

    @pytest.mark.asyncio
    async def test_raises_on_fetch_failure_with_no_stale(self):
        """Should propagate exception when fetch fails and no stale data."""
        cache = _IBGEMunicipioCache()

        async def fetch() -> dict[tuple[str, str], str]:
            raise RuntimeError("API unavailable")

        with pytest.raises(RuntimeError, match="API unavailable"):
            await cache.get_or_fetch(fetch)

    @pytest.mark.asyncio
    async def test_fetch_only_once_when_concurrent(self):
        """Concurrent access should only fetch once (double-check locking)."""
        cache = _IBGEMunicipioCache(ttl=0.01)

        # Simulate slow fetch
        call_count = 0

        async def slow_fetch() -> dict[tuple[str, str], str]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # simulate network delay
            return {("sao-paulo", "SP"): "3550308"}

        cache._ts = time.monotonic() - 1  # expired
        cache._ttl = 0.01

        # Launch 5 concurrent requests
        tasks = [cache.get_or_fetch(slow_fetch) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert call_count == 1  # fetch called only once
        for result in results:
            assert result == {("sao-paulo", "SP"): "3550308"}

    @pytest.mark.asyncio
    async def test_clear_resets_state(self):
        """Clear should empty cache and reset timestamp."""
        cache = _IBGEMunicipioCache()
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic()

        cache.clear()

        assert cache.size == 0
        assert not cache.is_cached
        assert cache._ts == 0.0

    @pytest.mark.asyncio
    async def test_fetch_preserves_ttl_boundary(self):
        """Data just within TTL should be used from cache."""
        cache = _IBGEMunicipioCache(ttl=60)
        cache._data = {("sao-paulo", "SP"): "3550308"}
        cache._ts = time.monotonic() - 59  # 59s ago (within 60s TTL)
        call_count = 0

        async def fetch() -> dict[tuple[str, str], str]:
            nonlocal call_count
            call_count += 1
            return {}

        result = await cache.get_or_fetch(fetch)
        assert call_count == 0  # cached data returned
        assert result == {("sao-paulo", "SP"): "3550308"}


# ---------------------------------------------------------------------------
# Module-level cache instance
# ---------------------------------------------------------------------------


class TestModuleLevelCache:
    """Tests for the module-level _ibge_cache singleton."""

    def test_singleton_is_ibgemunicipiocache(self):
        """_ibge_cache should be an _IBGEMunicipioCache instance."""
        assert isinstance(_ibge_cache, _IBGEMunicipioCache)

    def test_singleton_default_ttl(self):
        """_ibge_cache should have default 7-day TTL."""
        assert _ibge_cache._ttl == 7 * 24 * 3600

    def test_starts_empty(self):
        """_ibge_cache should start empty."""
        assert _ibge_cache.size == 0
        assert not _ibge_cache.is_cached


# ---------------------------------------------------------------------------
# Thread safety with concurrent tasks
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    """Stress tests for concurrent cache access."""

    @pytest.mark.asyncio
    async def test_concurrent_high_contention(self):
        """Many concurrent tasks should not corrupt cache state."""
        cache = _IBGEMunicipioCache(ttl=0.01)

        async def fast_fetch() -> dict[tuple[str, str], str]:
            await asyncio.sleep(0.01)
            return {f"key-{i}": str(i) for i in range(10)}

        # Force expiry
        cache._ts = time.monotonic() - 1
        cache._ttl = 0.01

        # 20 concurrent callers
        tasks = [cache.get_or_fetch(fast_fetch) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All should return the same data
        expected = {f"key-{i}": str(i) for i in range(10)}
        for result in results:
            assert result == expected

    @pytest.mark.asyncio
    async def test_sequential_refresh_no_race(self):
        """Sequential expiry and refresh cycles should be stable."""
        cache = _IBGEMunicipioCache(ttl=0.05)

        for cycle in range(5):
            # Populate with cycle-specific data
            data = {f"v{cycle}_k{i}": str(i) for i in range(5)}

            async def make_fetch(d: dict):
                async def fetch() -> dict[tuple[str, str], str]:
                    await asyncio.sleep(0.01)
                    return d
                return fetch

            result = await cache.get_or_fetch(await make_fetch(data))
            assert result == data
            assert cache.size == 5

            # Let cache expire
            await asyncio.sleep(0.06)
