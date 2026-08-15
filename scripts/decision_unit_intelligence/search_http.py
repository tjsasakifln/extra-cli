"""CONFENGE HTTP boundary to a private SearXNG instance.

This module is the only extra-cli path that talks to SearXNG. It never imports,
vendors, or links SearXNG/AGPL code. Failures (missing URL, 429, 5xx, timeout,
circuit-open, invalid JSON) raise SearchBackendUnavailableError and are never
converted into an empty successful hit list.

In-process DDGS failover is off by default. Enabling it is an explicit operator
choice recorded on the backend id and event log; it does not pretend SearXNG
succeeded.
"""

from __future__ import annotations

import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from time import monotonic, perf_counter
from typing import Any
from urllib.parse import urlsplit

import httpx

from scripts.decision_unit_intelligence.web_discovery import USER_AGENT, SearchHit

_PUBLIC_SEARXNG_HOST_MARKERS = (
    "searx.space",
    "searx.be",
    "search.sapti.me",
    "paulgo.io",
    "search.ononoki.org",
    "priv.au",
    "searxng.site",
)


class SearchBackendUnavailableError(Exception):
    """Visible backend unavailability. Never treat as a successful miss."""

    def __init__(
        self,
        reason: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
        detail: str = "",
    ) -> None:
        self.reason = reason
        self.status_code = status_code
        self.retry_after = retry_after
        self.detail = detail
        parts = [reason]
        if status_code is not None:
            parts.append(f"status={status_code}")
        if retry_after:
            parts.append(f"retry_after={retry_after}")
        if detail:
            parts.append(detail)
        super().__init__("; ".join(parts))


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass
class SearchHttpMetrics:
    """In-process counters for the HTTP search client (not a public product)."""

    requests: int = 0
    status_counts: Counter[int] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    result_counts: list[int] = field(default_factory=list)
    engine_failures: Counter[str] = field(default_factory=Counter)
    http_429: int = 0
    http_5xx: int = 0
    timeouts: int = 0
    circuit_opens: int = 0
    network_errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_status(self, status_code: int, latency_ms: float, result_count: int) -> None:
        with self._lock:
            self.requests += 1
            self.status_counts[status_code] += 1
            self.latencies_ms.append(latency_ms)
            self.result_counts.append(result_count)
            if status_code == 429:
                self.http_429 += 1
            elif status_code >= 500:
                self.http_5xx += 1

    def record_timeout(self) -> None:
        with self._lock:
            self.requests += 1
            self.timeouts += 1

    def record_circuit_open(self) -> None:
        with self._lock:
            self.circuit_opens += 1

    def record_network(self) -> None:
        with self._lock:
            self.requests += 1
            self.network_errors += 1

    def record_engine_failures(self, engines: list[str]) -> None:
        if not engines:
            return
        with self._lock:
            self.engine_failures.update(engines)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = list(self.latencies_ms)
            return {
                "requests": self.requests,
                "status_counts": {str(k): v for k, v in sorted(self.status_counts.items())},
                "p50_ms": _percentile(latencies, 50),
                "p95_ms": _percentile(latencies, 95),
                "http_429": self.http_429,
                "http_5xx": self.http_5xx,
                "timeouts": self.timeouts,
                "circuit_opens": self.circuit_opens,
                "network_errors": self.network_errors,
                "engine_failures": dict(self.engine_failures),
                "result_count_total": sum(self.result_counts),
                "result_count_last": self.result_counts[-1] if self.result_counts else 0,
            }


class CircuitBreaker:
    """Process-local fail-closed breaker. No proxy rotation, no silent reset."""

    def __init__(self, *, failure_threshold: int = 5, reset_timeout_seconds: float = 60.0) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state_unlocked(monotonic())

    def _state_unlocked(self, now: float) -> str:
        if self._opened_at is None:
            return "closed"
        if now - self._opened_at >= self.reset_timeout_seconds:
            return "half_open"
        return "open"

    def before_call(self) -> None:
        with self._lock:
            if self._state_unlocked(monotonic()) == "open":
                raise SearchBackendUnavailableError("circuit_open", detail="searxng circuit is open")

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = monotonic()


