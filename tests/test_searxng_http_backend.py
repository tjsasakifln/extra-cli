"""Contract tests for the shipped SearXNG HTTP client (local fixture only)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from scripts.decision_unit_intelligence.providers.public_search import PublicSearchProvider
from scripts.decision_unit_intelligence.search_http import (
    CircuitBreaker,
    ExplicitFailoverSearchBackend,
    SearchBackendUnavailableError,
    SearxngHttpBackend,
    build_search_backend,
    require_searxng_url,
)
from scripts.decision_unit_intelligence.web_discovery import (
    CachedRateLimitedSearchBackend,
    JsonDiscoveryCache,
    SearchHit,
)
from tests.test_decision_unit_web_discovery import _context


class _FixtureState:
    def __init__(self) -> None:
        self.mode = "ok"
        self.hits: list[dict[str, Any]] = [
            {
                "url": "https://empresaexemplo.com.br/institucional/diretoria",
                "title": "Empresa Exemplo - site oficial",
                "content": "Diretoria e contato institucional.",
                "engine": "duckduckgo",
            }
        ]
        self.unresponsive: list[list[str]] = []
        self.requests = 0
        self.last_query: str | None = None
        self.last_format: str | None = None


def _start_fixture(state: _FixtureState) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/search":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            state.requests += 1
            state.last_query = (params.get("q") or [""])[0]
            state.last_format = (params.get("format") or [""])[0]
            if state.mode == "stall":
                raise TimeoutError("fixture stall")
            if state.mode == "429":
                self.send_response(429)
                self.send_header("Retry-After", "7")
                self.end_headers()
                return
            if state.mode == "500":
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"upstream boom")
                return
            if state.mode == "html":
                body = b"<html><body>not json</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            payload = {"query": state.last_query, "results": state.hits, "unresponsive_engines": state.unresponsive}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


@pytest.fixture()
def searxng_fixture():
    state = _FixtureState()
    server, url = _start_fixture(state)
    try:
        yield state, url
    finally:
        server.shutdown()
        server.server_close()


def test_require_url_fails_closed_and_rejects_public_third_party() -> None:
    with pytest.raises(SearchBackendUnavailableError) as missing:
        require_searxng_url("  ")
    assert missing.value.reason == "missing_url"
    with pytest.raises(SearchBackendUnavailableError) as public:
        require_searxng_url("https://searx.be")
    assert public.value.reason == "public_instance_denied"
    assert require_searxng_url("http://127.0.0.1:18888") == "http://127.0.0.1:18888"


def test_json_hits_parse_from_shipped_client(searxng_fixture) -> None:
    state, url = searxng_fixture
    backend = SearxngHttpBackend(url, timeout_seconds=2.0)
    hits = backend.search("empresa exemplo diretor", limit=3)
    assert state.last_format == "json"
    assert hits == [
        SearchHit(
            url="https://empresaexemplo.com.br/institucional/diretoria",
            title="Empresa Exemplo - site oficial",
            snippet="Diretoria e contato institucional.",
            engine="duckduckgo",
        )
    ]
    snap = backend.metrics.snapshot()
    assert snap["requests"] == 1
    assert snap["status_counts"]["200"] == 1
    assert snap["result_count_last"] == 1


def test_429_5xx_timeout_and_circuit_are_unavailability_not_empty_success(searxng_fixture) -> None:
    state, url = searxng_fixture
    backend = SearxngHttpBackend(
        url,
        timeout_seconds=0.2,
        breaker=CircuitBreaker(failure_threshold=2, reset_timeout_seconds=30.0),
    )

    state.mode = "429"
    with pytest.raises(SearchBackendUnavailableError) as too_many:
        backend.search("q-429", limit=2)
    assert too_many.value.reason == "http_429"
    assert too_many.value.status_code == 429
    assert too_many.value.retry_after == "7"

    state.mode = "500"
    with pytest.raises(SearchBackendUnavailableError) as boom:
        backend.search("q-500", limit=2)
    assert boom.value.reason == "http_5xx"
    assert boom.value.status_code == 500

    with pytest.raises(SearchBackendUnavailableError) as opened:
        backend.search("q-circuit", limit=2)
    assert opened.value.reason == "circuit_open"
    assert state.requests == 2
    assert backend.metrics.snapshot()["circuit_opens"] == 1
    assert backend.metrics.snapshot()["http_429"] == 1
    assert backend.metrics.snapshot()["http_5xx"] == 1

    stall = SearxngHttpBackend("http://127.0.0.1:1", timeout_seconds=0.05)
    with pytest.raises(SearchBackendUnavailableError) as timed_out:
        stall.search("q-timeout", limit=1)
    assert timed_out.value.reason in {"timeout", "network"}


def test_failures_are_not_cached_as_empty_success(searxng_fixture, tmp_path: Path) -> None:
    state, url = searxng_fixture
    raw = SearxngHttpBackend(url, timeout_seconds=2.0)
    cached = CachedRateLimitedSearchBackend(
        raw,
        cache=JsonDiscoveryCache(tmp_path, ttl_days=7),
        min_interval_seconds=0,
    )
    state.mode = "429"
    with pytest.raises(SearchBackendUnavailableError):
        cached.search("same-query", limit=2)
    assert cached.cache_misses == 1
    assert JsonDiscoveryCache(tmp_path, ttl_days=7).get("search", "searxng|2|same-query") is None

    state.mode = "ok"
    hits = cached.search("same-query", limit=2)
    assert hits
    assert cached.cache_misses == 2
    replay = cached.search("same-query", limit=2)
    assert replay == hits
    assert cached.cache_hits == 1


def test_explicit_failover_is_recorded_and_default_build_does_not_hide_outage(searxng_fixture) -> None:
    state, url = searxng_fixture
    state.mode = "429"

    closed = build_search_backend("searxng", searxng_url=url, timeout_seconds=2.0, failover="off")
    with pytest.raises(SearchBackendUnavailableError) as blocked:
        closed.search("no-fallback", limit=1)
    assert blocked.value.reason == "http_429"

    class FakeDdgs:
        backend_id = "ddgs"

        def search(self, query: str, *, limit: int) -> list[SearchHit]:
            return [SearchHit(url="https://fallback.example/hit", title=query, snippet="ddgs")][:limit]

    wrapped = ExplicitFailoverSearchBackend(
        SearxngHttpBackend(url, timeout_seconds=2.0),
        FakeDdgs(),
        policy="ddgs",
    )
    hits = wrapped.search("with-fallback", limit=1)
    assert hits[0].url == "https://fallback.example/hit"
    assert wrapped.failover_used is True
    assert wrapped.backend_id == "searxng_explicit_failover_ddgs"
    assert wrapped.events[0]["primary_reason"] == "http_429"
    assert wrapped.events[0]["hidden"] is False


def test_public_search_maps_backend_outage_to_source_blocked(searxng_fixture) -> None:
    _state, url = searxng_fixture
    _state.mode = "429"
    provider = PublicSearchProvider(
        backend=SearxngHttpBackend(url, timeout_seconds=2.0),
        budget=__import__(
            "scripts.decision_unit_intelligence.web_discovery", fromlist=["SearchBudget"]
        ).SearchBudget(max_queries=2, max_results_per_query=2, max_pages=1, min_query_interval_seconds=0),
    )
    result = provider.collect(_context())
    assert result.attempts[0].blocked is True
    assert result.attempts[0].stop_reason == "SOURCE_BLOCKED"
    assert result.attempts[0].status == "blocked"
    assert result.attempts[0].extra["result_count"] == 0
    assert result.attempts[0].extra["failures"]
