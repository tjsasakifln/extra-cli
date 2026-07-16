"""Tests for BaseHTTPClient — retry, circuit breaker, metrics, timeout chain.

Focuses on unit-testable components:
- RetryConfig (deterministic, no HTTP needed)
- InProcessCircuitBreaker (async but standalone)
- Exception classes
- Metrics label verification
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from scripts.crawl.clients.base.base import (
    BaseHTTPClient,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    HTTPClientError,
    HTTPRetryableError,
    RetryConfig,
    InProcessCircuitBreaker,
)
from scripts.crawl.metrics import (
    CBStateEnum,
    CB_STATE_GAUGE,
    HTTP_REQUESTS_TOTAL,
    HTTP_RETRIES_TOTAL,
)


# ===========================================================================
# RetryConfig — fully deterministic, no HTTP needed
# ===========================================================================


class TestRetryConfig:
    def test_default_retryable_statuses(self):
        cfg = RetryConfig()
        assert 429 in cfg.retryable_statuses
        assert 500 in cfg.retryable_statuses
        assert 502 in cfg.retryable_statuses
        assert 503 in cfg.retryable_statuses
        assert 504 in cfg.retryable_statuses
        assert 408 in cfg.retryable_statuses
        assert 425 in cfg.retryable_statuses
        assert 400 not in cfg.retryable_statuses
        assert 404 not in cfg.retryable_statuses

    def test_get_delay_exponential(self):
        cfg = RetryConfig(base_delay=10, multiplier=2, max_delay=100, jitter_factor=0)
        assert cfg.get_delay(0) == 10.0
        assert cfg.get_delay(1) == 20.0
        assert cfg.get_delay(2) == 40.0
        assert cfg.get_delay(3) == 80.0
        assert cfg.get_delay(4) == 100.0  # capped at max_delay

    def test_get_delay_with_jitter(self):
        cfg = RetryConfig(base_delay=10, multiplier=2, max_delay=100, jitter_factor=0.2)
        delay = cfg.get_delay(0)
        # With jitter_factor=0.2, delay should be in [8, 12]
        assert 8.0 <= delay <= 12.0, f"Expected delay ~10, got {delay}"

    def test_get_delay_retry_after_precedence(self):
        """Given Retry-After header, when get_delay called, then header value used."""
        cfg = RetryConfig(base_delay=60, multiplier=5, max_delay=600, jitter_factor=0)
        delay = cfg.get_delay(0, retry_after=5.0)
        assert delay == 5.0

    def test_get_delay_retry_after_with_jitter(self):
        """Given Retry-After header, when jitter applied, then delay around header value."""
        cfg = RetryConfig(base_delay=60, multiplier=5, max_delay=600, jitter_factor=0.1)
        delay = cfg.get_delay(0, retry_after=10.0)
        assert 9.0 <= delay <= 11.0, f"Expected delay ~10, got {delay}"

    def test_parse_retry_after_seconds(self):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {"Retry-After": "120"}
        assert RetryConfig.parse_retry_after(mock_response) == 120.0

    def test_parse_retry_after_none(self):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {}
        assert RetryConfig.parse_retry_after(mock_response) is None

    def test_parse_retry_after_invalid(self):
        """Given non-numeric Retry-After (e.g. HTTP-date), when parsed, then None returned."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
        assert RetryConfig.parse_retry_after(mock_response) is None


# ===========================================================================
# InProcessCircuitBreaker — async but standalone, no HTTP needed
# ===========================================================================


class TestInProcessCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig())
        assert cb.state == CBStateEnum.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    @pytest.mark.asyncio
    async def test_allow_request_when_closed(self):
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig())
        assert await cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_trips_after_threshold_failures(self):
        """Given threshold=3, when 3 consecutive failures, then circuit opens."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=3, cooldown=60))

        # First two failures — stays closed
        for _ in range(2):
            assert await cb.allow_request() is True
            await cb.record_failure()
            assert cb.is_closed is True

        # Third failure — trips to OPEN
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True
        assert cb._consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_rejects_when_open(self):
        """Given OPEN breaker, when allow_request checked, then returns False."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=1, cooldown=60))
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True
        assert await cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_half_open_after_cooldown(self):
        """Given OPEN breaker after cooldown, when allow_request, then HALF_OPEN probe allowed."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=1, cooldown=0.05))
        # Trip breaker
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True

        # Wait for cooldown
        await asyncio.sleep(0.06)

        # Should allow probe
        assert await cb.allow_request() is True
        assert cb.is_half_open is True

    @pytest.mark.asyncio
    async def test_recovers_to_closed_after_half_open_success(self):
        """Given HALF_OPEN probe succeeds, when record_success, then circuit closes."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=1, cooldown=0.05))
        # Trip breaker
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True

        await asyncio.sleep(0.06)

        # Probe (HALF_OPEN)
        assert await cb.allow_request() is True
        assert cb.is_half_open is True

        # Probe succeeds
        await cb.record_success()
        assert cb.is_closed is True
        assert cb._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_returns_to_open_after_half_open_failure(self):
        """Given HALF_OPEN probe fails, when record_failure, then circuit re-opens."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=1, cooldown=0.05))
        # Trip breaker
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True

        await asyncio.sleep(0.06)

        # Probe (HALF_OPEN)
        assert await cb.allow_request() is True
        assert cb.is_half_open is True

        # Probe fails — back to OPEN
        await cb.record_failure()
        assert cb.is_open is True
        assert cb._consecutive_failures == 2  # Now has 2 consecutive

    @pytest.mark.asyncio
    async def test_reset_manually(self):
        """Given OPEN breaker, when reset called, then CLOSED."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=1, cooldown=60))
        assert await cb.allow_request() is True
        await cb.record_failure()
        assert cb.is_open is True

        await cb.reset()
        assert cb.is_closed is True
        assert cb._consecutive_failures == 0
        assert await cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_success_during_normal_operation_keeps_closed(self):
        """Given CLOSED breaker, when record_success, then stays CLOSED."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=3, cooldown=60))
        await cb.record_success()
        assert cb.is_closed is True
        assert cb._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_by_success(self):
        """Given some failures but below threshold, when record_success, then counter resets."""
        cb = InProcessCircuitBreaker("test", CircuitBreakerConfig(threshold=5, cooldown=60))
        await cb.record_failure()
        await cb.record_failure()
        assert cb._consecutive_failures == 2
        await cb.record_success()
        assert cb._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_half_open_max_requests_limited(self):
        """Given HALF_OPEN with half_open_max_requests=1, only 1 probe allowed."""
        cb = InProcessCircuitBreaker(
            "test", CircuitBreakerConfig(threshold=1, cooldown=0.05, half_open_max_requests=1)
        )
        # Trip
        assert await cb.allow_request() is True
        await cb.record_failure()
        await asyncio.sleep(0.06)

        # First probe allowed
        assert await cb.allow_request() is True

        # Second probe NOT allowed (still HALF_OPEN, no success yet)
        assert await cb.allow_request() is False


# ===========================================================================
# BaseHTTPClient — using mocked transport
# ===========================================================================


@pytest.fixture
def client():
    """BaseHTTPClient with fast retry for testing."""
    return BaseHTTPClient(
        source_name="test",
        base_url="https://api.example.com",
        retry_config=RetryConfig(max_retries=0, base_delay=0.01),
        cb_config=CircuitBreakerConfig(threshold=5, cooldown=60),
        timeouts={"connect": 1.0, "read": 2.0, "total": 5.0},
    )


@pytest.mark.asyncio
async def test_get_success(client):
    """Given client, when GET succeeds, then response returned with status 200."""
    # Mock the internal client's request
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.headers = {}

    client._client.request = AsyncMock(return_value=mock_response)

    response = await client.get("/ok")
    assert response.status_code == 200
    client._client.request.assert_called_once()


@pytest.mark.asyncio
async def test_post_success(client):
    """Given client, when POST succeeds, then response returned."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.headers = {}

    client._client.request = AsyncMock(return_value=mock_response)

    response = await client.post("/data", json_body={"key": "value"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_no_retry_on_400(client):
    """Given 400 response, when client receives, then error raised (no retry)."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.is_success = False
    mock_response.headers = {}
    mock_response.text = "Bad request"

    client._client.request = AsyncMock(return_value=mock_response)

    with pytest.raises(HTTPClientError) as exc_info:
        await client.get("/bad-request")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_after_threshold(client):
    """Given threshold=5 failures, when client called again, then CircuitBreakerOpen raised."""
    client.cb_config = CircuitBreakerConfig(threshold=2, cooldown=60)
    client._circuit_breaker = InProcessCircuitBreaker("test", client.cb_config)

    # Trip the breaker with recent _opened_at so cooldown hasn't elapsed
    client._circuit_breaker._consecutive_failures = 2
    client._circuit_breaker._state = CBStateEnum.OPEN
    client._circuit_breaker._opened_at = time.time()  # opened JUST now — cooldown hasn't elapsed

    with pytest.raises(CircuitBreakerOpen):
        await client.get("/any")


# ===========================================================================
# Circuit breaker integrated with BaseHTTPClient
# ===========================================================================


@pytest.mark.asyncio
async def test_breaker_integration_via_direct_failure(client):
    """Given client, when circuit breaker records failure, then consecutive count incremented."""
    client.retry_config = RetryConfig(max_retries=0, base_delay=0.01)

    # Directly exercise the circuit breaker
    cb = client._circuit_breaker
    assert cb._consecutive_failures == 0

    await cb.record_failure()
    assert cb._consecutive_failures == 1

    await cb.record_failure()
    assert cb._consecutive_failures == 2


# ===========================================================================
# Metrics
# ===========================================================================


class TestMetrics:
    def test_http_requests_total_labels(self):
        """Given metrics, when labels set, then source+method supported."""
        sample = HTTP_REQUESTS_TOTAL.labels(source="test", method="GET")
        assert sample is not None

    def test_http_retries_total_labels(self):
        """Given metrics, when labels set, then source+status supported."""
        sample = HTTP_RETRIES_TOTAL.labels(source="test", status="429")
        assert sample is not None

    def test_cb_state_gauge_labels(self):
        """Given metrics, when labels set, then source supported."""
        sample = CB_STATE_GAUGE.labels(source="test")
        assert sample is not None


# ===========================================================================
# Exceptions
# ===========================================================================


class TestExceptions:
    def test_circuit_breaker_open_str(self):
        exc = CircuitBreakerOpen("breaker is open")
        assert str(exc) == "breaker is open"

    def test_http_client_error_with_status(self):
        exc = HTTPClientError("error msg", status_code=500)
        assert exc.status_code == 500
        assert str(exc) == "error msg"

    def test_http_client_error_without_status(self):
        exc = HTTPClientError("plain error")
        assert exc.status_code is None

    def test_http_retryable_error(self):
        exc = HTTPRetryableError("retry later", status_code=429)
        assert exc.status_code == 429
        assert exc.response is None

    def test_exception_hierarchy(self):
        """Verify exception inheritance."""
        assert issubclass(CircuitBreakerOpen, Exception)
        assert issubclass(HTTPClientError, Exception)
        assert issubclass(HTTPRetryableError, Exception)