def require_searxng_url(url: str | None, *, allow_public: bool | None = None) -> str:
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        raise SearchBackendUnavailableError("missing_url", detail="CONFENGE_SEARXNG_URL or --searxng-url is required")
    parsed = urlsplit(cleaned if "://" in cleaned else f"http://{cleaned}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SearchBackendUnavailableError("missing_url", detail="SearXNG URL has no host")
    public_allowed = (
        allow_public
        if allow_public is not None
        else os.getenv("CONFENGE_SEARXNG_ALLOW_PUBLIC", "").strip() in {"1", "true", "yes"}
    )
    if (not public_allowed) and any(host == marker or host.endswith(f".{marker}") for marker in _PUBLIC_SEARXNG_HOST_MARKERS):
        raise SearchBackendUnavailableError(
            "public_instance_denied",
            detail="public third-party SearXNG is not allowed for batch discovery",
        )
    return cleaned if "://" in cleaned else f"http://{cleaned}"


def resolve_failover_policy(value: str | None) -> str:
    policy = (value or os.getenv("CONFENGE_SEARCH_FAILOVER", "off")).strip().lower() or "off"
    if policy in {"off", "none", "false", "0"}:
        return "off"
    if policy == "ddgs":
        return "ddgs"
    raise ValueError(f"unsupported search failover: {policy}")


def _unresponsive_engines(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("unresponsive_engines") or []
    names: list[str] = []
    for row in raw:
        if isinstance(row, (list, tuple)) and row:
            names.append(str(row[0]))
        elif isinstance(row, str):
            names.append(row)
        elif isinstance(row, dict) and row.get("engine"):
            names.append(str(row["engine"]))
    return names


class SearxngHttpBackend:
    """GET/POST {url}/search?q=…&format=json against a CONFENGE-controlled instance."""

    backend_id = "searxng"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 12.0,
        max_concurrency: int = 2,
        metrics: SearchHttpMetrics | None = None,
        breaker: CircuitBreaker | None = None,
        allow_public: bool | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = require_searxng_url(base_url, allow_public=allow_public)
        self.timeout_seconds = timeout_seconds
        self.max_concurrency = max(1, max_concurrency)
        self.metrics = metrics or SearchHttpMetrics()
        self.breaker = breaker or CircuitBreaker()
        self._sema = threading.Semaphore(self.max_concurrency)
        self._transport = transport

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        try:
            self.breaker.before_call()
        except SearchBackendUnavailableError:
            self.metrics.record_circuit_open()
            raise
        params = {"q": query, "format": "json", "language": "pt-BR", "safesearch": "1"}
        started = perf_counter()
        self._sema.acquire()
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            ) as client:
                response = client.get(f"{self.base_url}/search", params=params)
        except httpx.TimeoutException as exc:
            self.metrics.record_timeout()
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("timeout", detail=type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            self.metrics.record_network()
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("network", detail=type(exc).__name__) from exc
        finally:
            self._sema.release()

        latency_ms = (perf_counter() - started) * 1000.0
        status = response.status_code
        retry_after = response.headers.get("Retry-After")
        if status == 429:
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("http_429", status_code=429, retry_after=retry_after)
        if status >= 500:
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("http_5xx", status_code=status)
        if status >= 400:
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("http_4xx", status_code=status)

        try:
            payload = response.json()
        except ValueError as exc:
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("invalid_json", status_code=status) from exc
        if not isinstance(payload, dict):
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("invalid_json", status_code=status, detail="payload is not an object")

        rows = payload.get("results")
        if rows is None:
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("invalid_json", status_code=status, detail="missing results array")
        if not isinstance(rows, list):
            self.metrics.record_status(status, latency_ms, 0)
            self.breaker.record_failure()
            raise SearchBackendUnavailableError("invalid_json", status_code=status, detail="results is not an array")

        hits = [
            SearchHit(
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("content") or ""),
                engine=str(row.get("engine") or "") or None,
            )
            for row in rows[:limit]
            if isinstance(row, dict) and row.get("url")
        ]
        self.metrics.record_status(status, latency_ms, len(hits))
        self.metrics.record_engine_failures(_unresponsive_engines(payload))
        self.breaker.record_success()
        return hits


class ExplicitFailoverSearchBackend:
    """Opt-in recorded failover. Default discovery must not construct this."""

    def __init__(self, primary: SearxngHttpBackend, fallback: Any, *, policy: str) -> None:
        if policy != "ddgs":
            raise ValueError(f"unsupported explicit failover policy: {policy}")
        self.primary = primary
        self.fallback = fallback
        self.policy = policy
        self.backend_id = f"searxng_explicit_failover_{getattr(fallback, 'backend_id', policy)}"
        self.events: list[dict[str, Any]] = []
        self.failover_used = False

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        try:
            return self.primary.search(query, limit=limit)
        except SearchBackendUnavailableError as exc:
            self.failover_used = True
            self.events.append(
                {
                    "query": query,
                    "primary_reason": exc.reason,
                    "primary_status": exc.status_code,
                    "fallback": getattr(self.fallback, "backend_id", self.policy),
                    "policy": self.policy,
                    "hidden": False,
                }
            )
            return self.fallback.search(query, limit=limit)


def build_search_backend(
    search_backend: str,
    *,
    searxng_url: str | None = None,
    timeout_seconds: float = 12.0,
    failover: str | None = None,
    ddgs_factory: Any | None = None,
    **searxng_kwargs: Any,
) -> Any:
    """Wire the selected backend. Failover is explicit and recorded."""

    if search_backend == "off":
        raise ValueError("search backend is off")
    if search_backend == "ddgs":
        if ddgs_factory is not None:
            return ddgs_factory(timeout_seconds=timeout_seconds)
        from scripts.decision_unit_intelligence.web_discovery import DdgsSearchBackend

        return DdgsSearchBackend(timeout_seconds=timeout_seconds)
    if search_backend != "searxng":
        raise ValueError(f"unsupported search backend: {search_backend}")

    primary = SearxngHttpBackend(searxng_url or "", timeout_seconds=timeout_seconds, **searxng_kwargs)
    policy = resolve_failover_policy(failover)
    if policy == "off":
        return primary
    if ddgs_factory is not None:
        fallback = ddgs_factory(timeout_seconds=timeout_seconds)
    else:
        from scripts.decision_unit_intelligence.web_discovery import DdgsSearchBackend

        fallback = DdgsSearchBackend(timeout_seconds=timeout_seconds)
    return ExplicitFailoverSearchBackend(primary, fallback, policy=policy)
