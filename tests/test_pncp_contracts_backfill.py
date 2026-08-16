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


def test_zero_proof_does_not_confirm_zero_when_all_rows_rejected() -> None:
    job = WindowJob(ente_id="e3b", window_start="2025-01-01", window_end="2025-01-31")
    ingest_window(
        job,
        pages=[_page(1)],
        rows=[
            {"contract_id": "bad", "value_kind": "foo", "amount": 1, "raw_uri": "x", "sha256": "y"},
            {"contract_id": "nope", "value_kind": "pago", "amount": 1, "raw_uri": "", "sha256": ""},
        ],
        query_complete=True,
        persist_ok=True,
    )
    assert job.status == "complete"
    assert job.fetched == 2
    assert job.persisted == []
    assert len(job.rejected) == 2
    proof = zero_proof(job)
    assert proof["verdict"] == "REJECTED_ALL"
    assert proof["verdict"] != "ZERO_CONFIRMED"
    assert proof["fetched"] == 2
    assert proof["rejected"] == 2


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


def test_pinned_national_windows_and_resume_skip() -> None:
    from datetime import date

    from scripts.crawl.pncp_contracts_backfill import WINDOW_START
    from scripts.crawl.run_contracts_90d_pilot import (
        evaluate_window_completion,
        planned_window_keys,
        resolve_pilot_range,
        resume_action_for_window,
    )

    start, end = resolve_pilot_range(
        days=591,
        start_date=date.fromisoformat(WINDOW_START),
        end_date=date(2026, 8, 15),
    )
    keys = planned_window_keys(start, end)
    assert start.isoformat() == "2025-01-01"
    assert keys[0] == "20250101_20250130"
    assert keys[-1] == "20260725_20260815"
    assert len(keys) == 20
    drifted = planned_window_keys(date(2025, 1, 2), date(2026, 8, 16))
    assert drifted[0] != keys[0]
    completed = [keys[0], keys[1]]
    assert resume_action_for_window(keys[0], completed) == "skip"
    assert resume_action_for_window(keys[2], completed) == "fetch"
    ok, errors = evaluate_window_completion(
        ["upsert failed"],
        pages_exhausted=False,
        last_total_pages=100,
        page=19,
        max_pages=500,
    )
    assert ok is False
    assert errors
    partial_ok, _ = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=10,
        page=10,
        max_pages=500,
    )
    assert partial_ok is True


def test_report_classifies_residual_and_keeps_unknown() -> None:
    from datetime import date

    from scripts.crawl.pncp_contracts_backfill import WINDOW_START
    from scripts.ops.report_national_backfill import (
        build_national_backfill_report,
        reconcile_window_counts,
    )

    start = date.fromisoformat(WINDOW_START)
    end = date(2026, 8, 15)
    report = build_national_backfill_report(
        {
            "completed_windows": ["20250101_20250130"],
            "failed_windows": ["20251127_20251226"],
            "blocked_windows": [],
            "window_results": {
                "20250101_20250130": {
                    "terminal": "COMPLETE",
                    "fetched": 10,
                    "persisted": 2,
                    "rejected": 0,
                    "skipped": 8,
                },
                "20251127_20251226": {
                    "terminal": "FAILED",
                    "fetched": 5,
                    "persisted": 1,
                    "rejected": 1,
                    "skipped": 3,
                },
            },
            "meta": {"run_id": "contracts-90d-fixture"},
        },
        start=start,
        end=end,
        origin_main_sha="aaa",
        host_sha="bbb",
    )
    by_key = {w["window_key"]: w for w in report["windows"]}
    assert by_key["20250101_20250130"]["terminal"] == "complete"
    assert by_key["20250101_20250130"]["resume"] == "skip"
    assert by_key["20251127_20251226"]["terminal"] == "failed"
    assert by_key["20251127_20251226"]["resume"] == "retry"
    open_key = "20250131_20250301"
    assert by_key[open_key]["terminal"] == "open"
    assert by_key[open_key]["reconciliation"]["identity"] == "UNKNOWN"
    assert by_key[open_key]["reconciliation"]["fetched"] is None
    assert report["counts"]["complete"] == 1
    assert report["counts"]["failed"] == 1
    assert report["counts"]["retry"] >= 1
    assert report["claims"]["VPS_OPERATIONAL"] is False
    assert report["pin"]["window_start"] == WINDOW_START
    missing = reconcile_window_counts(None, None, None)
    assert missing["identity"] == "UNKNOWN"
    assert missing["balanced"] is None
    assert reconcile_window_counts(10, 2, 0, 8)["balanced"] is True
    assert reconcile_window_counts(10, 2, 0)["balanced"] is False


