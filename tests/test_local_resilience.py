"""Contract, resume, evidence, DLQ, isolation and honesty tests for pre-VPS resilience."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult
from scripts.crawl.resilience.adapters import PNCPAdapter, ScComprasAdapter
from scripts.crawl.resilience.circuit_breaker import PersistentCircuitBreaker
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy
from scripts.crawl.resilience.persistence import InMemoryPersistence
from scripts.crawl.resilience.pipeline import OperationalPipeline
from scripts.crawl.resilience.stages import InvalidCheckpointTransition, validate_transition
from scripts.crawl.resilience.state import (
    CanonicalCheckpoint,
    CheckpointStore,
    EvidenceLedger,
    FileDLQ,
    RawStore,
    WatermarkStore,
    coerce_canonical_checkpoint,
)
from scripts.ops.health import collect_health
from scripts.ops.resilient_cycle import run_cycle
from scripts.ops.validate_systemd import validate as validate_systemd


def config(tmp_path: Path, **overrides: Any) -> ResilienceConfig:
    env = overrides.pop("environment", "fixture")
    mode = overrides.pop("execution_mode", "fixture")
    base = ResilienceConfig(
        environment=env,
        execution_mode=mode,
        connect_timeout=1,
        read_timeout=1,
        max_retries=1,
        base_delay=0,
        max_delay=0,
        jitter=0,
        rate_limit_fallback=0,
        request_delay=0,
        page_size=1,
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
    return replace(base, **overrides)


@pytest.mark.parametrize(
    ("http_status", "expected"),
    [(401, "auth_blocked"), (403, "auth_blocked"), (408, "error"), (425, "error"), (429, "rate_limited"), (500, "error"), (502, "error"), (503, "error"), (504, "error")],
)
def test_http_failures_never_become_empty(http_status: int, expected: str) -> None:
    result = FetchResult(request_completed=False, http_status=http_status, errors=[f"HTTP {http_status}"])
    assert result.status == expected
    assert result.empty_confirmed is False
    assert result.coverage_satisfactory is False


@pytest.mark.parametrize("error", ["timeout", "connection error", "200 HTML", "JSON invalido", "schema inesperado"])
def test_response_failures_are_error_not_empty(error: str) -> None:
    result = FetchResult(request_completed=False, http_status=200 if error.startswith("200") else None, errors=[error])
    assert result.status == "error"
    assert not result.empty_confirmed


def test_partial_pagination_forces_fail_closed() -> None:
    result = FetchResult(status="success", records=[{"id": 1}], request_completed=True, http_status=200, pages_fetched=1, pages_expected=2, provenance={"raw": "x"})
    assert result.status == "partial"
    assert not result.coverage_satisfactory


def test_204_empty_can_be_confirmed_only_with_complete_request() -> None:
    result = FetchResult(status="empty_confirmed", records=[], request_completed=True, http_status=204, empty_confirmed=True, pages_fetched=1, pages_expected=1, provenance={"raw": "x"})
    assert result.coverage_satisfactory
    with pytest.raises(ValueError):
        FetchResult(status="empty_confirmed", request_completed=False, empty_confirmed=True)


def test_zero_ambiguous_never_counts() -> None:
    result = FetchResult(status="partial", records=[], request_completed=True, http_status=200, provenance={"raw": "x"})
    assert not result.empty_confirmed
    assert not result.coverage_satisfactory


def test_raw_hash_is_reproducible_and_deduplicated(tmp_path: Path) -> None:
    store = RawStore(tmp_path / "raw")
    first, hash_a = store.persist(source="pncp", run_id="r1", request_scope="p1", payload={"b": 2, "a": 1}, provenance={"response_headers": {"Authorization": "secret", "ETag": "ok"}})
    second, hash_b = store.persist(source="pncp", run_id="r2", request_scope="p1", payload={"a": 1, "b": 2}, provenance={})
    assert first == second
    assert hash_a == hash_b
    saved = json.loads(first.read_text(encoding="utf-8"))
    assert "authorization" not in saved["provenance"]["response_headers"]


def test_checkpoint_atomic_resume_and_no_reprocess(tmp_path: Path) -> None:
    calls = 0
    payload = [{"numeroControlePNCP": "00000000000100-1-000001/2026", "orgaoEntidade": {"cnpj": "00000000000100"}, "unidadeOrgao": {}, "anoCompra": 2026, "sequencialCompra": 1}]

    def fetcher(_request, _modalidade, _page):
        nonlocal calls
        calls += 1
        return FetchResult(status="success", records=payload, request_completed=True, http_status=200, pages_fetched=1, pages_expected=1, provenance={"test": True}, metadata={"pagination": {"totalPaginas": 1, "paginasRestantes": 0}, "url": "fixture://pncp"})

    adapter = PNCPAdapter(config(tmp_path), page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    request = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="r1")
    first = adapter.fetch(request)
    scope = first.metadata["raw"][0]["request_scope"]
    cp = adapter.checkpoints.load("pncp", scope)
    assert cp and cp.status == "raw_persisted"
    assert first.pages_expected == 1
    cp.status = "success"
    adapter.checkpoints.save(cp)
    second = adapter.fetch(request)
    assert calls == 1
    assert second.records == payload
    assert second.metadata["pages_reused"] == 1
    assert second.pages_expected == 1
    assert second.pages_fetched == 1


def test_rate_limit_checkpoint_no_watermark(tmp_path: Path) -> None:
    def fetcher(*_args):
        return FetchResult(status="rate_limited", request_completed=False, http_status=429, errors=["HTTP 429"], provenance={"test": True})

    adapter = PNCPAdapter(config(tmp_path), page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    result = adapter.fetch(CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="r429"))
    assert result.status == "rate_limited"
    assert adapter.checkpoints.pending("pncp")
    assert not list((tmp_path / "ops" / "watermarks").glob("**/*.json"))


def test_circuit_breaker_persistent_across_instances(tmp_path: Path) -> None:
    cfg = config(tmp_path, circuit_breaker_threshold=2, circuit_breaker_cooldown=3600)
    calls = 0

    def fetcher(*_args):
        nonlocal calls
        calls += 1
        return FetchResult(status="rate_limited", request_completed=False, http_status=429, errors=["HTTP 429"])

    adapter = PNCPAdapter(cfg, page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    request = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17))
    assert adapter.fetch(request).status == "rate_limited"
    assert adapter.fetch(request).status == "rate_limited"
    # New process/instance must still be blocked without network.
    calls_before = calls
    adapter2 = PNCPAdapter(cfg, page_fetcher=fetcher)
    adapter2.legacy.INGESTION_MODALIDADES = [1]
    result = adapter2.fetch(request)
    assert result.status == "rate_limited"
    assert "circuit_breaker_open" in result.errors
    assert calls == calls_before  # no new HTTP


def test_daily_request_budget_blocks_new_slice(tmp_path: Path) -> None:
    calls = 0

    def fetcher(*_args):
        nonlocal calls
        calls += 1
        return FetchResult(status="success", records=[{"id": calls}], request_completed=True, http_status=200, metadata={"pagination": {"totalPaginas": 1, "paginasRestantes": 0}})

    adapter = PNCPAdapter(config(tmp_path, daily_request_budget=1), page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    first = CrawlRequest(mode="incremental", date_from=date(2026, 7, 16), date_to=date(2026, 7, 16))
    second = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17))
    assert adapter.fetch(first).status == "success"
    result = adapter.fetch(second)
    assert result.status == "rate_limited"
    assert "daily_request_budget_exhausted" in result.errors
    assert calls == 1


def test_evidence_and_watermark_require_provenance_and_completeness(tmp_path: Path) -> None:
    ledger = EvidenceLedger(tmp_path / "evidence")
    wm = WatermarkStore(tmp_path / "watermarks")
    cp = CanonicalCheckpoint(source="pncp", run_id="r", request_scope="w", status="partial")
    partial = FetchResult(status="partial", records=[{"id": 1}], request_completed=False, pages_fetched=1, pages_expected=2, provenance={"raw": "x"})
    path, evidence = ledger.write(
        source="pncp",
        run_id="r",
        request_scope="w",
        result=partial,
        window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
        environment="fixture",
        execution_mode="fixture",
    )
    assert not evidence["satisfactory"]
    with pytest.raises(ValueError):
        wm.commit(cp, path, evidence)

    complete = FetchResult(status="success", records=[{"id": 1}], request_completed=True, pages_fetched=2, pages_expected=2, provenance={"raw": "x"})
    path, evidence = ledger.write(
        source="pncp",
        run_id="r",
        request_scope="w",
        result=complete,
        window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
        environment="fixture",
        execution_mode="fixture",
        db_committed=False,
    )
    assert evidence["mechanics_satisfactory"]
    assert not evidence["operational_satisfactory"]
    cp.status = "success"
    assert wm.commit(cp, path, evidence).is_file()


def test_live_watermark_requires_db_committed(tmp_path: Path) -> None:
    ledger = EvidenceLedger(tmp_path / "evidence")
    wm = WatermarkStore(tmp_path / "watermarks")
    complete = FetchResult(status="success", records=[{"id": 1}], request_completed=True, pages_fetched=1, pages_expected=1, provenance={"raw": "x"})
    path, evidence = ledger.write(
        source="pncp",
        run_id="r",
        request_scope="w",
        result=complete,
        window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
        environment="development",
        execution_mode="live",
        db_committed=False,
    )
    assert not evidence["satisfactory"]
    cp = CanonicalCheckpoint(source="pncp", run_id="r", request_scope="w", status="success")
    with pytest.raises(ValueError):
        wm.commit(cp, path, evidence)


def test_dlq_dedup_batch_continue_and_replay(tmp_path: Path) -> None:
    dlq = FileDLQ(tmp_path / "dlq")
    good: list[int] = []
    for value in [1, "poison", 2]:
        try:
            if value == "poison":
                raise ValueError("invalid record")
            good.append(value)
        except ValueError as exc:
            dlq.push(source="pncp", run_id="r", payload={"value": value}, error=exc)
            dlq.push(source="pncp", run_id="r", payload={"value": value}, error=exc)
    assert good == [1, 2]
    assert len(dlq.pending()) == 1
    record = json.loads(dlq.pending()[0].read_text(encoding="utf-8"))
    assert record["attempts"] == 2
    assert dlq.replay(lambda row: good.append(3), source="pncp") == (1, 0)
    assert not dlq.pending()


def test_sc_compras_zero_is_ambiguous(tmp_path: Path) -> None:
    adapter = ScComprasAdapter(config(tmp_path), list_fetcher=lambda _year: ([], {"ok": True, "total_elementos": 0, "url": "fixture://sc"}))
    result = adapter.fetch(CrawlRequest(mode="incremental", date_from=date.today(), date_to=date.today()))
    assert result.status == "partial"
    assert not result.empty_confirmed


def test_sc_compras_snapshot_resume_without_http(tmp_path: Path) -> None:
    calls = 0
    items = [{"id": 1}, {"id": 2}]

    def fetcher(_year: int):
        nonlocal calls
        calls += 1
        return items, {"ok": True, "total_elementos": 2, "url": "fixture://sc"}

    adapter = ScComprasAdapter(config(tmp_path, page_size=1, max_pages=10), list_fetcher=fetcher)
    request = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="sc1")
    first = adapter.fetch(request)
    assert first.status == "success"
    assert first.pages_fetched == 2
    assert calls == 1
    assert first.metadata["snapshot_hash"]
    second = adapter.fetch(request)
    assert second.status == "success"
    assert calls == 1  # snapshot resume — no new HTTP
    assert {row["id"] for row in second.records} == {1, 2}


def test_sc_compras_order_change_invalidates_cross_snapshot_mix(tmp_path: Path) -> None:
    """Changing order between fetches yields a new snapshot_hash — no silent mix."""
    seq = [
        ([{"id": 1}, {"id": 2}], {"ok": True, "total_elementos": 2, "url": "fixture://sc"}),
        ([{"id": 2}, {"id": 1}], {"ok": True, "total_elementos": 2, "url": "fixture://sc"}),
    ]
    calls = 0

    def fetcher(_year: int):
        nonlocal calls
        payload = seq[min(calls, len(seq) - 1)]
        calls += 1
        return payload

    adapter = ScComprasAdapter(config(tmp_path, page_size=1), list_fetcher=fetcher)
    req = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="sc-order")
    first = adapter.fetch(req)
    h1 = first.metadata["snapshot_hash"]
    # Force re-fetch by removing snapshot checkpoint but keeping chunk files would be unsafe;
    # full re-fetch of bulk produces different hash.
    snap_scope = "year=2026|snapshot"
    adapter.checkpoints.path_for("sc_compras", snap_scope).unlink(missing_ok=True)
    second = adapter.fetch(req)
    h2 = second.metadata["snapshot_hash"]
    assert h1 != h2
    assert calls == 2


def test_sc_compras_incomplete_bulk_never_success(tmp_path: Path) -> None:
    items = [{"id": i} for i in range(50)]

    def list_fetcher(_year: int) -> tuple[list[dict], dict]:
        return items, {"ok": True, "total_elementos": 100, "url": "fixture://sc-incomplete"}

    adapter = ScComprasAdapter(config(tmp_path, page_size=50, max_pages=10), list_fetcher=list_fetcher)
    result = adapter.fetch(
        CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), run_id="sc-incomplete")
    )
    assert result.status == "partial"
    assert result.empty_confirmed is False
    assert result.coverage_satisfactory is False
    assert len(result.records) == 50


def test_fixture_cycle_never_makes_live_health_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESILIENCE_STATE_PATH", str(tmp_path))
    monkeypatch.setenv("RESILIENCE_ENV", "fixture")
    monkeypatch.setenv("RESILIENCE_PAGE_SIZE", "1")
    monkeypatch.setenv("RESILIENCE_REQUEST_DELAY", "0")
    monkeypatch.setenv("RESILIENCE_REQUIRE_DB", "0")
    fixtures = Path("tests/fixtures/resilience")
    cfg = ResilienceConfig.from_env(environment="fixture", execution_mode="fixture")
    code1, first = run_cycle(fixture_dir=fixtures, config=cfg, persistence=InMemoryPersistence())
    code2, second = run_cycle(fixture_dir=fixtures, config=cfg, persistence=InMemoryPersistence())
    assert code1 == code2 == 0
    assert first["status"] == "TEST_HEALTHY"
    assert second["status"] == "TEST_HEALTHY"
    assert all(row.get("satisfactory") for row in second["results"].values())
    assert all(not row.get("operational_satisfactory") for row in second["results"].values())

    # Fixture health may be green.
    fixture_code, fixture_health = collect_health(env="fixture")
    assert fixture_code == 0
    assert fixture_health["status"] == "TEST_HEALTHY"

    # Live health remains blocked — no live watermark.
    live_code, live_health = collect_health(env="development")
    assert live_code == 2
    assert live_health["status"] == "no_live_evidence"
    assert not list((tmp_path / "development" / "ops" / "watermarks").glob("**/*.json")) if (tmp_path / "development").exists() else True


def test_checkpoint_invalid_schema_fails_explicitly() -> None:
    with pytest.raises(TypeError, match="checkpoint schema invalido"):
        coerce_canonical_checkpoint({"page_scopes": ["a"], "pages_reused": 1})


def test_checkpoint_invalid_transition_raises() -> None:
    with pytest.raises(InvalidCheckpointTransition):
        validate_transition("watermark_committed", "raw_persisted")


def test_pncp_orchestrator_resume_after_429(tmp_path: Path) -> None:
    """Real orchestrator: page1 raw, page2 429 → resume reuses page1, completes window."""
    pages_hit: list[int] = []

    def fetcher(_request, _modalidade, page: int):
        pages_hit.append(page)
        if page == 1:
            return FetchResult(
                status="success",
                records=[{"numeroControlePNCP": "1", "orgaoEntidade": {"cnpj": "1"}, "unidadeOrgao": {}, "anoCompra": 2026, "sequencialCompra": 1}],
                request_completed=True,
                http_status=200,
                provenance={"p": 1},
                metadata={"pagination": {"totalPaginas": 2, "paginasRestantes": 1, "totalRegistros": 2, "numeroPagina": 1, "empty": False}, "url": "fixture://p1"},
            )
        if len([p for p in pages_hit if p == 2]) == 1:
            return FetchResult(status="rate_limited", request_completed=False, http_status=429, errors=["HTTP 429"], provenance={"p": 2})
        return FetchResult(
            status="success",
            records=[{"numeroControlePNCP": "2", "orgaoEntidade": {"cnpj": "1"}, "unidadeOrgao": {}, "anoCompra": 2026, "sequencialCompra": 2}],
            request_completed=True,
            http_status=200,
            provenance={"p": 2},
            metadata={"pagination": {"totalPaginas": 2, "paginasRestantes": 0, "totalRegistros": 2, "numeroPagina": 2, "empty": False}, "url": "fixture://p2"},
        )

    cfg = config(tmp_path, environment="fixture", execution_mode="fixture", page_size=1, max_pages=10, request_delay=0)
    # Patch transform to identity for stable normalize.
    adapter = PNCPAdapter(cfg, page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    adapter.normalize = lambda raw: list(raw)  # type: ignore[method-assign]

    pipeline = OperationalPipeline(cfg, persistence=InMemoryPersistence())
    scope = "mode=incremental|date=2026-07-17"
    req = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), request_scope=scope, run_id="run1", source="pncp")

    out1 = pipeline.run_source(adapter, req, run_id="run1")
    assert out1["status"] in {"rate_limited", "partial", "error"} or not out1.get("satisfactory")
    assert not out1.get("watermark")
    assert 1 in pages_hit and 2 in pages_hit

    # Second run — new process semantics (new pipeline), same state paths.
    pipeline2 = OperationalPipeline(cfg, persistence=InMemoryPersistence())
    adapter2 = PNCPAdapter(cfg, page_fetcher=fetcher)
    adapter2.legacy.INGESTION_MODALIDADES = [1]
    adapter2.normalize = lambda raw: list(raw)  # type: ignore[method-assign]
    hits_before = list(pages_hit)
    out2 = pipeline2.run_source(adapter2, req, run_id="run2")
    # Page 1 must not be re-fetched.
    assert pages_hit.count(1) == hits_before.count(1)
    assert pages_hit.count(2) >= 2
    assert out2.get("satisfactory") is True
    pending = CheckpointStore(cfg.checkpoint_path).pending("pncp")
    # Page scopes should be complete; run may still list non-pending.
    page_pending = [p for p in pending if "page=" in p.request_scope]
    assert page_pending == []
    assert out2.get("watermark")
    assert (cfg.ops_path / "watermarks" / "pncp").exists()


def test_http_policy_from_env_prefers_resilience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESILIENCE_MAX_RETRIES", "3")
    monkeypatch.setenv("PNCP_MAX_RETRIES", "99")
    monkeypatch.setenv("RESILIENCE_CONNECT_TIMEOUT", "2.5")
    policy = HttpResiliencePolicy.from_env()
    assert policy.max_retries == 3
    assert policy.connect_timeout == 2.5


def test_http_policy_legacy_mapping_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESILIENCE_MAX_RETRIES", raising=False)
    monkeypatch.setenv("PNCP_MAX_RETRIES", "7")
    with pytest.warns(DeprecationWarning, match="deprecadas"):
        policy = HttpResiliencePolicy.from_env()
    assert policy.max_retries == 7


def test_http_policy_retry_after_prevails() -> None:
    policy = HttpResiliencePolicy(base_delay=10, max_delay=100, jitter=0)
    assert policy.retry_delay(0, retry_after=3.0) == 3.0


def test_http_policy_respected_by_pncp_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.crawl import pncp_crawler_adapter as pncp

    sleeps: list[float] = []
    attempts = {"n": 0}

    class FakeResp:
        status_code = 429
        headers = {"Retry-After": "2", "content-type": "application/json"}

    class FakeSession:
        def get(self, *args, **kwargs):
            attempts["n"] += 1
            assert kwargs["timeout"] == (1.0, 5.0)
            return FakeResp()

    policy = HttpResiliencePolicy(connect_timeout=1.0, read_timeout=5.0, max_retries=2, base_delay=1, max_delay=10, jitter=0, retry_after_fallback=60)
    result = pncp._http_get_json(
        "https://example.test/x",
        session=FakeSession(),  # type: ignore[arg-type]
        sleeper=lambda s: sleeps.append(s),
        http_policy=policy,
    )
    assert result.status == "rate_limited" or not result.request_completed
    assert attempts["n"] == 3  # initial + 2 retries
    assert sleeps and all(s == 2.0 for s in sleeps)  # Retry-After prevails


def test_freshness_recent_fetch_old_content(tmp_path: Path) -> None:
    cfg = config(tmp_path, environment="development", execution_mode="live")
    cfg.ops_path.mkdir(parents=True, exist_ok=True)
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    now = datetime.now(UTC).isoformat()
    history_dir = cfg.ops_path / "run_history" / "pncp"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "20260717.jsonl").write_text(
        json.dumps(
            {
                "source": "pncp",
                "finished_at": now,
                "status": "success",
                "satisfactory": True,
                "operational_satisfactory": True,
                "db_committed": True,
                "execution_mode": "live",
                "environment": "development",
                "content_max_timestamp": old,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # Minimal latest so not no_live_evidence
    (cfg.ops_path / "latest.json").write_text(
        json.dumps(
            {
                "run_id": "r",
                "mode": "live",
                "environment": "development",
                "execution_mode": "live",
                "results": {
                    "pncp": {"status": "success", "satisfactory": True, "operational_satisfactory": True, "db_committed": True, "db_records_committed": 1, "content_max_timestamp": old},
                    "ciga_dom": {"status": "success", "satisfactory": True, "operational_satisfactory": True, "db_committed": True, "db_records_committed": 1},
                    "sc_compras": {"status": "success", "satisfactory": True, "operational_satisfactory": True, "db_committed": True, "db_records_committed": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    for src in ("pncp", "ciga_dom", "sc_compras"):
        p = cfg.ops_path / "latest_sources" / f"{src}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "started_at": now,
                    "environment": "development",
                    "execution_mode": "live",
                    "result": {
                        "status": "success",
                        "satisfactory": True,
                        "operational_satisfactory": True,
                        "db_committed": True,
                        "db_records_committed": 1,
                        "content_max_timestamp": old if src == "pncp" else now,
                    },
                }
            ),
            encoding="utf-8",
        )
        hd = cfg.ops_path / "run_history" / src
        hd.mkdir(parents=True, exist_ok=True)
        (hd / "h.jsonl").write_text(
            json.dumps(
                {
                    "source": src,
                    "finished_at": now,
                    "status": "success",
                    "satisfactory": True,
                    "operational_satisfactory": True,
                    "db_committed": True,
                    "execution_mode": "live",
                    "environment": "development",
                    "content_max_timestamp": old if src == "pncp" else now,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    code, report = collect_health(cfg, env="development")
    pncp = report["sources"]["pncp"]
    assert pncp["collection_freshness"] == "current"
    assert pncp["content_freshness"] == "stale"
    assert pncp["operational_freshness"] == "stale"
    assert code == 2


def test_last_success_preserved_after_failure(tmp_path: Path) -> None:
    cfg = config(tmp_path, environment="development", execution_mode="live")
    hd = cfg.ops_path / "run_history" / "pncp"
    hd.mkdir(parents=True, exist_ok=True)
    success_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    fail_at = datetime.now(UTC).isoformat()
    (hd / "h.jsonl").write_text(
        json.dumps(
            {
                "source": "pncp",
                "finished_at": success_at,
                "status": "success",
                "satisfactory": True,
                "operational_satisfactory": True,
                "db_committed": True,
                "execution_mode": "live",
                "environment": "development",
                "content_max_timestamp": success_at,
            }
        )
        + "\n"
        + json.dumps(
            {
                "source": "pncp",
                "finished_at": fail_at,
                "status": "error",
                "satisfactory": False,
                "operational_satisfactory": False,
                "db_committed": False,
                "execution_mode": "live",
                "environment": "development",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (cfg.ops_path / "latest.json").write_text(
        json.dumps({"run_id": "x", "mode": "live", "environment": "development", "execution_mode": "live", "results": {}}),
        encoding="utf-8",
    )
    for src in ("pncp", "ciga_dom", "sc_compras"):
        p = cfg.ops_path / "latest_sources" / f"{src}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"environment": "development", "execution_mode": "live", "result": {"status": "error"}}), encoding="utf-8")
        if src != "pncp":
            h2 = cfg.ops_path / "run_history" / src
            h2.mkdir(parents=True, exist_ok=True)
            (h2 / "h.jsonl").write_text(
                json.dumps(
                    {
                        "source": src,
                        "finished_at": success_at,
                        "status": "success",
                        "satisfactory": True,
                        "operational_satisfactory": True,
                        "db_committed": True,
                        "execution_mode": "live",
                        "environment": "development",
                        "content_max_timestamp": success_at,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
    code, report = collect_health(cfg, env="development")
    assert report["sources"]["pncp"]["last_operational_success"] is not None
    assert report["sources"]["pncp"]["last_attempt"] is not None
    assert report["sources"]["pncp"]["last_operational_success"] < report["sources"]["pncp"]["last_attempt"]


def test_pipeline_crash_after_db_repairs_watermark(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    mem = InMemoryPersistence()
    records = [{"pncp_id": "x1", "orgao_cnpj": "123", "id": 1}]

    class StubAdapter:
        source_id = "pncp"

        def health(self):
            from scripts.crawl.ingestion._base.crawler import SourceHealth

            return SourceHealth(source="pncp", status="healthy", message="ok")

        def fetch(self, request):
            return FetchResult(
                status="success",
                records=records,
                request_completed=True,
                pages_fetched=1,
                pages_expected=1,
                http_status=200,
                provenance={"raw": "ok"},
                metadata={"raw": []},
            )

        def normalize(self, raw):
            return list(raw)

    scope = "mode=incremental|date=2026-07-17"
    req = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17), request_scope=scope, run_id="crash1", source="pncp")
    p1 = OperationalPipeline(cfg, persistence=mem, crash_after="evidence_committed")
    out1 = p1.run_source(StubAdapter(), req, run_id="crash1")  # type: ignore[arg-type]
    assert out1["status"] == "error"
    assert mem.rows  # DB side effect kept
    # Rerun without crash completes evidence+watermark without re-duplicating.
    p2 = OperationalPipeline(cfg, persistence=mem)
    out2 = p2.run_source(StubAdapter(), req, run_id="crash1")  # type: ignore[arg-type]
    assert out2.get("satisfactory") is True
    assert mem.call_count >= 1


def test_migration_enforces_fail_closed_evidence() -> None:
    sql = Path("db/migrations/054_local_resilience_contract.sql").read_text(encoding="utf-8")
    assert "ck_coverage_evidence_satisfactory" in sql
    assert "pages_fetched >= pages_expected" in sql
    assert "provenance <> '{}'::jsonb" in sql


def test_systemd_priority_units_are_statically_safe() -> None:
    assert validate_systemd() == []


def test_checkpoint_state_machine_happy_path() -> None:
    validate_transition("pending", "raw_persisted")
    validate_transition("raw_persisted", "normalized")
    validate_transition("normalized", "db_committed")
    validate_transition("db_committed", "evidence_committed")
    validate_transition("evidence_committed", "watermark_committed")


def test_breaker_fixture_isolated_from_live(tmp_path: Path) -> None:
    live = PersistentCircuitBreaker(tmp_path / "breakers", environment="development", source="pncp", threshold=1, cooldown_seconds=1000)
    fix = PersistentCircuitBreaker(tmp_path / "breakers", environment="fixture", source="pncp", threshold=1, cooldown_seconds=1000)
    live.record_failure(http_status=429)
    assert not live.allow_request()
    assert fix.allow_request()
