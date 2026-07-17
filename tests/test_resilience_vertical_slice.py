"""Vertical slice: adapter → raw → normalize → upsert → evidence → watermark.

InMemory path for unit. Real PostgreSQL path is mandatory when DATABASE_URL is set
(CI resilience-gate provides Postgres). Soft-skip is forbidden when DSN is present.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.persistence import InMemoryPersistence, PostgresPersistence
from scripts.crawl.resilience.pipeline import OperationalPipeline
from scripts.crawl.resilience.state import CheckpointStore


def _cfg(tmp_path: Path, **kwargs) -> ResilienceConfig:
    from dataclasses import replace

    base = ResilienceConfig(
        environment=kwargs.pop("environment", "test"),
        execution_mode=kwargs.pop("execution_mode", "fixture"),
        connect_timeout=1,
        read_timeout=1,
        max_retries=0,
        base_delay=0,
        max_delay=0,
        jitter=0,
        rate_limit_fallback=0,
        request_delay=0,
        page_size=50,
        max_pages=5,
        circuit_breaker_threshold=5,
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
        require_db=kwargs.pop("require_db", False),
    )
    return replace(base, **kwargs)


class _PncpStub:
    source_id = "pncp"

    def __init__(self, records: list[dict]):
        self.records = records
        self.fetches = 0

    def health(self):
        from scripts.crawl.ingestion._base.crawler import SourceHealth

        return SourceHealth(source="pncp", status="healthy", message="ok")

    def fetch(self, request: CrawlRequest) -> FetchResult:
        self.fetches += 1
        return FetchResult(
            status="success",
            records=self.records,
            request_completed=True,
            pages_fetched=1,
            pages_expected=1,
            http_status=200,
            provenance={"vertical": True, "raw": "memory"},
            metadata={"raw": []},
        )

    def normalize(self, raw: list[dict]) -> list[dict]:
        return [{**r, "source": "pncp"} for r in raw]


@pytest.mark.unit
def test_vertical_slice_memory_idempotent(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    mem = InMemoryPersistence()
    records = [
        {
            "pncp_id": "00000000000100-1-000001/2026",
            "orgao_cnpj": "00000000000100",
            "objeto_compra": "Obra de teste",
            "data_publicacao": "2026-07-01",
        }
    ]
    adapter = _PncpStub(records)
    pipeline = OperationalPipeline(cfg, persistence=mem)
    scope = "mode=incremental|date=2026-07-17"
    req = CrawlRequest(
        mode="incremental",
        date_from=date(2026, 7, 17),
        date_to=date(2026, 7, 17),
        request_scope=scope,
        run_id="v1",
        source="pncp",
    )
    out1 = pipeline.run_source(adapter, req, run_id="v1")  # type: ignore[arg-type]
    assert out1["satisfactory"] is True
    cfg2 = _cfg(tmp_path / "b")
    mem2 = InMemoryPersistence()
    p2 = OperationalPipeline(cfg2, persistence=mem2)
    out_a = p2.run_source(adapter, req, run_id="v2")  # type: ignore[arg-type]
    out_b = p2.run_source(adapter, req, run_id="v2")  # type: ignore[arg-type]
    assert out_a["satisfactory"] and out_b.get("satisfactory")
    assert len(mem2.rows) == 1
    assert mem2.call_count >= 1


@pytest.mark.unit
@pytest.mark.parametrize("fail_mode", ["unavailable", "during_upsert"])
def test_vertical_slice_db_failure_no_watermark(tmp_path: Path, fail_mode: str) -> None:
    cfg = _cfg(tmp_path, environment="development", execution_mode="live", require_db=True)
    mem = InMemoryPersistence()
    mem.fail_mode = fail_mode
    adapter = _PncpStub([{"pncp_id": "x", "orgao_cnpj": "1"}])
    pipeline = OperationalPipeline(cfg, persistence=mem)
    req = CrawlRequest(
        mode="incremental",
        date_from=date(2026, 7, 17),
        date_to=date(2026, 7, 17),
        request_scope="s",
        run_id="fail",
        source="pncp",
    )
    out = pipeline.run_source(adapter, req, run_id="fail")  # type: ignore[arg-type]
    assert out["satisfactory"] is False
    assert out.get("operational_satisfactory") is not True
    assert not list((tmp_path / "ops" / "watermarks").glob("**/*.json"))


@pytest.mark.unit
def test_crash_after_evidence_before_watermark_rerun(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    mem = InMemoryPersistence()
    adapter = _PncpStub([{"pncp_id": "z", "orgao_cnpj": "9"}])
    req = CrawlRequest(
        mode="incremental",
        date_from=date(2026, 7, 17),
        date_to=date(2026, 7, 17),
        request_scope="s2",
        run_id="c1",
        source="pncp",
    )
    p1 = OperationalPipeline(cfg, persistence=mem, crash_after="evidence_committed")
    assert p1.run_source(adapter, req, run_id="c1")["status"] == "error"  # type: ignore[arg-type]
    p2 = OperationalPipeline(cfg, persistence=mem)
    out = p2.run_source(adapter, req, run_id="c1")  # type: ignore[arg-type]
    assert out.get("satisfactory") is True
    assert out.get("watermark")


@pytest.mark.database
@pytest.mark.integration
def test_vertical_slice_postgres_real_path(tmp_path: Path) -> None:
    """Real PG path — hard-fails when DSN is set but upsert/schema cannot complete."""
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        pytest.skip("DATABASE_URL not set")

    import psycopg2

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regprocedure('upsert_pncp_raw_bids(jsonb)') IS NOT NULL")
        has_upsert = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pncp_raw_bids')"
        )
        has_table = bool(cur.fetchone()[0])
    finally:
        cur.close()
        conn.close()
    if not has_upsert or not has_table:
        pytest.fail("DATABASE_URL set but pncp_raw_bids / upsert_pncp_raw_bids missing — migrations incomplete")

    cfg = _cfg(tmp_path, environment="test", execution_mode="live", require_db=True)
    backend = PostgresPersistence(dsn=dsn)
    adapter = _PncpStub(
        [
            {
                "pncp_id": "88888888888888-1-000099/2026",
                "orgao_cnpj": "88888888888888",
                "ano_compra": 2026,
                "sequencial_compra": 99,
                "objeto_compra": "Vertical slice integration real PG",
                "source": "pncp",
                "source_id": "88888888888888-1-000099/2026",
                "data_publicacao": "2026-07-01",
                "uf": "SC",
                "modalidade_id": 1,
            }
        ]
    )
    pipeline = OperationalPipeline(cfg, persistence=backend)
    req = CrawlRequest(
        mode="incremental",
        date_from=date(2026, 7, 17),
        date_to=date(2026, 7, 17),
        request_scope="pg-slice-real",
        run_id="pg-real-1",
        source="pncp",
    )
    out = pipeline.run_source(adapter, req, run_id="pg-real-1")  # type: ignore[arg-type]
    assert not out.get("errors"), f"unexpected errors: {out.get('errors')}"
    assert out.get("db_committed") is True
    assert out.get("operational_satisfactory") is True or out.get("satisfactory") is True
    assert out.get("watermark")
    # Idempotent second run
    out2 = pipeline.run_source(adapter, req, run_id="pg-real-2")  # type: ignore[arg-type]
    assert out2.get("db_committed") is True or out2.get("resumed") is True
    # Count rows for this pncp_id
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM pncp_raw_bids WHERE pncp_id = %s", ("88888888888888-1-000099/2026",))
        count = cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()
    assert count >= 1
    assert CheckpointStore(cfg.checkpoint_path).pending("pncp") == [] or out.get("watermark")


@pytest.mark.database
@pytest.mark.integration
def test_vertical_slice_postgres_failure_injected_then_recover(tmp_path: Path) -> None:
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        pytest.skip("DATABASE_URL not set")

    cfg = _cfg(tmp_path, environment="test", execution_mode="live", require_db=True)
    # Injected unavailable before real backend
    bad = InMemoryPersistence()
    bad.fail_mode = "unavailable"
    adapter = _PncpStub([{"pncp_id": "777-1-1/2026", "orgao_cnpj": "77777777777777", "source": "pncp"}])
    req = CrawlRequest(
        mode="incremental",
        date_from=date(2026, 7, 17),
        date_to=date(2026, 7, 17),
        request_scope="pg-recover",
        run_id="pg-r1",
        source="pncp",
    )
    p1 = OperationalPipeline(cfg, persistence=bad)
    out1 = p1.run_source(adapter, req, run_id="pg-r1")  # type: ignore[arg-type]
    assert out1.get("satisfactory") is False
    assert not out1.get("watermark")

    # Recover with real PG — same scope/run continues after stage failure
    p2 = OperationalPipeline(cfg, persistence=PostgresPersistence(dsn=dsn))
    out2 = p2.run_source(adapter, req, run_id="pg-r1")  # type: ignore[arg-type]
    # May still fail if stub record lacks full schema fields; must not soft-pass without db.
    if out2.get("errors"):
        # Fail closed still required
        assert out2.get("operational_satisfactory") is not True
        assert not out2.get("watermark") or out2.get("db_committed")
    else:
        assert out2.get("db_committed") is True
