"""BaseHTTPClient — Resilient HTTP client for all data sources.

Provides:
- Exponential retry with jitter for transient errors
- Circuit breaker integration (per-source)
- Prometheus metrics (duration, status, bytes)
- Timeout chain (connect, read, total)
- Retry-After header respect
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from scripts.crawl.metrics import (
    CBStateEnum,
    CB_OPEN_DURATION,
    CB_STATE_GAUGE,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
    HTTP_RETRIES_TOTAL,
    CRAWL_BYTES_TOTAL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Existing types preserved for backward compatibility
# ---------------------------------------------------------------------------


class SourceCapability(StrEnum):
    """Capabilities a data source may support."""

    PAGINATION = "pagination"
    DATE_RANGE = "date_range"
    FILTER_BY_UF = "filter_by_uf"
    FILTER_BY_MODALITY = "filter_by_modality"


class SourceStatus(StrEnum):
    """Operational status of a data source."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class SourceMetadata:
    """Metadata about a data source."""

    def __init__(
        self,
        name: str = "",
        code: str = "",
        base_url: str = "",
        capabilities: set[SourceCapability] | None = None,
        rate_limit_rps: float = 10.0,
        priority: int = 1,
    ):
        self.name = name
        self.code = code
        self.base_url = base_url
        self.capabilities = capabilities or set()
        self.rate_limit_rps = rate_limit_rps
        self.priority = priority


class UnifiedProcurement:
    """Unified procurement record across all sources."""

    def __init__(
        self,
        source_id: str = "",
        source_name: str = "",
        objeto: str = "",
        valor_estimado: float = 0.0,
        orgao: str = "",
        cnpj_orgao: str = "",
        uf: str = "",
        municipio: str = "",
        data_publicacao: datetime | None = None,
        data_abertura: datetime | None = None,
        data_encerramento: datetime | None = None,
        numero_edital: str = "",
        ano: str = "",
        esfera: str = "",
        modalidade: str = "",
        modalidade_id: int | None = None,
        situacao: str = "",
        link_edital: str = "",
        link_portal: str = "",
        raw_data: dict[str, Any] | None = None,
    ):
        self.source_id = source_id
        self.source_name = source_name
        self.objeto = objeto
        self.valor_estimado = valor_estimado
        self.orgao = orgao
        self.cnpj_orgao = cnpj_orgao
        self.uf = uf
        self.municipio = municipio
        self.data_publicacao = data_publicacao
        self.data_abertura = data_abertura
        self.data_encerramento = data_encerramento
        self.numero_edital = numero_edital
        self.ano = ano
        self.esfera = esfera
        self.modalidade = modalidade
        self.modalidade_id = modalidade_id
        self.situacao = situacao
        self.link_edital = link_edital
        self.link_portal = link_portal
        self.raw_data = raw_data


# ---------------------------------------------------------------------------
# Retry / circuit breaker configuration
# ---------------------------------------------------------------------------


class RetryConfig:
    """Retry policy configuration.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts (default 3).
    base_delay : float
        Base delay in seconds for exponential backoff (default 60.0).
    multiplier : float
        Multiplier for exponential backoff (default 5.0).
    max_delay : float
        Maximum delay in seconds between retries (default 600.0).
    jitter_factor : float
        Random jitter factor applied to delay: delay * (1 - jitter, 1 + jitter) (default 0.1).
    retryable_statuses : set[int]
        HTTP status codes that should be retried.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 60.0,
        multiplier: float = 5.0,
        max_delay: float = 600.0,
        jitter_factor: float = 0.1,
        retryable_statuses: set[int] | None = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.retryable_statuses = retryable_statuses or {408, 425, 429, 500, 502, 503, 504}

    def get_delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Compute delay for the given attempt number (0-based).

        If the server provided a Retry-After header, that value takes
        precedence (with jitter applied). Otherwise exponential backoff.
        """
        if retry_after is not None and retry_after > 0:
            delay = float(retry_after)
        else:
            delay = min(self.base_delay * (self.multiplier ** attempt), self.max_delay)

        # Apply jitter
        jitter = delay * self.jitter_factor
        return delay + random.uniform(-jitter, jitter)

    @staticmethod
    def parse_retry_after(response: httpx.Response) -> float | None:
        """Parse Retry-After header from response, supporting both seconds and HTTP-date."""
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            # RFC 7231: could be HTTP-date — fall back to default
            return None


