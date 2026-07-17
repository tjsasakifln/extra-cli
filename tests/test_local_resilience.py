"""Contract, resume, evidence, DLQ and idempotency tests for pre-VPS resilience."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult
from scripts.crawl.resilience.adapters import PNCPAdapter, ScComprasAdapter
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.state import (
    CanonicalCheckpoint,
    CheckpointStore,
    EvidenceLedger,
    FileDLQ,
    RawStore,
    WatermarkStore,
)
from scripts.ops.health import collect_health
from scripts.ops.resilient_cycle import run_cycle
from scripts.ops.validate_systemd import validate as validate_systemd


def config(tmp_path: Path, **overrides) -> ResilienceConfig:
    base = ResilienceConfig(
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
        checkpoint_path=tmp_path / "checkpoints",
        raw_path=tmp_path / "raw",
        dlq_path=tmp_path / "dlq",
        evidence_path=tmp_path / "evidence",
        ops_path=tmp_path / "ops",
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


def test_circuit_breaker_opens_without_infinite_retry(tmp_path: Path) -> None:
    calls = 0

    def fetcher(*_args):
        nonlocal calls
        calls += 1
        return FetchResult(status="rate_limited", request_completed=False, http_status=429, errors=["HTTP 429"])

    adapter = PNCPAdapter(config(tmp_path), page_fetcher=fetcher)
    adapter.legacy.INGESTION_MODALIDADES = [1]
    request = CrawlRequest(mode="incremental", date_from=date(2026, 7, 17), date_to=date(2026, 7, 17))
    assert adapter.fetch(request).status == "rate_limited"
    assert adapter.fetch(request).status == "rate_limited"
    result = adapter.fetch(request)
    assert result.status == "rate_limited"
    assert "circuit_breaker_open" in result.errors
    assert calls == 2


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
    path, evidence = ledger.write(source="pncp", run_id="r", request_scope="w", result=partial, window={"date_from": "2026-07-17", "date_to": "2026-07-17"})
    assert not evidence["satisfactory"]
    with pytest.raises(ValueError):
        wm.commit(cp, path, evidence)

    complete = FetchResult(status="success", records=[{"id": 1}], request_completed=True, pages_fetched=2, pages_expected=2, provenance={"raw": "x"})
    path, evidence = ledger.write(source="pncp", run_id="r", request_scope="w", result=complete, window={"date_from": "2026-07-17", "date_to": "2026-07-17"})
    cp.status = "success"
    assert wm.commit(cp, path, evidence).is_file()


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


def test_sc_compras_raw_persisted_is_not_refetched(tmp_path: Path) -> None:
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
    second = adapter.fetch(request)
    assert second.status == "success"
    assert second.pages_fetched == 2
    assert calls == 2  # list meta may re-run; pages must come from raw
    assert {row["id"] for row in second.records} == {1, 2}
    # No extra raw files for the same page scopes.
    raw_files = list((tmp_path / "raw" / "sc_compras").rglob("*.json"))
    assert len(raw_files) == 2


def test_controlled_cycle_is_idempotent_and_health_is_single_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RESILIENCE_STATE_PATH", str(tmp_path))
    monkeypatch.setenv("RESILIENCE_PAGE_SIZE", "1")
    monkeypatch.setenv("RESILIENCE_REQUEST_DELAY", "0")
    fixtures = Path("tests/fixtures/resilience")
    code1, first = run_cycle(fixture_dir=fixtures)
    code2, second = run_cycle(fixture_dir=fixtures)
    assert code1 == code2 == 0
    assert all(row["satisfactory"] for row in second["results"].values())
    canonical_hashes_1 = {s: row["checkpoint"]["content_hash"] for s, row in first["results"].items()}
    canonical_hashes_2 = {s: row["checkpoint"]["content_hash"] for s, row in second["results"].items()}
    assert canonical_hashes_1 == canonical_hashes_2
    health_code, health = collect_health(config(tmp_path))
    assert health_code == 0
    assert health["status"] == "healthy"


def test_crash_after_raw_does_not_advance_watermark(tmp_path: Path) -> None:
    raw = RawStore(tmp_path / "raw")
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    raw_path, digest = raw.persist(source="pncp", run_id="r", request_scope="p1", payload={"data": [1]}, provenance={})
    checkpoints.save(CanonicalCheckpoint(source="pncp", run_id="r", request_scope="p1", status="raw_persisted", content_hash=digest, raw_reference=str(raw_path)))
    assert not list((tmp_path / "watermarks").glob("**/*.json"))
    assert checkpoints.pending("pncp")[0].status == "raw_persisted"


def test_crash_after_canonical_before_evidence_does_not_advance_watermark(tmp_path: Path) -> None:
    """Canonical persisted, evidence incomplete → WatermarkStore must refuse commit."""
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    ledger = EvidenceLedger(tmp_path / "evidence")
    watermarks = WatermarkStore(tmp_path / "watermarks")
    canonical = tmp_path / "canonical.json"
    canonical.write_text('[{"id": 1}]', encoding="utf-8")

    # Simulate crash after canonical write: checkpoint still partial, provenance incomplete.
    cp = CanonicalCheckpoint(
        source="pncp",
        run_id="crash-r1",
        request_scope="window=2026-07-17:2026-07-17|modalidade=1|page=1",
        status="partial",
        pages_fetched=1,
        pages_expected=2,
    )
    checkpoints.save(cp)
    incomplete = FetchResult(
        status="partial",
        records=[{"id": 1}],
        request_completed=False,
        pages_fetched=1,
        pages_expected=2,
        provenance={},  # missing provenance blocks satisfactory evidence
    )
    path, evidence = ledger.write(
        source="pncp",
        run_id="crash-r1",
        request_scope=cp.request_scope,
        result=incomplete,
        window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
    )
    assert evidence["satisfactory"] is False
    with pytest.raises(ValueError, match="watermark exige"):
        watermarks.commit(cp, path, evidence)
    assert not list((tmp_path / "watermarks").glob("**/*.json"))
    assert checkpoints.pending("pncp")
    assert canonical.is_file()


def test_sc_compras_incomplete_bulk_never_success(tmp_path: Path) -> None:
    """total_elementos > len(items) must be partial — empty virtual pages are not completeness."""
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
    assert result.pages_fetched < result.pages_expected
    assert any("records_lt_reported_total" in w or "empty_virtual_page" in w for w in result.warnings)
    ledger = EvidenceLedger(tmp_path / "evidence")
    _path, evidence = ledger.write(
        source="sc_compras",
        run_id="sc-incomplete",
        request_scope="year=2026",
        result=result,
        window={"date_from": "2026-07-17", "date_to": "2026-07-17"},
    )
    assert evidence["satisfactory"] is False


def test_migration_enforces_fail_closed_evidence() -> None:
    sql = Path("db/migrations/054_local_resilience_contract.sql").read_text(encoding="utf-8")
    assert "ck_coverage_evidence_satisfactory" in sql
    assert "pages_fetched >= pages_expected" in sql
    assert "provenance <> '{}'::jsonb" in sql


def test_systemd_priority_units_are_statically_safe() -> None:
    assert validate_systemd() == []