def test_campaign_terminal_blocked_names_guc_windows_and_drift() -> None:
    from datetime import date

    from scripts.crawl.pncp_contracts_backfill import WINDOW_START
    from scripts.ops.report_national_backfill import (
        ALLOWED_TERMINALS,
        TERMINAL_BLOCKED,
        TERMINAL_COMPLETE,
        build_national_backfill_report,
        classify_campaign_terminal,
    )

    start = date.fromisoformat(WINDOW_START)
    end = date(2026, 8, 15)
    failed = [
        "20251127_20251226",
        "20251227_20260125",
        "20260126_20260224",
        "20260225_20260326",
        "20260327_20260425",
        "20260426_20260525",
        "20260526_20260624",
    ]
    completed = [
        "20250101_20250130",
        "20250131_20250301",
        "20250302_20250331",
        "20250401_20250430",
        "20250501_20250530",
        "20250531_20250629",
        "20250630_20250729",
        "20250730_20250828",
        "20250829_20250927",
        "20250928_20251027",
        "20251028_20251126",
        "20260625_20260724",
        "20260725_20260815",
    ]
    report = build_national_backfill_report(
        {
            "completed_windows": completed,
            "failed_windows": failed,
            "blocked_windows": ["20260725_20260816"],
            "current_window": "20260725_20260816",
            "window_results": {
                "20260725_20260816": {
                    "terminal": "BLOCKED",
                    "fetched": 80500,
                    "persisted": 0,
                    "rejected": 284,
                    "skipped": 80216,
                }
            },
            "meta": {"run_id": "contracts-90d-live-shape"},
        },
        start=start,
        end=end,
        origin_main_sha="820c83b8",
        host_sha="bbc4b6b7",
        incremental_only=False,
        default_blocker="max_locks_per_transaction",
    )
    state = report["campaign_state"]
    assert state["terminal"] == TERMINAL_BLOCKED
    assert state["terminal"] in ALLOWED_TERMINALS
    assert state["blocker"] == "max_locks_per_transaction"
    named = [w["window_key"] for w in state["windows"]]
    assert named[:7] == failed
    assert "20260725_20260816" in named
    drift = next(w for w in state["windows"] if w["window_key"] == "20260725_20260816")
    assert drift["in_pin"] is False
    assert drift["terminal"] == "blocked"
    assert report["claims"]["campaign_terminal"] is False
    assert report["claims"]["VPS_OPERATIONAL"] is False
    assert report["counts"]["planned"] == 20
    assert report["counts"]["complete"] == 13
    assert report["counts"]["failed"] == 7

    complete_report = {
        "counts": {"planned": 20, "complete": 20},
        "residual": [],
    }
    done = classify_campaign_terminal(complete_report, incremental_only=True)
    assert done["terminal"] == TERMINAL_COMPLETE
    assert done["windows"] == []
    not_only = classify_campaign_terminal(complete_report, incremental_only=False)
    assert not_only["terminal"] == TERMINAL_BLOCKED
    assert not_only["blocker"] == "incremental_not_only_writer"
    unknown = classify_campaign_terminal(
        {"counts": {"planned": 20, "complete": 19}, "residual": [{"window_key": "x", "terminal": "failed"}]},
    )
    assert unknown["blocker"] == "UNKNOWN"
    assert unknown["windows"][0]["blocker"] == "UNKNOWN"
