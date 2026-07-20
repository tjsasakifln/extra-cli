"""Chaos tests: HTTP 429 fail-closed paths on the shipped resilience adapters."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult
from scripts.crawl.resilience.adapters import PNCPAdapter, ScComprasAdapter
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.state import EvidenceLedger, WatermarkStore


def _cfg(tmp_path: Path, **overrides: object) -> ResilienceConfig:
    """Build a fail-closed test config matching current ResilienceConfig fields."""
    base = dict(
        environment="test",
        execution_mode="fixture",
        connect_timeout=1,
        read_timeout=1,
        max_retries=1,
        base_delay=0,
        max_delay=0,
        jitter=0,
        rate_limit_fallback=0,
        request_delay=0,
        page_size=50,
        max_pages=10,
        circuit_breaker_threshold=2,
        circuit_breaker_cooldown=60,
        daily_request_budget=100,
        freshness_sla_hours=24,
        state_root=tmp_path,
        checkpoint_path=tmp_path / "checkpoints",
        raw_path=tmp_path / "raw",
        dlq_path=tmp_path / "dlq",
        evidence_path=tmp_path / "evidence",
        ops_path=tmp_path / "ops",
        breaker_path=tmp_path / "breakers",
        require_db=False,
    )
    base.update(overrides)
    return ResilienceConfig(**base)  # type: ignore[arg-type]


@pytest.mark.chaos
class Test429RateLimit:
    """429 must never become success/empty or advance watermark."""

    def test_pncp_429_is_rate_limited_checkpointed_no_watermark(self, tmp_path: Path) -> None:
        calls = 0

        def fetcher(*_args: object) -> FetchResult:
            nonlocal calls
            calls += 1
            return FetchResult(
                status="rate_limited",
                request_completed=False,
                http_status=429,
                errors=["HTTP 429"],
                metadata={"response_headers": {"Retry-After": "30"}},
            )

        adapter = PNCPAdapter(_cfg(tmp_path), page_fetcher=fetcher)
        adapter.legacy.INGESTION_MODALIDADES = [1]
        result = adapter.fetch(
            CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="chaos-429")
        )
        assert result.status == "rate_limited"
        assert result.empty_confirmed is False
        assert result.coverage_satisfactory is False
        assert adapter.checkpoints.pending("pncp")
        ledger = EvidenceLedger(tmp_path / "evidence")
        path, evidence = ledger.write(
            source="pncp",
            run_id="chaos-429",
            request_scope="w",
            result=result,
            window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
        )
        assert evidence["satisfactory"] is False
        wm = WatermarkStore(tmp_path / "ops" / "watermarks")
        with pytest.raises(ValueError):
            wm.commit(adapter.checkpoints.pending("pncp")[0], path, evidence)
        assert calls == 1

    def test_pncp_429_sequence_opens_circuit_breaker(self, tmp_path: Path) -> None:
        calls = 0

        def fetcher(*_args: object) -> FetchResult:
            nonlocal calls
            calls += 1
            return FetchResult(status="rate_limited", request_completed=False, http_status=429, errors=["HTTP 429"])

        adapter = PNCPAdapter(_cfg(tmp_path, circuit_breaker_threshold=2), page_fetcher=fetcher)
        adapter.legacy.INGESTION_MODALIDADES = [1]
        request = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17))
        assert adapter.fetch(request).status == "rate_limited"
        assert adapter.fetch(request).status == "rate_limited"
        third = adapter.fetch(request)
        assert third.status == "rate_limited"
        assert "circuit_breaker_open" in third.errors
        assert calls == 2

    def test_sc_compras_429_is_rate_limited_not_empty(self, tmp_path: Path) -> None:
        def list_fetcher(_year: int) -> tuple[list[dict], dict]:
            return [], {"ok": False, "http_status": 429, "error": "rate limited", "url": "fixture://sc"}

        adapter = ScComprasAdapter(_cfg(tmp_path), list_fetcher=list_fetcher)
        result = adapter.fetch(
            CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17))
        )
        assert result.status == "rate_limited"
        assert result.empty_confirmed is False
        assert result.coverage_satisfactory is False
        assert not result.records
