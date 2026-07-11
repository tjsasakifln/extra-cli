"""Unit tests for IBGE municipio cache in scripts/crawl/enricher.py.

Tests cover the module-level dict-based cache with TTL:
  - _IBGE_MUNICIPIOS_CACHE, _IBGE_MUNICIPIOS_CACHE_TS, _IBGE_MUNICIPIOS_CACHE_TTL
  - _fetch_ibge_municipio_lookup() async function

The cache stores (nome_lower, uf) -> codigo_ibge mappings with 7-day TTL.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.crawl import enricher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_async_client_mock(status_code: int, json_data: list | None) -> AsyncMock:
    """Build a mock for ``httpx.AsyncClient``.

    In Python 3.12+, calling an ``AsyncMock`` automatically returns an
    awaitable coroutine that resolves to ``return_value``.  So both
    ``__aenter__`` and ``get`` are ``AsyncMock`` instances whose
    ``return_value`` is the next object in the chain.
    """
    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=client)

    return instance


# ---------------------------------------------------------------------------
# Cache constants
# ---------------------------------------------------------------------------


class TestCacheConstants:
    """Tests for cache TTL constant."""

    def test_ttl_is_7_days(self):
        """_IBGE_MUNICIPIOS_CACHE_TTL should be 7 days in seconds."""
        assert enricher._IBGE_MUNICIPIOS_CACHE_TTL == 7 * 24 * 3600

    def test_cache_starts_empty(self):
        """Cache dict starts empty and timestamp starts at 0."""
        assert enricher._IBGE_MUNICIPIOS_CACHE == {}
        assert enricher._IBGE_MUNICIPIOS_CACHE_TS == 0.0


# ---------------------------------------------------------------------------
# _fetch_ibge_municipio_lookup — fresh cache returns immediately
# ---------------------------------------------------------------------------


class TestFetchWithFreshCache:
    """Tests for _fetch_ibge_municipio_lookup when cache is already fresh."""

    @pytest.mark.asyncio
    async def test_returns_cached_data_when_fresh(self):
        """When cache is within TTL, return cache without HTTP call."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            test_data = {("sao-paulo", "SP"): "3550308"}
            enricher._IBGE_MUNICIPIOS_CACHE = test_data
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic()

            with patch.object(enricher.httpx, "AsyncClient") as mock_cls:
                result = await enricher._fetch_ibge_municipio_lookup()
                mock_cls.assert_not_called()
                assert result == test_data
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts

    @pytest.mark.asyncio
    async def test_returns_cached_data_before_ttl_expiry(self):
        """Data just within TTL boundary is returned from cache."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            test_data = {("florianopolis", "SC"): "4205407"}
            enricher._IBGE_MUNICIPIOS_CACHE = test_data
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic() - (6 * 24 * 3600)

            with patch.object(enricher.httpx, "AsyncClient") as mock_cls:
                result = await enricher._fetch_ibge_municipio_lookup()
                mock_cls.assert_not_called()
                assert result == test_data
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts


# ---------------------------------------------------------------------------
# _fetch_ibge_municipio_lookup — HTTP fetch behavior
# ---------------------------------------------------------------------------


class TestFetchApiBehavior:
    """Tests for the HTTP fetch and retry logic."""

    @pytest.mark.asyncio
    async def test_fetch_populates_cache(self):
        """Fetching from API populates the module cache."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            enricher._IBGE_MUNICIPIOS_CACHE = {}
            enricher._IBGE_MUNICIPIOS_CACHE_TS = 0.0

            api_data = [
                {"id": 4205407, "nome": "Florianopolis",
                 "microrregiao": {"mesorregiao": {"UF": {"sigla": "SC"}}}},
                {"id": 4204202, "nome": "Chapeco",
                 "microrregiao": {"mesorregiao": {"UF": {"sigla": "SC"}}}},
            ]

            mock_instance = _make_async_client_mock(200, api_data)
            with patch.object(enricher.httpx, "AsyncClient", return_value=mock_instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert ("florianopolis", "SC") in result
            assert result[("florianopolis", "SC")] == "4205407"
            assert ("chapeco", "SC") in result
            assert result[("chapeco", "SC")] == "4204202"
            assert len(result) == 2
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts

    @pytest.mark.asyncio
    async def test_stale_cache_replaced_on_fetch(self):
        """When cache is expired, fresh API data replaces stale data."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            enricher._IBGE_MUNICIPIOS_CACHE = {("stale", "SC"): "0000000"}
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic() - (8 * 24 * 3600)

            fresh_data = [
                {"id": 3550308, "nome": "Sao Paulo",
                 "microrregiao": {"mesorregiao": {"UF": {"sigla": "SP"}}}},
            ]

            mock_instance = _make_async_client_mock(200, fresh_data)
            with patch.object(enricher.httpx, "AsyncClient", return_value=mock_instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert ("sao paulo", "SP") in result
            assert result[("sao paulo", "SP")] == "3550308"
            assert len(result) == 1
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts

    @pytest.mark.asyncio
    async def test_fallback_to_stale_on_http_error(self):
        """Returns stale cache when API returns non-200."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            stale_data = {("chapeco", "SC"): "4204202"}
            enricher._IBGE_MUNICIPIOS_CACHE = stale_data
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic() - (8 * 24 * 3600)

            mock_instance = _make_async_client_mock(500, None)
            with patch.object(enricher.httpx, "AsyncClient", return_value=mock_instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert result == stale_data
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts

    @pytest.mark.asyncio
    async def test_fallback_to_stale_on_timeout(self):
        """Returns stale cache when HTTP request times out."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            stale_data = {("chapeco", "SC"): "4204202"}
            enricher._IBGE_MUNICIPIOS_CACHE = stale_data
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic() - (8 * 24 * 3600)

            # Simulate a timeout: make the get call raise
            client = MagicMock()
            client.get = AsyncMock(side_effect=enricher.httpx.TimeoutException("timeout"))

            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=client)

            with patch.object(enricher.httpx, "AsyncClient", return_value=instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert result == stale_data
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts

    @pytest.mark.asyncio
    async def test_retry_on_http_500(self):
        """Retries up to 3 times on HTTP 500, then falls back to stale."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            stale_data = {("chapeco", "SC"): "4204202"}
            enricher._IBGE_MUNICIPIOS_CACHE = stale_data
            enricher._IBGE_MUNICIPIOS_CACHE_TS = time.monotonic() - (8 * 24 * 3600)

            mock_instance = _make_async_client_mock(500, None)
            with patch.object(enricher.httpx, "AsyncClient", return_value=mock_instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert result == stale_data
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts


# ---------------------------------------------------------------------------
# Integration: no stale cache on first fetch
# ---------------------------------------------------------------------------


class TestFetchWithNoCache:
    """Tests when there is no cached data at all."""

    @pytest.mark.asyncio
    async def test_empty_cache_fetches_from_api(self):
        """On first call with empty cache, fetches from API."""
        original_cache = enricher._IBGE_MUNICIPIOS_CACHE
        original_ts = enricher._IBGE_MUNICIPIOS_CACHE_TS
        try:
            enricher._IBGE_MUNICIPIOS_CACHE = {}
            enricher._IBGE_MUNICIPIOS_CACHE_TS = 0.0

            api_data = [
                {"id": 4205407, "nome": "Floripa",
                 "microrregiao": {"mesorregiao": {"UF": {"sigla": "SC"}}}},
            ]

            mock_instance = _make_async_client_mock(200, api_data)
            with patch.object(enricher.httpx, "AsyncClient", return_value=mock_instance):
                result = await enricher._fetch_ibge_municipio_lookup()

            assert len(result) == 1
            assert result[("floripa", "SC")] == "4205407"
        finally:
            enricher._IBGE_MUNICIPIOS_CACHE = original_cache
            enricher._IBGE_MUNICIPIOS_CACHE_TS = original_ts