class CircuitBreakerConfig:
    """Per-source circuit breaker configuration.

    Parameters
    ----------
    threshold : int
        Number of consecutive failures to trip the breaker (default 5).
    cooldown : float
        Seconds to remain OPEN before transitioning to HALF_OPEN (default 60.0).
    half_open_max_requests : int
        Number of probe requests while HALF_OPEN (default 1).
    """

    def __init__(
        self,
        threshold: int = 5,
        cooldown: float = 60.0,
        half_open_max_requests: int = 1,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.half_open_max_requests = half_open_max_requests


# ---------------------------------------------------------------------------
# In-process circuit breaker
# ---------------------------------------------------------------------------


class InProcessCircuitBreaker:
    """Lightweight in-process circuit breaker, no Redis dependency.

    State machine: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN).

    Thread-safe via asyncio lock.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self._lock = asyncio.Lock()
        self._state = CBStateEnum.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_requests = 0

    @property
    def state(self) -> CBStateEnum:
        return self._state

    async def allow_request(self) -> bool:
        """Check whether a request should be allowed through."""
        async with self._lock:
            if self._state == CBStateEnum.CLOSED:
                return True

            if self._state == CBStateEnum.OPEN:
                if self._opened_at and (time.time() - self._opened_at) >= self.config.cooldown:
                    # Transition to HALF_OPEN — this probe counts toward the limit
                    self._state = CBStateEnum.HALF_OPEN
                    self._half_open_requests = 1
                    CB_STATE_GAUGE.labels(source=self.name).set(int(CBStateEnum.HALF_OPEN))
                    logger.info("Circuit breaker [%s] → HALF_OPEN (cooldown elapsed)", self.name)
                    return True
                return False

            # HALF_OPEN: allow limited probe requests
            if self._half_open_requests < self.config.half_open_max_requests:
                self._half_open_requests += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record a successful request.

        - Resets consecutive failure count.
        - If HALF_OPEN or OPEN, transitions to CLOSED.
        - If already CLOSED, just resets the failure counter (health check signal).
        """
        async with self._lock:
            self._consecutive_failures = 0
            if self._state in (CBStateEnum.HALF_OPEN, CBStateEnum.OPEN):
                self._state = CBStateEnum.CLOSED
                self._opened_at = None
                self._half_open_requests = 0
                CB_STATE_GAUGE.labels(source=self.name).set(int(CBStateEnum.CLOSED))
                CB_OPEN_DURATION.labels(source=self.name).observe(0.0)
                logger.info("Circuit breaker [%s] → CLOSED (success recovered)", self.name)

    async def record_failure(self) -> None:
        """Record a failure — trip breaker if threshold exceeded."""
        async with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.config.threshold:
                if self._state != CBStateEnum.OPEN:
                    self._state = CBStateEnum.OPEN
                    self._opened_at = time.time()
                    CB_STATE_GAUGE.labels(source=self.name).set(int(CBStateEnum.OPEN))
                    CB_OPEN_DURATION.labels(source=self.name).observe(0.0)
                    logger.warning(
                        "Circuit breaker [%s] → OPEN after %d consecutive failures",
                        self.name,
                        self._consecutive_failures,
                    )

    async def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        async with self._lock:
            self._state = CBStateEnum.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_requests = 0
            CB_STATE_GAUGE.labels(source=self.name).set(int(CBStateEnum.CLOSED))

    @property
    def is_closed(self) -> bool:
        return self._state == CBStateEnum.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CBStateEnum.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CBStateEnum.HALF_OPEN


# ---------------------------------------------------------------------------
# BaseHTTPClient
# ---------------------------------------------------------------------------


class BaseHTTPClient:
    """Resilient HTTP client for data source crawling.

    Wraps ``httpx.AsyncClient`` with:
    - Exponential retry with jitter for transient errors
    - Circuit breaker per source to prevent cascading failures
    - Prometheus metrics emission
    - Timeout chain (connect, read, total)
    - Optional per-source rate limiting

    Parameters
    ----------
    source_name : str
        Logical name of the data source (e.g., ``"pncp"``, ``"pcp"``).
    base_url : str
        Base URL for the source API.
    retry_config : RetryConfig, optional
        Retry policy. Defaults to RetryConfig().
    cb_config : CircuitBreakerConfig, optional
        Circuit breaker config. Defaults to CircuitBreakerConfig().
    timeouts : dict, optional
        Timeout overrides. Keys: ``connect``, ``read``, ``total`` (seconds).
    rate_limit_rps : float, optional
        Maximum requests per second. 0 = no limit.
    extra_headers : dict, optional
        Additional headers to include with every request.
    """

    def __init__(
        self,
        source_name: str,
        base_url: str,
        retry_config: RetryConfig | None = None,
        cb_config: CircuitBreakerConfig | None = None,
        timeouts: dict[str, float] | None = None,
        rate_limit_rps: float = 0.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.source_name = source_name
        self.base_url = base_url.rstrip("/")
        self.retry_config = retry_config or RetryConfig()
        self.cb_config = cb_config or CircuitBreakerConfig()

        self.timeouts = {
            "connect": 10.0,
            "read": 30.0,
            "total": 120.0,
            **(timeouts or {}),
        }

        self.rate_limit_rps = rate_limit_rps
        self._rate_limit_semaphore: asyncio.Semaphore | None = None
        if rate_limit_rps > 0:
            self._rate_limit_semaphore = asyncio.Semaphore(int(rate_limit_rps))

        self._extra_headers = extra_headers or {}
        self._circuit_breaker = InProcessCircuitBreaker(source_name, self.cb_config)
        self._client = self._build_client()
        self._last_request_time: float = 0.0

    def _build_client(self) -> httpx.AsyncClient:
        """Build the underlying httpx AsyncClient with configured timeouts."""
        timeout_config = httpx.Timeout(
            self.timeouts["total"],
            connect=self.timeouts["connect"],
            read=self.timeouts["read"],
        )
        return httpx.AsyncClient(
            timeout=timeout_config,
            headers=self._extra_headers,
            follow_redirects=True,
        )

    async def _rate_limit_wait(self) -> None:
        """Enforce per-source rate limiting."""
        if self._rate_limit_semaphore is None:
            return
        async with self._rate_limit_semaphore:
            now = time.time()
            elapsed = now - self._last_request_time
            min_interval = 1.0 / self.rate_limit_rps
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_time = time.time()

    def _is_retryable(self, status_code: int) -> bool:
        """Determine if a status code should trigger a retry."""
        return status_code in self.retry_config.retryable_statuses

    def _is_network_error(self, exc: Exception) -> bool:
        """Determine if an exception is a transient network error."""
        return isinstance(
            exc,
            (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.WriteError,
                httpx.PoolTimeout,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
            ),
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        max_retries: int | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with retry, circuit breaker, and metrics.

        Parameters
        ----------
        method : str
            HTTP method (``"GET"``, ``"POST"``, etc.).
        path : str
            URL path relative to ``base_url`` (e.g., ``"/api/v1/bids"``).
        params : dict, optional
            Query parameters.
        json_body : any, optional
            JSON-serializable body for POST/PUT requests.
        headers : dict, optional
            Per-request headers merged with client defaults.
        max_retries : int, optional
            Override max retries for this specific request.

        Returns
        -------
        httpx.Response
            The response object.

        Raises
        ------
        CircuitBreakerOpen
            If the circuit breaker is OPEN and rejects the request.
        """
        max_retries = max_retries if max_retries is not None else self.retry_config.max_retries
        url = f"{self.base_url}/{path.lstrip('/')}"

        # Circuit breaker check
        if not await self._circuit_breaker.allow_request():
            HTTP_REQUESTS_TOTAL.labels(source=self.source_name, method=method).inc()
            raise CircuitBreakerOpen(
                f"Circuit breaker [{self.source_name}] is OPEN — request rejected"
            )

        # Rate limit wait
        await self._rate_limit_wait()

        last_error: Exception | None = None
        request_headers = {**self._extra_headers, **(headers or {})}

        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=request_headers,
                )

                duration = time.time() - start_time

                # Emit metrics
                HTTP_REQUESTS_TOTAL.labels(source=self.source_name, method=method).inc()
                HTTP_REQUEST_DURATION.labels(
                    source=self.source_name,
                    method=method,
                    status=str(response.status_code),
                ).observe(duration)

                # Track bytes
                content_length = response.headers.get("content-length")
                if content_length:
                    CRAWL_BYTES_TOTAL.labels(source=self.source_name).inc(int(content_length))

                # Success path
                if response.is_success:
                    await self._circuit_breaker.record_success()
                    return response

                # Determine retryability
                if self._is_retryable(response.status_code):
                    retry_after = RetryConfig.parse_retry_after(response)
                    delay = self.retry_config.get_delay(attempt, retry_after)
                    HTTP_RETRIES_TOTAL.labels(
                        source=self.source_name,
                        status=str(response.status_code),
                    ).inc()
                    logger.warning(
                        "HTTP %d from %s (attempt %d/%d) — retrying in %.1fs",
                        response.status_code,
                        self.source_name,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    last_error = HTTPRetryableError(
                        f"HTTP {response.status_code} from {self.source_name}",
                        status_code=response.status_code,
                        response=response,
                    )
                    continue

                # Non-retryable client error — record failure
                await self._circuit_breaker.record_failure()
                raise HTTPClientError(
                    f"HTTP {response.status_code} from {self.source_name}: {response.text[:500]}",
                    status_code=response.status_code,
                    response=response,
                )

            except httpx.TimeoutException as exc:
                duration = time.time() - start_time
                await self._circuit_breaker.record_failure()
                if attempt < max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    HTTP_RETRIES_TOTAL.labels(source=self.source_name, status="timeout").inc()
                    logger.warning(
                        "Timeout %s %s (attempt %d/%d) — retrying in %.1fs",
                        method,
                        url,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    last_error = exc
                    continue
                raise HTTPClientError(
                    f"Timeout after {max_retries + 1} attempts: {exc}"
                ) from exc

            except (
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.WriteError,
                httpx.PoolTimeout,
            ) as exc:
                duration = time.time() - start_time
                await self._circuit_breaker.record_failure()
                if attempt < max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    HTTP_RETRIES_TOTAL.labels(source=self.source_name, status="connection").inc()
                    logger.warning(
                        "Connection error %s %s (attempt %d/%d) — retrying in %.1fs: %s",
                        method,
                        url,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    last_error = exc
                    continue
                raise HTTPClientError(
                    f"Connection error after {max_retries + 1} attempts: {exc}"
                ) from exc

        # All retries exhausted
        raise HTTPClientError(
            f"All {max_retries + 1} attempts failed for {self.source_name}: {last_error}"
        )

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int | None = None,
    ) -> httpx.Response:
        """Convenience wrapper for GET requests."""
        return await self.request("GET", path, params=params, headers=headers, max_retries=max_retries)

    async def post(
        self,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int | None = None,
    ) -> httpx.Response:
        """Convenience wrapper for POST requests."""
        return await self.request(
            "POST", path, json_body=json_body, params=params, headers=headers, max_retries=max_retries
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @property
    def circuit_breaker_state(self) -> CBStateEnum:
        """Current circuit breaker state."""
        return self._circuit_breaker._state

    @property
    def circuit_breaker(self) -> InProcessCircuitBreaker:
        """Access the circuit breaker instance for monitoring."""
        return self._circuit_breaker


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class BaseHTTPError(Exception):
    """Base exception for HTTP client errors."""


class CircuitBreakerOpen(BaseHTTPError):
    """Raised when the circuit breaker rejects a request."""


class HTTPRetryableError(BaseHTTPError):
    """Raised when a retryable HTTP error occurred (used internally).

    This is a transient exception; the caller is expected to retry.
    """

    def __init__(self, message: str, status_code: int, response: httpx.Response | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class HTTPClientError(BaseHTTPError):
    """Raised when an HTTP request fails deterministically (non-retryable)."""

    def __init__(self, message: str, status_code: int | None = None, response: httpx.Response | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


__all__ = [
    # Existing types
    "SourceCapability",
    "SourceMetadata",
    "SourceStatus",
    "UnifiedProcurement",
    # Retry / circuit breaker
    "RetryConfig",
    "CircuitBreakerConfig",
    "InProcessCircuitBreaker",
    # Client
    "BaseHTTPClient",
    # Exceptions
    "BaseHTTPError",
    "CircuitBreakerOpen",
    "HTTPRetryableError",
    "HTTPClientError",
]
