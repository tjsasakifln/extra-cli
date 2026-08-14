"""Tests for per-entity PNCP contracts backfill (#249)."""

from __future__ import annotations

from scripts.crawl.pncp_contracts_backfill import (
    VALUE_KINDS,
    WindowJob,
    buyer_intel_rows,
    classify_value,
    ingest_window,
    job_report,
    record_page,
    zero_proof,
)


def _page(n: int, status: int = 200) -> object:
    return record_page(
        page=n,
        url=f"https://pncp.gov.br/api/consulta/v1/contratos?pagina={n}",
        status=status,
        body=f"p{n}".encode(),
        records=1,
    )


def _row(contract_id: str, kind: str, amount: float, page: int = 1) -> dict:
    return {
        "contract_id": contract_id,
        "value_kind": kind,
        "amount": amount,
        "page": page,
        "raw_uri": f"cas://pncp-contracts/{contract_id}",
        "sha256": "a" * 64,
    }


def test_window_ends_complete_or_failed_with_checkpoint_after_persist() -> None:
    job = WindowJob(ente_id="e1", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(
        job,
        pages=[_page(1)],
        rows=[_row("c1", "contratado", 1000.0)],
        query_complete=True,
        persist_ok=True,
    )
    assert job.status == "complete"
    assert job.checkpoint_after_persist is True
    failed = WindowJob(ente_id="e1", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(failed, pages=[_page(1, status=429)], rows=[], query_complete=False, persist_ok=False)
    assert failed.status == "failed"
    assert failed.error == "retryable_http"
    assert failed.checkpoint_after_persist is False


def test_pagination_raw_hash_and_counts_reconcile() -> None:
    page = _page(1)
    assert page.raw_uri.startswith("cas://")
    assert len(page.sha256) == 64
    job = WindowJob(ente_id="e2", window_start="2025-01-01", window_end="2025-03-31")
    ingest_window(
        job,
        pages=[page],
        rows=[
            _row("ok", "estimado", 10.0),
            {"contract_id": "bad", "value_kind": "foo", "amount": 1, "raw_uri": "x", "sha256": "y"},
        ],
        query_complete=True,
        persist_ok=True,
    )
    assert job.fetched == 2
    assert len(job.persisted) == 1
    assert len(job.rejected) == 1
    assert job.balanced
    assert job.rejected[0]["reason"] == "unknown_value_kind"


def test_value_kinds_are_distinct() -> None:
    assert set(VALUE_KINDS) == {"estimado", "homologado", "contratado", "pago"}
    assert classify_value("Homologado", "15.5") == ("homologado", 15.5)
    assert classify_value("pago", -1) == "negative_amount"


def test_zero_proof_and_freshness_require_complete_window() -> None:
    empty = WindowJob(ente_id="e3", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(empty, pages=[_page(1)], rows=[], query_complete=True, persist_ok=True)
    assert zero_proof(empty)["verdict"] == "ZERO_CONFIRMED"
    incomplete = WindowJob(ente_id="e3", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(incomplete, pages=[], rows=[], query_complete=False, persist_ok=True)
    assert zero_proof(incomplete)["verdict"] == "SCOPE_INCOMPLETE"


def test_buyer_intel_uses_only_rows_with_provenance() -> None:
    job = WindowJob(ente_id="e4", window_start="2025-01-01", window_end="2025-12-31")
    ingest_window(
        job,
        pages=[_page(1)],
        rows=[
            _row("with", "pago", 50.0),
            {"contract_id": "nope", "value_kind": "pago", "amount": 1, "raw_uri": "", "sha256": ""},
        ],
        query_complete=True,
        persist_ok=True,
    )
    intel = buyer_intel_rows([job])
    assert [item.contract_id for item in intel] == ["with"]
    assert intel[0].provenance["source"] == "pncp_contratos"
    report = job_report(job)
    assert report["status"] == "complete"
    assert report["policy_window_start"] == "2025-01-01"


def test_replay_same_window_is_idempotent_and_never_checkpoints_before_persist() -> None:
    job = WindowJob(ente_id="e5", window_start="2025-01-01", window_end="2025-01-31")
    rows = [_row("c-replay", "contratado", 99.0)]
    ingest_window(job, pages=[_page(1)], rows=rows, query_complete=True, persist_ok=True)
    ingest_window(job, pages=[_page(1)], rows=rows, query_complete=True, persist_ok=True)
    assert job.status == "complete"
    assert len(job.persisted) == 1
    assert job.balanced
    blocked = WindowJob(ente_id="e5", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(blocked, pages=[_page(1)], rows=rows, query_complete=True, persist_ok=False)
    assert blocked.status == "failed"
    assert blocked.checkpoint_after_persist is False
    assert blocked.persisted == []
