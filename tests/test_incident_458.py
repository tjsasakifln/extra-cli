"""Regression suite for production incident #458."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from scripts import health_check
from scripts.crawl.contracts_crawler import FetchResult, FetchStatus
from scripts.crawl.resilience.persistence import resilience_evidence_state
from scripts.crawl.run_contracts_90d_pilot import (
    _fetch_page_with_retry,
    classify_incident_error_text,
    closed_crawl_range,
)


def _result(status: FetchStatus, *, page: int = 1) -> FetchResult:
    return FetchResult(status=status, current_page=page, error_message=status.value)


def test_errors_2_replay_keeps_both_upstream_contract_failures() -> None:
    fixture = Path("tests/fixtures/pncp_incident_458/errors-2.sanitized.json")
    captured = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(captured["errors"]) == 2
    for item in captured["errors"]:
        actual = classify_incident_error_text(item["message"])
        assert actual["class"] == item["class"]
        assert actual["transience"] == item["transience"]
        assert actual["owner"] == item["owner"]


def test_incremental_range_has_exact_closed_days() -> None:
    start, inclusive_end, exclusive_end = closed_crawl_range(date(2026, 8, 22), 7)
    assert start == date(2026, 8, 15)
    assert inclusive_end == date(2026, 8, 21)
    assert exclusive_end == date(2026, 8, 22)
    assert (inclusive_end - start).days + 1 == 7


def test_sealed_artifact_cannot_claim_open_current_day(monkeypatch, tmp_path) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    monkeypatch.setattr(pilot, "utc_today", lambda: date(2026, 8, 23))
    report = pilot.seal_pilot_artifact(
        days=1,
        checkpoint_dir=str(tmp_path / "checkpoint"),
        output_json=str(tmp_path / "sealed.json"),
        run_id="incident-458-seal",
        windows_detail=[],
    )
    assert report["range_start"] == "2026-08-22"
    assert report["range_end"] == "2026-08-22"
    assert report["window_boundary"] == "closed_through_d_minus_1"


def test_incremental_fetch_uses_update_endpoint(monkeypatch) -> None:
    from scripts.crawl import contracts_crawler

    seen: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"data": [], "totalRegistros": 0, "totalPaginas": 0}'

    def fake_open(request, **_kwargs):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    result = contracts_crawler._fetch_page(
        "20260815",
        "20260821",
        1,
        query_kind="update",
        max_retries=0,
    )
    assert result.status == FetchStatus.SUCCESS_ZERO
    assert "/contratos/atualizacao?" in seen[0]


def test_retry_is_bounded_with_backoff_jitter_and_telemetry(monkeypatch) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    outcomes = [
        _result(FetchStatus.HTTP_SERVER_ERROR),
        _result(FetchStatus.HTTP_RATE_LIMIT),
        _result(FetchStatus.SUCCESS_DATA),
    ]
    monkeypatch.setattr(pilot, "_fetch_page", lambda *_a, **_k: outcomes.pop(0))
    sleeps: list[float] = []
    telemetry: list[dict] = []
    result = _fetch_page_with_retry(
        "20260815",
        "20260821",
        1,
        max_retries=2,
        telemetry=telemetry,
        sleeper=sleeps.append,
        jitter=lambda _a, b: b / 2,
    )
    assert result.status == FetchStatus.SUCCESS_DATA
    assert sleeps == [1.5, 3.0]
    assert [row["attempt"] for row in telemetry] == [1, 2, 3]
    assert telemetry[0]["classification"]["class"] == "transient"


def test_permanent_page_failure_is_not_retried(monkeypatch) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    calls: list[int] = []
    monkeypatch.setattr(
        pilot,
        "_fetch_page",
        lambda *_a, **_k: calls.append(1) or _result(FetchStatus.HTTP_CLIENT_ERROR),
    )
    telemetry: list[dict] = []
    result = _fetch_page_with_retry("20260815", "20260821", 4, telemetry=telemetry)
    assert result.status == FetchStatus.HTTP_CLIENT_ERROR
    assert len(calls) == 1
    assert telemetry[0]["classification"]["class"] == "permanent"


def test_success_without_canonical_rows_is_partial_not_zero() -> None:
    assert resilience_evidence_state("success", persisted=0) == "partial"
    assert resilience_evidence_state("empty_confirmed", persisted=0) == "success_zero"
    assert resilience_evidence_state("success", persisted=2) == "success_with_data"


@pytest.mark.database
@pytest.mark.integration
@pytest.mark.real_db
def test_real_db_evidence_distinguishes_partial_from_proven_zero() -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("LOCAL_DATALAKE_DSN/DATABASE_URL not configured")

    import psycopg2

    from scripts.crawl.resilience.persistence import PostgresPersistence

    conn = psycopg2.connect(dsn)
    backend = PostgresPersistence(dsn=dsn)
    try:
        common = {
            "source": "pncp-incident-458-test",
            "pages_fetched": 1,
            "pages_expected": 1,
            "provenance": {"fixture": "incident-458"},
            "date_from": "2026-08-21",
            "date_to": "2026-08-21",
            "satisfactory": True,
        }
        backend._project_resilience_evidence(
            conn,
            run_id="incident-458-partial",
            request_scope="date=2026-08-21",
            fetch_status="success",
            fetched=1,
            persisted=0,
            **common,
        )
        backend._project_resilience_evidence(
            conn,
            run_id="incident-458-proven-zero",
            request_scope="date=2026-08-20",
            fetch_status="empty_confirmed",
            fetched=0,
            persisted=0,
            **common,
        )
        with conn.cursor() as cur:
            cur.execute(
                """SELECT run_id, state, request_scope, pages_fetched, satisfactory
                   FROM coverage_evidence
                   WHERE source = 'pncp-incident-458-test'
                   ORDER BY run_id"""
            )
            rows = cur.fetchall()
        assert rows == [
            ("incident-458-partial", "partial", "date=2026-08-21", 1, False),
            ("incident-458-proven-zero", "success_zero", "date=2026-08-20", 1, True),
        ]
    finally:
        conn.rollback()
        conn.close()


def test_interruption_restart_replays_committed_page_idempotently(monkeypatch, tmp_path) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    monkeypatch.setattr(pilot, "CONTRACTS_REQUEST_DELAY", 0)
    monkeypatch.setattr(pilot, "CONTRACTS_JANELA_DELAY", 0)
    monkeypatch.setattr(pilot, "UPSERT_BATCH", 1)
    monkeypatch.setattr(pilot, "transform", lambda rows: rows)

    def interrupted(_start, _end, page, **_kwargs):
        if page == 1:
            return FetchResult(
                status=FetchStatus.SUCCESS_DATA,
                items=[{"numeroControlePNCP": "page-1"}],
                total_records=2,
                total_pages=2,
                current_page=1,
            )
        raise KeyboardInterrupt("fixture interruption")

    monkeypatch.setattr(pilot, "_fetch_page", interrupted)
    try:
        pilot.run_pilot(
            "",
            days=1,
            dry_run=True,
            checkpoint_dir=str(tmp_path),
            run_id="incident-458-interrupted",
            logical_job_id="pncp-contracts-incremental",
            campaign_id="historical_contracts_incremental",
        )
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - fixture must interrupt
        raise AssertionError("fixture did not interrupt")

    checkpoint = json.loads((tmp_path / "contracts_full.json").read_text(encoding="utf-8"))
    progress = checkpoint["meta"]["in_progress_window"]
    assert progress["last_page_committed"] == 1
    assert progress["restart_from_page"] == 1

    def resumed(_start, _end, page, **_kwargs):
        return FetchResult(
            status=FetchStatus.SUCCESS_DATA,
            items=[{"numeroControlePNCP": f"page-{page}"}],
            total_records=2,
            total_pages=2,
            current_page=page,
        )

    monkeypatch.setattr(pilot, "_fetch_page", resumed)
    report = pilot.run_pilot(
        "",
        days=1,
        dry_run=True,
        checkpoint_dir=str(tmp_path),
        run_id="incident-458-resumed",
        logical_job_id="pncp-contracts-incremental",
        campaign_id="historical_contracts_incremental",
    )
    assert report["status"] == "success"
    assert report["totals"]["pages_reprocessed"] == 1
    assert report["windows"][0]["resume_policy"] == "replay_from_page_1_unstable_upstream_order"


def test_live_window_artifact_reconciles_inserted_and_skipped(monkeypatch, tmp_path) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    class FakeCursor:
        def __init__(self) -> None:
            self.query = ""

        def execute(self, query, _params=None) -> None:
            self.query = " ".join(str(query).split())

        def fetchone(self):
            if "information_schema.columns" in self.query:
                return {"exists": 1}
            if "MIN(data_assinatura)" in self.query:
                return {"min_a": date(2026, 8, 22), "max_a": date(2026, 8, 22)}
            if "n_sample" in self.query:
                return {"n_sample": 20}
            return {
                "n": 2,
                "min_pub": date(2026, 8, 22),
                "max_pub": date(2026, 8, 22),
            }

        def fetchall(self):
            return [{"mes": date(2026, 8, 1), "n": 2}]

        def close(self) -> None:
            return None

    class FakeConnection:
        autocommit = False

        def cursor(self, **_kwargs):
            return FakeCursor()

        def close(self) -> None:
            return None

    monkeypatch.setattr(pilot, "utc_today", lambda: date(2026, 8, 23))
    monkeypatch.setattr(pilot, "CONTRACTS_REQUEST_DELAY", 0)
    monkeypatch.setattr(pilot, "CONTRACTS_JANELA_DELAY", 0)
    monkeypatch.setattr(pilot, "UPSERT_BATCH", 2)
    monkeypatch.setattr(pilot, "transform", lambda rows: rows)
    monkeypatch.setattr(pilot.psycopg2, "connect", lambda _dsn: FakeConnection())
    monkeypatch.setattr(pilot, "_upsert_batch", lambda _conn, _rows: (1, 1))
    monkeypatch.setattr(
        pilot,
        "_fetch_page",
        lambda *_a, **_k: FetchResult(
            status=FetchStatus.SUCCESS_DATA,
            items=[
                {"numeroControlePNCP": "inserted"},
                {"numeroControlePNCP": "skipped"},
            ],
            total_records=2,
            total_pages=1,
            current_page=1,
        ),
    )

    report = pilot.run_pilot(
        "postgresql://sanitized",
        days=1,
        checkpoint_dir=str(tmp_path / "checkpoint"),
        output_json=str(tmp_path / "artifact.json"),
        run_id="incident-458-live-reconcile",
        query_kind="update",
    )
    drift = report["windows"][0]["population_drift"]
    assert report["status"] == "success"
    assert report["totals"]["inserted"] == 1
    assert report["totals"]["skipped"] == 1
    assert drift["fetched"] == 2
    assert drift["persisted"] == 2
    assert drift["counts_reconciled"] is True
    assert drift["ok"] is True
    assert drift["decision"] == "accept"

    monkeypatch.setattr(pilot, "_upsert_batch", lambda _conn, _rows: (1, 0))
    inconsistent = pilot.run_pilot(
        "postgresql://sanitized",
        days=1,
        checkpoint_dir=str(tmp_path / "inconsistent-checkpoint"),
        output_json=str(tmp_path / "inconsistent-artifact.json"),
        run_id="incident-458-live-inconsistent",
        query_kind="update",
    )
    bad_window = inconsistent["windows"][0]
    assert inconsistent["status"] == "partial"
    assert bad_window["population_drift"]["ok"] is False
    assert any("local_persistence_reconciliation" in error for error in bad_window["errors"])
    assert bad_window["failure_classifications"][0]["class"] == "local_corruption"


def test_nonempty_page_with_zero_transforms_is_local_failure(monkeypatch, tmp_path) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    monkeypatch.setattr(pilot, "CONTRACTS_REQUEST_DELAY", 0)
    monkeypatch.setattr(pilot, "CONTRACTS_JANELA_DELAY", 0)
    monkeypatch.setattr(pilot, "transform", lambda _rows: [])
    monkeypatch.setattr(
        pilot,
        "_fetch_page",
        lambda *_a, **_k: FetchResult(
            status=FetchStatus.SUCCESS_DATA,
            items=[{"numeroControlePNCP": "raw-but-invalid"}],
            total_records=1,
            total_pages=1,
            current_page=1,
        ),
    )
    report = pilot.run_pilot(
        "",
        days=1,
        dry_run=True,
        checkpoint_dir=str(tmp_path),
        run_id="incident-458-transform-corruption",
    )
    assert report["status"] == "failed"
    assert report["totals"]["windows_failed"] == 1
    assert report["windows"][0]["failure_classifications"][0]["class"] == "local_corruption"


def test_tail_reconciliation_failure_is_not_suppressed(monkeypatch, tmp_path) -> None:
    from scripts.crawl import run_contracts_90d_pilot as pilot

    monkeypatch.setattr(pilot, "CONTRACTS_REQUEST_DELAY", 0)
    monkeypatch.setattr(pilot, "CONTRACTS_JANELA_DELAY", 0)
    monkeypatch.setattr(pilot, "UPSERT_BATCH", 1)
    monkeypatch.setattr(pilot, "transform", lambda rows: rows)
    calls = 0

    def fetch(_start, _end, page, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return FetchResult(
                status=FetchStatus.SUCCESS_DATA,
                items=[{"numeroControlePNCP": "page-1"}],
                total_records=100,
                total_pages=2,
                current_page=page,
            )
        if calls == 2:
            return FetchResult(
                status=FetchStatus.SUCCESS_DATA,
                items=[{"numeroControlePNCP": "page-2"}],
                total_records=101,
                total_pages=2,
                current_page=page,
            )
        return _result(FetchStatus.HTTP_CLIENT_ERROR, page=page)

    monkeypatch.setattr(pilot, "_fetch_page", fetch)
    report = pilot.run_pilot(
        "",
        days=1,
        dry_run=True,
        checkpoint_dir=str(tmp_path),
        run_id="incident-458-tail-failure",
    )
    window = report["windows"][0]
    assert report["status"] == "partial"
    assert report["totals"]["page_errors"] == 1
    assert window["status"] == "partial"
    assert any("Tail page" in error for error in window["errors"])
    assert any(
        item["class"] == "permanent" and "Tail page" in item["error"]
        for item in window["failure_classifications"]
    )


def test_health_bundle_runs_freshness_after_infrastructure_failure(monkeypatch, tmp_path) -> None:
    from scripts.ops import health_bundle, pncp_contract_freshness

    calls: list[str] = []
    monkeypatch.setattr(
        sys.modules["scripts.health_check"],
        "main",
        lambda: calls.append("infrastructure") or 2,
    )
    monkeypatch.setattr(
        pncp_contract_freshness,
        "main",
        lambda _argv: calls.append("freshness") or 1,
    )
    report = health_bundle.run_bundle(freshness_output=tmp_path / "freshness.json")
    assert calls == ["infrastructure", "freshness"]
    assert report["status"] == "UNHEALTHY"
    assert report["exit_code"] == 2


def test_coverage_bundle_writes_snapshot_after_diagnostic_failure() -> None:
    from scripts.ops import coverage_bundle

    commands: list[list[str]] = []

    def fake_runner(command):
        commands.append(list(command))
        return 1 if len(commands) == 1 else 0

    report = coverage_bundle.run_bundle(runner=fake_runner)

    assert [item["name"] for item in report["checks"]] == [
        "coverage_diagnostic",
        "coverage_snapshot_export",
    ]
    assert [item["exit_code"] for item in report["checks"]] == [1, 0]
    assert report["status"] == "UNHEALTHY"
    assert report["exit_code"] == 1
    assert "--report-coverage" in commands[0]
    assert "--snapshot" in commands[1]
    assert "--export" in commands[1]


def test_failed_live_alert_channel_falls_back_to_durable_ledger(monkeypatch, tmp_path) -> None:
    from scripts import notify
    from scripts.ops.alert_pipeline import AlertEvent, dispatch_alert

    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://sanitized.invalid/hook")
    monkeypatch.setattr(
        notify,
        "dispatch",
        lambda _title, _body: [
            {"channel": "webhook", "success": False, "message": "HTTP 404"}
        ],
    )
    ledger = tmp_path / "alerts.jsonl"
    result = dispatch_alert(
        AlertEvent(
            title="PNCP stale",
            body="freshness exceeded",
            severity="critical",
            next_action="inspect checkpoint",
        ),
        dry_run=False,
        ledger_path=ledger,
        state_path=tmp_path / "state.json",
    )
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert result["durable"] is True
    assert result["fallback_ledger"] == str(ledger)
    fallback = [row for row in records if row["event"] == "fallback_persist"]
    assert fallback and "next_action" in fallback[-1]["body"]


def test_onfailure_alert_is_durable_before_broken_webhook(tmp_path) -> None:
    from scripts.ops.onfailure_alert import record_service_failure

    def broken_webhook(_request, **_kwargs):
        raise urllib.error.HTTPError(
            "https://sanitized.invalid/hook",
            404,
            "Not Found",
            hdrs=None,
            fp=None,
        )

    ledger = tmp_path / "onfailure.jsonl"
    result = record_service_failure(
        service="pncp-contracts.service",
        host="sanitized-host",
        ledger=ledger,
        webhook_url="https://sanitized.invalid/hook",
        opener=broken_webhook,
    )
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert result["durable"] is True
    assert result["delivered"] is False
    assert [row["event"] for row in rows] == ["service_failed", "delivery_failed"]
    assert rows[0]["service"] == "pncp-contracts.service"
    assert "sanitized.invalid" not in ledger.read_text(encoding="utf-8")


def test_dual_health_requires_denominator_zero_and_as_of() -> None:
    cap = {
        "as_of": "2026-08-22T00:00:00Z",
        "applicable_denominator": 100,
        "covered_numerator": 95,
        "success_zero_count": 5,
        "coverage_pct": 0.95,
    }
    valid = {
        "dual_gate_status": "PASS",
        "pipeline_success": True,
        "scope_complete": True,
        "as_of": "2026-08-22T00:00:00Z",
        "capabilities": {"open_tenders": dict(cap), "historical_contracts": dict(cap)},
    }
    assert health_check.validate_dual_coverage_summary(valid)[0] is True
    del valid["capabilities"]["historical_contracts"]["applicable_denominator"]
    ok, reason = health_check.validate_dual_coverage_summary(valid)
    assert ok is False
    assert "applicable_denominator" in reason


def test_migration_accepts_persistence_failure_class() -> None:
    sql = Path("db/migrations/100_crawl_failure_persist_class.sql").read_text(encoding="utf-8")
    assert "PERSIST_FAILURE" in sql


def test_systemd_units_use_bundle_venv_and_service_mode() -> None:
    health = Path("deploy/systemd/extra-health-check.service").read_text(encoding="utf-8")
    coverage = Path("deploy/systemd/coverage-report.service").read_text(encoding="utf-8")
    alerts = Path("deploy/systemd/extra-check-alerts.service").read_text(encoding="utf-8")
    onfailure = Path("deploy/systemd/extra-onfailure@.service").read_text(encoding="utf-8")
    assert "scripts.ops.health_bundle" in health
    assert health.count("ExecStart=") == 1
    assert "scripts.ops.coverage_bundle" in coverage
    assert "ExecStartPre=" not in coverage
    assert "OnFailure=extra-onfailure@%n.service" in coverage
    assert "--service-mode" in alerts
    assert "/var/lib/extra-consultoria/alerts/alert_ledger.jsonl" in alerts
    assert "/var/lib/extra-consultoria/alerts/onfailure.jsonl" in onfailure
    assert "StateDirectory=extra-consultoria/alerts" in onfailure
    assert "StateDirectoryMode=0750" in onfailure
    assert "/opt/extra-consultoria/.venv/bin/python" in onfailure
    assert "scripts/ops/onfailure_alert.py" in onfailure
