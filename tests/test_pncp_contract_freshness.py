"""Focused tests for PNCP_CONTRACT_FRESHNESS/1.0 — drive shipped producers only."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.crawl.pncp_contract import PNCP_TAMANHO_PAGINA_MIN
from scripts.crawl.pncp_entity_pagination import expected_pages
from scripts.ops.pncp_contract_freshness import (
    CONTRACT_VERSION,
    DESIRED_HARD_GUARDRAIL_HOURS,
    DESIRED_OPERATIONAL_TARGET_HOURS,
    LOCK_BUSY_EXIT,
    REASON_BACKUP_UNAVAILABLE,
    REASON_CADENCE_CANNOT_MEET_6H,
    REASON_CADENCE_CANNOT_MEET_24H,
    REASON_CHECKPOINT_CONFLICT,
    REASON_CHECKPOINT_IN_WORKTREE,
    REASON_DB_UNAVAILABLE,
    REASON_DUPLICATE_REPLAY,
    REASON_EXTERNAL_TRANSIENT,
    REASON_HTTP_200_NOT_PROOF,
    REASON_ILLEGAL_PAGE_SIZE,
    REASON_LAG_ABOVE_HARD_GUARDRAIL,
    REASON_LAG_ABOVE_OPERATIONAL_TARGET,
    REASON_LATE_ARRIVAL,
    REASON_LOCK_BUSY_NO_CLOSE,
    REASON_MISSED_TIMER,
    REASON_MISSING_EVIDENCE,
    REASON_MISSING_SOURCE_TIMESTAMP,
    REASON_PAGINATION_INCOMPLETE,
    REASON_REBOOT_CATCHUP_REQUIRED,
    REASON_RESTORE_MISMATCH,
    REASON_RETIFICACAO,
    REASON_SCHEMA_DRIFT,
    REASON_SINGLE_ROW_NOT_PROOF,
    REASON_STALE_CHECKPOINT,
    REASON_TIMER_ACTIVE_NOT_PROOF,
    REASON_TIMER_DELAYED,
    REASON_WINDOW_EMPTY_COMPLETE,
    REASON_WINDOW_EMPTY_INCOMPLETE,
    REASON_WINDOW_INCOMPLETE,
    STATUSES,
    TIMER_UNIT_PATH,
    build_contract,
    cadence_from_unit_text,
    classify_backup,
    classify_ingest_http,
    classify_late_arrival,
    classify_replay,
    classify_retificacao,
    classify_schema,
    classify_status,
    collect_backup_snapshot,
    collect_checkpoint_snapshot,
    collect_db_snapshot,
    collect_snapshot,
    collect_timer_snapshot,
    empty_window_reason,
    health_exit,
    lag_percentiles,
    last_successful_close_at,
    legal_page_size,
    load_shipped_cadence,
    load_shipped_service_text,
    main,
    parse_dt,
    parse_oncalendar_spec,
    parse_success_exit_statuses,
    resolve_effective_cadence,
    resume_units,
)
from scripts.ops.source_contract_tests import classify_http_outcome

NOW = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)


def _closed_window(**overrides: object) -> dict:
    base = {
        "window_key": "20260812_20260819",
        "status": "completed",
        "source_window": {"start": "2026-08-12", "end": "2026-08-19"},
        "pages_expected": 92,
        "pages_fetched": 92,
        "expected": 45703,
        "fetched": 45703,
        "persisted": 18495,
        "deduplicated": 27208,
        "failed": 0,
        "closed_at": "2026-08-19T09:21:14Z",
        "run_id": "contracts-90d-20260819T090020Z-2d53827e9d",
    }
    base.update(overrides)
    return base


def _snapshot(**overrides: object) -> dict:
    base: dict = {
        "as_of": NOW.isoformat().replace("+00:00", "Z"),
        "live": True,
        "has_evidence": True,
        "deployed_sha": "9c5e7d47f99902d9d97cf479aefbba8cd391a14d",
        "run_id": "contracts-90d-20260819T090020Z-2d53827e9d",
        "attempt_id": "contracts-90d-20260819T090020Z-2d53827e9d",
        "source_publication_or_update_at": "2026-08-19T00:00:47Z",
        "first_observed_at": "2026-08-19T09:21:09Z",
        "persisted_at": "2026-08-19T09:21:09Z",
        "windows": [_closed_window()],
        "checkpoint": {
            "path": "/var/lib/extra-consultoria/checkpoints/contracts/contracts_full.json",
            "in_worktree": False,
            "sha256": "abc123",
            "completed_windows": ["20260807_20260814", "20260812_20260819"],
            "blocked_windows": ["20260810_20260817"],
            "failed_windows": [],
            "logical_job_id": "pncp-contracts-incremental",
            "attempt_run_id": "contracts-90d-20260819T090020Z-2d53827e9d",
            "updated_at": "2026-08-19T09:21:14Z",
            "before": {"completed_windows": ["20260807_20260814"]},
            "after": {"completed_windows": ["20260807_20260814", "20260812_20260819"]},
        },
        "timer": {
            "unit": "pncp-contracts.timer",
            "active": True,
            "enabled": True,
            "last_run_at": "2026-08-19T09:00:20Z",
            "next_run_at": "2026-08-21T09:00:00Z",
            "last_result": "success",
            "last_exec_status": 0,
        },
        "db": {
            "available": True,
            "columns": list(
                {
                    "contrato_id",
                    "ingested_at",
                    "data_publicacao_fonte",
                    "data_atualizacao_fonte",
                    "first_seen_at",
                }
            ),
            "latest_ingested_at": "2026-08-19T09:21:09Z",
            "latest_source_publication_or_update_at": "2026-08-19T00:00:47Z",
        },
        "lags_hours": [9.34, 8.85, 8.85, 8.85, 8.85],
        "evidence_only": {"timer_active": False, "http_200": False, "single_recent_row": False},
    }
    base.update(overrides)
    return base


def test_missing_evidence_is_unknown_not_fresh() -> None:
    status, reasons = classify_status(has_evidence=False, current_lag_hours=None)
    assert status == "UNKNOWN"
    assert REASON_MISSING_EVIDENCE in reasons
    artifact = build_contract(
        {"has_evidence": False, "as_of": NOW.isoformat(), "evidence_only": {"timer_active": True}}
    )
    assert artifact["status"] == "UNKNOWN"
    assert artifact["status"] != "FRESH"
    assert REASON_TIMER_ACTIVE_NOT_PROOF in artifact["reason_codes"]


def test_timer_http_single_row_never_fresh() -> None:
    timer = build_contract(
        {
            "as_of": NOW.isoformat(),
            "has_evidence": False,
            "evidence_only": {"timer_active": True},
            "timer": {"active": True, "last_run_at": NOW.isoformat()},
        }
    )
    http_only = build_contract(
        {
            "as_of": NOW.isoformat(),
            "has_evidence": False,
            "evidence_only": {"http_200": True},
        }
    )
    row_only = build_contract(
        {
            "as_of": NOW.isoformat(),
            "has_evidence": False,
            "evidence_only": {"single_recent_row": True},
            "db": {"available": True, "latest_ingested_at": NOW.isoformat()},
        }
    )
    assert timer["status"] == "UNKNOWN"
    assert REASON_TIMER_ACTIVE_NOT_PROOF in timer["reason_codes"]
    assert http_only["status"] == "UNKNOWN"
    assert REASON_HTTP_200_NOT_PROOF in http_only["reason_codes"]
    assert row_only["status"] == "UNKNOWN"
    assert REASON_SINGLE_ROW_NOT_PROOF in row_only["reason_codes"]
    assert "FRESH" not in {timer["status"], http_only["status"], row_only["status"]}


def test_incomplete_window_is_not_fresh() -> None:
    artifact = build_contract(
        _snapshot(
            windows=[
                _closed_window(window_key="20260801_20260807", closed_at="2026-08-07T09:00:00Z"),
                {
                    "window_key": "20260820_20260821",
                    "status": "failed",
                    "pages_expected": 10,
                    "pages_fetched": 3,
                    "expected": 100,
                    "fetched": 30,
                    "persisted": 0,
                    "failed": 7,
                    "error": "incomplete",
                },
            ],
            checkpoint={
                "completed_windows": ["20260801_20260807"],
                "blocked_windows": [],
                "failed_windows": ["20260820_20260821"],
                "in_worktree": False,
                "updated_at": "2026-08-07T09:00:00Z",
            },
        )
    )
    assert artifact["status"] != "FRESH"
    assert artifact["status"] == "STALE"
    assert (
        REASON_WINDOW_INCOMPLETE in artifact["reason_codes"] or REASON_PAGINATION_INCOMPLETE in artifact["reason_codes"]
    )


def test_lag_above_target_degraded_and_24h_stale() -> None:
    degraded_status, degraded_reasons = classify_status(has_evidence=True, current_lag_hours=7.0)
    stale_status, stale_reasons = classify_status(has_evidence=True, current_lag_hours=29.0)
    assert degraded_status == "DEGRADED"
    assert REASON_LAG_ABOVE_OPERATIONAL_TARGET in degraded_reasons
    assert stale_status == "STALE"
    assert REASON_LAG_ABOVE_HARD_GUARDRAIL in stale_reasons
    live = build_contract(_snapshot())
    assert live["status"] == "STALE"
    assert live["current_lag_hours"] is not None
    assert live["current_lag_hours"] > DESIRED_HARD_GUARDRAIL_HOURS
    assert live["slo"]["sustainable_operational_target"] is True
    assert live["slo"]["sustainable_hard_guardrail"] is True
    assert live["slo"]["timer_max_inter_run_hours"] <= DESIRED_OPERATIONAL_TARGET_HOURS
    assert REASON_CADENCE_CANNOT_MEET_24H not in live["reason_codes"]
    assert live["slo"]["desired_operational_target_hours"] == DESIRED_OPERATIONAL_TARGET_HOURS


def test_unknown_distinct_from_zero_empty_window() -> None:
    complete_zero = empty_window_reason(
        pages_expected=1,
        pages_fetched=1,
        found_count=0,
        query_complete=True,
        page_size=50,
    )
    incomplete_zero = empty_window_reason(
        pages_expected=3,
        pages_fetched=1,
        found_count=0,
        query_complete=False,
        page_size=50,
    )
    unknown, _ = classify_status(has_evidence=False, current_lag_hours=None)
    assert complete_zero == REASON_WINDOW_EMPTY_COMPLETE
    assert incomplete_zero == REASON_WINDOW_EMPTY_INCOMPLETE
    assert unknown == "UNKNOWN"
    assert unknown != complete_zero
    assert complete_zero != "UNKNOWN"


def test_lag_percentiles_deterministic_on_fixture() -> None:
    samples = [float(i) for i in range(1, 101)]
    got = lag_percentiles(samples)
    assert got == {"p50": 50.0, "p95": 95.0, "p99": 99.0, "n": 100}
    empty = lag_percentiles([])
    assert empty == {"p50": None, "p95": None, "p99": None, "n": 0}


def test_legal_page_size_and_expected_pages() -> None:
    assert legal_page_size(PNCP_TAMANHO_PAGINA_MIN) is True
    assert legal_page_size(50) is True
    assert legal_page_size(5) is False
    assert legal_page_size(9) is False
    assert expected_pages(9892, 50) == 198
    assert expected_pages(0, 50) == 1


def test_illegal_page_size_is_internal_never_external_or_zero() -> None:
    reason = classify_ingest_http(status=400, page_size=5, body='{"message":"must be greater than or equal to 10"}')
    assert reason == REASON_ILLEGAL_PAGE_SIZE
    assert reason != REASON_EXTERNAL_TRANSIENT
    live_probe = classify_http_outcome(400, None, requested_page_size=5, body="must be greater than or equal to 10")
    assert live_probe == "INTERNAL_DEFECT"
    empty = empty_window_reason(pages_expected=1, pages_fetched=1, found_count=0, query_complete=True, page_size=5)
    assert empty == REASON_ILLEGAL_PAGE_SIZE


def test_http_429_5xx_timeout_named_reasons() -> None:
    assert classify_ingest_http(status=429, page_size=50) == REASON_EXTERNAL_TRANSIENT
    assert classify_ingest_http(status=503, page_size=50) == REASON_EXTERNAL_TRANSIENT
    assert classify_ingest_http(status=408, page_size=50, kind="timeout") == REASON_EXTERNAL_TRANSIENT
    assert classify_http_outcome(429, "http_429") == "http_429_rate_limited"
    assert classify_http_outcome(503, "http_5xx") == "http_5xx_server_error"


def test_schema_drift_and_db_unavailable() -> None:
    assert classify_schema(["contrato_id", "ingested_at"]) == REASON_SCHEMA_DRIFT
    artifact = build_contract(
        _snapshot(
            db={"available": False, "columns": ["contrato_id"]},
            windows=[_closed_window()],
        )
    )
    assert artifact["status"] == "UNKNOWN"
    assert REASON_DB_UNAVAILABLE in artifact["reason_codes"]
    assert REASON_SCHEMA_DRIFT in artifact["reason_codes"]


def test_duplicate_replay_late_arrival_retificacao() -> None:
    assert classify_replay(inserted=0, skipped=27208, rejected=0) == REASON_DUPLICATE_REPLAY
    late = classify_late_arrival(
        source_at=datetime(2026, 8, 20, 1, tzinfo=UTC),
        window_end=datetime(2026, 8, 19, 9, tzinfo=UTC),
        persisted_at=datetime(2026, 8, 21, 9, tzinfo=UTC),
    )
    assert late == REASON_LATE_ARRIVAL
    ret = classify_retificacao(
        publication_at=datetime(2026, 8, 19, tzinfo=UTC),
        update_at=datetime(2026, 8, 20, tzinfo=UTC),
        first_seen_at=datetime(2026, 8, 19, 9, tzinfo=UTC),
        last_seen_at=datetime(2026, 8, 21, 9, tzinfo=UTC),
    )
    assert ret == REASON_RETIFICACAO


def test_stale_checkpoint_conflict_and_worktree_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "data" / "contracts_checkpoints").mkdir(parents=True)
    durable = tmp_path / "var" / "lib" / "extra-consultoria"
    (durable / "checkpoints" / "contracts").mkdir(parents=True)
    refused = collect_checkpoint_snapshot(
        requested=repo / "data" / "contracts_checkpoints",
        production=True,
        repo_root=repo,
        state_root=durable,
    )
    assert refused["in_worktree"] is True or refused.get("conflict") is True
    conflict = build_contract(_snapshot(checkpoint={"conflict": True, "in_worktree": False}))
    assert conflict["status"] == "UNKNOWN"
    assert REASON_CHECKPOINT_CONFLICT in conflict["reason_codes"]
    worktree = build_contract(_snapshot(checkpoint={"in_worktree": True, "conflict": False}))
    assert worktree["status"] == "UNKNOWN"
    assert REASON_CHECKPOINT_IN_WORKTREE in worktree["reason_codes"]
    stale = classify_status(
        has_evidence=True,
        current_lag_hours=30,
        extra_reasons=[REASON_STALE_CHECKPOINT],
    )
    assert stale[0] == "STALE"


def test_restart_does_not_skip_pending_unit() -> None:
    result = resume_units(
        planned=["20260807_20260814", "20260812_20260819", "20260819_20260821"],
        completed=["20260807_20260814"],
    )
    assert result["skipped_resume"] == ["20260807_20260814"]
    assert result["next_unit"] == "20260812_20260819"
    assert "20260812_20260819" in result["pending"]
    assert "20260819_20260821" in result["pending"]
    assert result["next_unit"] not in result["skipped_resume"]


def test_missing_source_timestamp_and_delayed_timer() -> None:
    missing = build_contract(
        _snapshot(
            source_publication_or_update_at=None,
            db={
                "available": True,
                "columns": [
                    "contrato_id",
                    "ingested_at",
                    "data_publicacao_fonte",
                    "data_atualizacao_fonte",
                    "first_seen_at",
                ],
                "latest_ingested_at": "2026-08-19T09:21:09Z",
                "latest_source_publication_or_update_at": None,
            },
        )
    )
    assert missing["status"] == "UNKNOWN"
    assert REASON_MISSING_SOURCE_TIMESTAMP in missing["reason_codes"]
    delayed = build_contract(
        _snapshot(
            timer={
                "active": True,
                "last_run_at": "2026-08-10T09:00:00Z",
                "next_run_at": "2026-08-12T09:00:00Z",
                "last_exec_status": 0,
            }
        )
    )
    assert REASON_TIMER_DELAYED in delayed["reason_codes"]


def test_build_contract_required_fields_and_status_domain() -> None:
    artifact = build_contract(_snapshot())
    assert artifact["contract_version"] == CONTRACT_VERSION
    required = [
        "source_publication_or_update_at",
        "first_observed_at",
        "persisted_at",
        "source_observed_at",
        "run_id",
        "attempt_id",
        "source_window",
        "expected",
        "fetched",
        "persisted",
        "deduplicated",
        "failed",
        "checkpoint_before",
        "checkpoint_after",
        "latest_successful_closed_window",
        "oldest_unresolved_gap",
        "current_lag_hours",
        "lag_p50_hours",
        "lag_p95_hours",
        "lag_p99_hours",
        "status",
        "reason_codes",
        "as_of",
        "deployed_sha",
    ]
    for field in required:
        assert field in artifact, field
    assert artifact["status"] in STATUSES
    assert artifact["latest_successful_closed_window"] == "20260812_20260819"
    assert artifact["source_observed_at"] == "2026-08-19T09:21:14Z"
    assert artifact["oldest_unresolved_gap"] == "20260810_20260817"
    assert artifact["expected"] == 45703
    assert artifact["pages_expected"] == artifact["pages_fetched"] == 92
    assert health_exit("FRESH") == 0
    assert health_exit("DEGRADED") == 1
    assert health_exit("STALE") == 2
    assert health_exit("UNKNOWN") == 2


def test_overlapped_blocked_window_is_not_material_incomplete() -> None:
    """20260810_20260817 is blocked but covered by later completed lookbacks."""
    artifact = build_contract(_snapshot())
    assert artifact["unresolved_window_count"] == 1
    assert REASON_WINDOW_INCOMPLETE not in artifact["reason_codes"]


def test_cadence_4h_fixture_does_not_claim_cannot_meet_24h(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/pncp_contract_freshness/cadence-4h.snapshot.json")
    out = tmp_path / "cadence-4h.json"
    rc = main(["--from-snapshot", str(fixture), "--output", str(out), "--json", "--health"])
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["contract_version"] == CONTRACT_VERSION
    assert artifact["slo"]["timer_max_inter_run_hours"] == 4.0
    assert artifact["slo"]["sustainable_hard_guardrail"] is True
    assert artifact["slo"]["sustainable_operational_target"] is True
    assert REASON_CADENCE_CANNOT_MEET_24H not in artifact["reason_codes"]
    assert artifact["status"] == "FRESH"
    assert rc == artifact["health_exit"] == 0


def test_committed_host_fixture_drives_shipped_cli(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/pncp_contract_freshness/host-2026-08-20.snapshot.json")
    out = tmp_path / "fixture-out.json"
    rc = main(["--from-snapshot", str(fixture), "--output", str(out), "--json"])
    assert rc == 0
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["contract_version"] == CONTRACT_VERSION
    assert artifact["status"] == "STALE"
    assert artifact["status"] != "FRESH"
    assert artifact["latest_successful_closed_window"] == "20260812_20260819"
    assert artifact["health_exit"] == 2


def test_cli_from_snapshot_twice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    rc1 = main(["--from-snapshot", str(path), "--output", str(out1), "--json"])
    rc2 = main(["--from-snapshot", str(path), "--output", str(out2), "--json"])
    assert rc1 == 0 and rc2 == 0
    a = json.loads(out1.read_text(encoding="utf-8"))
    b = json.loads(out2.read_text(encoding="utf-8"))
    assert a["contract_version"] == b["contract_version"] == CONTRACT_VERSION
    assert a["status"] == b["status"]
    assert a["status"] in STATUSES
    assert a["status"] != "FRESH"
    captured = capsys.readouterr()
    assert CONTRACT_VERSION in captured.out


def _load_check_alerts():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "check-alerts.py"
    spec = importlib.util.spec_from_file_location("check_alerts_mod", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_alerts_use_shipped_evaluate() -> None:
    alerts = _load_check_alerts()
    AlertRegistry = alerts.AlertRegistry
    check_pncp_contract_freshness = alerts.check_pncp_contract_freshness

    registry = AlertRegistry()
    stale = build_contract(_snapshot())
    check_pncp_contract_freshness(registry, contract=stale)
    assert registry.has_critical()
    assert any(a["category"] == "freshness" for a in registry.alerts)
    registry2 = AlertRegistry()
    fresh_status, _ = classify_status(has_evidence=True, current_lag_hours=2.0)
    assert fresh_status == "FRESH"
    check_pncp_contract_freshness(
        registry2,
        contract={"status": "FRESH", "reason_codes": [], "current_lag_hours": 2.0, "health_exit": 0},
    )
    assert not registry2.has_critical()
    assert not registry2.has_warnings()


def test_parse_dt_systemd_show_stamp() -> None:
    parsed = parse_dt("Wed 2026-08-19 06:00:20 -03")
    assert parsed == datetime(2026, 8, 19, 9, 0, 20, tzinfo=UTC)
    nxt = parse_dt("Fri 2026-08-21 06:00:31 -03")
    assert nxt == datetime(2026, 8, 21, 9, 0, 31, tzinfo=UTC)
    assert parse_dt("n/a") is None


def test_collect_timer_snapshot_parses_systemd_stamps() -> None:
    snap = collect_timer_snapshot(
        show_timer={
            "ActiveState": "active",
            "UnitFileState": "enabled",
            "LastTriggerUSec": "Wed 2026-08-19 06:00:20 -03",
            "NextElapseUSecRealtime": "Fri 2026-08-21 06:00:31 -03",
        },
        show_service={
            "ExecMainStartTimestamp": "Wed 2026-08-19 06:00:20 -03",
            "ExecMainStatus": "0",
            "Result": "success",
        },
    )
    assert snap["last_run_at"] == "2026-08-19T09:00:20Z"
    assert snap["next_run_at"] == "2026-08-21T09:00:31Z"
    assert snap["last_exec_status"] == 0


class _FakePgConn:
    def __init__(self, columns: list[str], aggregate: dict) -> None:
        self.columns = columns
        self.aggregate = aggregate
        self.statements: list[str] = []
        self.closed = False

    def cursor(self, *args: object, **kwargs: object) -> _FakePgCursor:
        return _FakePgCursor(self)

    def close(self) -> None:
        self.closed = True


class _FakePgCursor:
    def __init__(self, conn: _FakePgConn) -> None:
        self.conn = conn
        self._rows: list[tuple[str, ...]] = []
        self._row: dict | None = None

    def execute(self, sql: str, params=None) -> None:
        self.conn.statements.append(sql)
        low = sql.lower()
        if "information_schema.columns" in low:
            self._rows = [(name,) for name in self.conn.columns]
            self._row = None
            return
        if "from pncp_supplier_contracts" in low:
            self._rows = []
            self._row = dict(self.conn.aggregate)
            return
        self._rows = []
        self._row = None

    def fetchall(self) -> list[tuple[str, ...]]:
        return self._rows

    def fetchone(self) -> dict | None:
        return self._row

    def close(self) -> None:
        return None


def _live_pg_connect(_dsn: str) -> _FakePgConn:
    return _FakePgConn(
        columns=[
            "contrato_id",
            "ingested_at",
            "data_publicacao_fonte",
            "data_atualizacao_fonte",
            "first_seen_at",
        ],
        aggregate={
            "row_count": 4591752,
            "latest_ingested_at": datetime(2026, 8, 19, 9, 21, 9, tzinfo=UTC),
            "latest_first_seen_at": datetime(2026, 8, 19, 9, 21, 9, tzinfo=UTC),
            "max_data_publicacao_fonte": datetime(2026, 8, 19, tzinfo=UTC).date(),
            "max_data_atualizacao_fonte": datetime(2026, 8, 19, tzinfo=UTC).date(),
        },
    )


def test_collect_db_snapshot_fills_source_first_seen_ingested() -> None:
    db = collect_db_snapshot(dsn="postgresql://test/pncp_datalake", connect=_live_pg_connect)
    assert db["available"] is True
    assert db["latest_ingested_at"] == "2026-08-19T09:21:09Z"
    assert db["latest_first_seen_at"] == "2026-08-19T09:21:09Z"
    assert db["latest_source_publication_or_update_at"] == "2026-08-19T00:00:00Z"


def test_collect_snapshot_live_shaped_is_stale_from_lag_not_unknown(tmp_path: Path) -> None:
    """Drive collect_snapshot (not a hand-filled artifact) with host-shaped inputs."""
    evidence = tmp_path / "incremental-latest.json"
    evidence.write_text(
        json.dumps(
            {
                "run_id": "contracts-90d-20260819T090020Z-2d53827e9d",
                "git_sha": "9c5e7d47f99902d9d97cf479aefbba8cd391a14d",
                "completed_at": "2026-08-19T09:21:14Z",
                "windows": [
                    {
                        "window_key": "20260812_20260819",
                        "status": "completed",
                        "pages": 92,
                        "expected": 45703,
                        "fetched": 45703,
                        "persisted": 18495,
                        "skipped": 27208,
                        "page_errors": 0,
                        "closed_at": "2026-08-19T09:21:14Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "contracts_full.json").write_text(
        json.dumps(
            {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": ["20260807_20260814", "20260812_20260819"],
                "blocked_windows": ["20260810_20260817"],
                "failed_windows": [],
                "updated_at": "2026-08-19T09:21:14Z",
                "last_error": "source_population_drift:totalRegistros 44515 -> 44517",
                "meta": {
                    "logical_job_id": "pncp-contracts-incremental",
                    "attempt_run_id": "contracts-90d-20260819T090020Z-2d53827e9d",
                    "checkpoint_version": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    timer = collect_timer_snapshot(
        show_timer={
            "ActiveState": "active",
            "UnitFileState": "enabled",
            "LastTriggerUSec": "Wed 2026-08-19 06:00:20 -03",
            "NextElapseUSecRealtime": "Fri 2026-08-21 06:00:31 -03",
        },
        show_service={
            "ExecMainStartTimestamp": "Wed 2026-08-19 06:00:20 -03",
            "ExecMainStatus": "0",
            "Result": "success",
        },
    )
    snapshot = collect_snapshot(
        live=True,
        evidence_path=evidence,
        checkpoint_dir=ckpt_dir,
        production=False,
        repo_root=tmp_path,
        state_root=tmp_path,
        dsn="postgresql://test/pncp_datalake",
        connect=_live_pg_connect,
        timer=timer,
        as_of=NOW,
    )
    assert snapshot["db"]["available"] is True
    assert snapshot["source_publication_or_update_at"]
    assert snapshot["persisted_at"]
    artifact = build_contract(snapshot)
    assert artifact["status"] == "STALE"
    assert artifact["status"] != "UNKNOWN"
    assert REASON_LAG_ABOVE_HARD_GUARDRAIL in artifact["reason_codes"]
    assert REASON_MISSING_SOURCE_TIMESTAMP not in artifact["reason_codes"]
    assert artifact["current_lag_hours"] is not None
    assert artifact["current_lag_hours"] > DESIRED_HARD_GUARDRAIL_HOURS
    assert artifact["last_run_at"] == "2026-08-19T09:00:20Z"
    assert artifact["next_run_at"] == "2026-08-21T09:00:31Z"
    assert artifact["pages_expected"] == artifact["pages_fetched"] == 92


def test_failed_upsert_lag_is_last_successful_close_not_checkpoint_updated_at(tmp_path: Path) -> None:
    """Live 2026-08-20 shape: completed 20260812_20260819, failed 20260813_20260820.

    checkpoint.updated_at is the FAILED attempt. Lag must stay >24h vs as_of 21:21Z.
    """
    as_of = datetime(2026, 8, 20, 21, 21, tzinfo=UTC)
    evidence = tmp_path / "incremental-latest.json"
    evidence.write_text(
        json.dumps(
            {
                "run_id": "contracts-90d-20260820T190346Z-3b2e6f48ba",
                "git_sha": "7ca6a8709e8e7dbf021b2f7aa12fbf4b88684428",
                "status": "failed",
                "completed_at": "2026-08-20T19:19:51Z",
                "windows": [
                    {
                        "window_key": "20260813_20260820",
                        "status": "failed",
                        "pages": 61,
                        "expected": 54005,
                        "fetched": 30500,
                        "persisted": 0,
                        "skipped": 30000,
                        "page_errors": 3,
                        "error": "upsert failed window=20260813_20260820 page~61: out of shared memory",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "contracts_full.json").write_text(
        json.dumps(
            {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": ["20260807_20260814", "20260812_20260819"],
                "blocked_windows": [],
                "failed_windows": ["20260813_20260820"],
                "updated_at": "2026-08-20T19:19:51Z",
                "last_error": "upsert failed window=20260813_20260820 page~61: out of shared memory",
                "window_results": {
                    "20260812_20260819": {
                        "terminal": "COMPLETE",
                        "expected": 45703,
                        "fetched": 45703,
                        "persisted": 18495,
                        "skipped": 27208,
                        "page_errors": 0,
                    },
                    "20260813_20260820": {
                        "terminal": "FAILED",
                        "expected": 54005,
                        "fetched": 30500,
                        "persisted": 0,
                        "page_errors": 3,
                    },
                },
                "meta": {
                    "logical_job_id": "pncp-contracts-incremental",
                    "attempt_run_id": "contracts-90d-20260820T190346Z-3b2e6f48ba",
                    "checkpoint_version": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    timer = collect_timer_snapshot(
        show_timer={
            "ActiveState": "active",
            "UnitFileState": "enabled",
            "LastTriggerUSec": "Thu 2026-08-20 16:03:46 -03",
            "NextElapseUSecRealtime": "Thu 2026-08-20 20:01:34 -03",
        },
        show_service={
            "ExecMainStartTimestamp": "Thu 2026-08-20 16:03:46 -03",
            "ExecMainStatus": "1",
            "Result": "exit-code",
        },
    )
    local_dir = tmp_path / "local-backups"
    offsite_dir = tmp_path / "offsite-backups"
    local_dir.mkdir()
    offsite_dir.mkdir()
    (local_dir / "pncp.dump").write_bytes(b"dump")
    old = offsite_dir / "daily"
    old.mkdir()
    stale = old / "pncp_datalake-2026-07-23.dump"
    stale.write_bytes(b"old")
    os.utime(stale, (as_of.timestamp() - 28 * 86400, as_of.timestamp() - 28 * 86400))
    snapshot = collect_snapshot(
        live=True,
        evidence_path=evidence,
        checkpoint_dir=ckpt_dir,
        production=False,
        repo_root=tmp_path,
        state_root=tmp_path,
        dsn="postgresql://test/pncp_datalake",
        connect=_live_pg_connect,
        timer=timer,
        as_of=as_of,
        backup_local_dir=local_dir,
        backup_offsite_dir=offsite_dir,
    )
    artifact = build_contract(snapshot)
    failed_stamp = parse_dt("2026-08-20T19:19:51Z")
    assert failed_stamp is not None
    fake_lag = (as_of - failed_stamp).total_seconds() / 3600.0
    assert fake_lag < DESIRED_HARD_GUARDRAIL_HOURS
    assert artifact["current_lag_hours"] is not None
    assert artifact["current_lag_hours"] > DESIRED_HARD_GUARDRAIL_HOURS
    assert artifact["current_lag_hours"] > fake_lag
    assert artifact["status"] != "FRESH"
    assert artifact["status"] == "STALE"
    assert REASON_LAG_ABOVE_HARD_GUARDRAIL in artifact["reason_codes"]
    assert artifact["latest_successful_closed_window"] == "20260812_20260819"
    assert artifact["backup_freshness"]["reason_code"] == REASON_BACKUP_UNAVAILABLE
    close = last_successful_close_at(
        latest_closed=None,
        snapshot=snapshot,
        completed_keys=["20260619_20260718", "20260807_20260814", "20260812_20260819"],
    )
    assert close == datetime(2026, 8, 19, tzinfo=UTC)
    assert artifact["latest_successful_closed_window"] == "20260812_20260819"


def test_collect_backup_snapshot_stale_offsite_is_unavailable(tmp_path: Path) -> None:
    as_of = datetime(2026, 8, 20, 21, 21, tzinfo=UTC)
    local_dir = tmp_path / "local"
    offsite_dir = tmp_path / "offsite" / "daily"
    local_dir.mkdir()
    offsite_dir.mkdir(parents=True)
    recent = local_dir / "pncp_datalake-20260820.dump"
    recent.write_bytes(b"local")
    os.utime(recent, (as_of.timestamp() - 9 * 3600, as_of.timestamp() - 9 * 3600))
    stale = offsite_dir / "pncp_datalake-2026-07-23.dump"
    stale.write_bytes(b"offsite")
    os.utime(stale, (as_of.timestamp() - 28 * 86400, as_of.timestamp() - 28 * 86400))
    snap = collect_backup_snapshot(as_of=as_of, local_dir=local_dir, offsite_dir=offsite_dir.parent)
    assert snap["offsite_age_hours"] is not None
    assert snap["offsite_age_hours"] > 28
    assert snap["available"] is False
    assert (
        classify_backup(
            available=snap["available"],
            latest_age_hours=snap["latest_age_hours"],
            max_age_hours=float(snap["max_age_hours"]),
        )
        == REASON_BACKUP_UNAVAILABLE
    )
    missing_offsite = collect_backup_snapshot(as_of=as_of, local_dir=local_dir, offsite_dir=tmp_path / "no-offsite")
    assert missing_offsite["available"] is False
    proof = tmp_path / "restore.json"
    proof.write_text(json.dumps({"hash_identical": False}), encoding="utf-8")
    mismatch = collect_backup_snapshot(
        as_of=as_of,
        local_dir=local_dir,
        offsite_dir=offsite_dir.parent,
        restore_proof_path=proof,
    )
    assert mismatch["restore_hash_identical"] is False
    assert (
        classify_backup(
            available=True,
            restore_hash_identical=mismatch["restore_hash_identical"],
        )
        == REASON_RESTORE_MISMATCH
    )


def test_real_db_marker_not_mocked_in_this_module() -> None:
    import scripts.ops.pncp_contract_freshness as shipped

    source = Path(shipped.__file__).read_text(encoding="utf-8")
    assert "unittest.mock" not in source
    assert "pytest.mark.real_db" not in source
    assert "psycopg2.connect = " not in source


def test_shipped_timer_is_every_4h_or_6h_with_explicit_timezone() -> None:
    cadence = load_shipped_cadence()
    text = TIMER_UNIT_PATH.read_text(encoding="utf-8")
    parsed = cadence_from_unit_text(text)
    assert parsed["on_calendar"] == cadence["on_calendar"]
    assert cadence["timezone"] in {"America/Sao_Paulo", "UTC"}
    assert cadence["timezone_explicit"] is True
    assert cadence["persistent"] is True
    assert cadence["max_inter_run_hours"] in {4.0, 6.0}
    assert cadence["max_inter_run_hours"] <= DESIRED_HARD_GUARDRAIL_HOURS
    four = parse_oncalendar_spec("*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo")
    six = parse_oncalendar_spec("*-*-* 00,06,12,18:00:00 America/Sao_Paulo")
    weekly = parse_oncalendar_spec("Mon,Wed,Fri *-*-* 06:00:00")
    assert four["max_inter_run_hours"] == 4.0
    assert six["max_inter_run_hours"] == 6.0
    assert weekly["max_inter_run_hours"] == 72.0
    assert four["timezone"] == "America/Sao_Paulo"
    assert "Mon,Wed,Fri" not in cadence["on_calendar"]
    slo = build_contract(_snapshot(timer={"active": True, "last_exec_status": 0})).get("slo")
    assert slo["timer_on_calendar"] == cadence["on_calendar"]
    assert slo["sustainable_hard_guardrail"] is True
    if cadence["max_inter_run_hours"] <= DESIRED_OPERATIONAL_TARGET_HOURS:
        assert slo["sustainable_operational_target"] is True
        assert REASON_CADENCE_CANNOT_MEET_6H not in build_contract(_snapshot()).get("reason_codes")
    assert REASON_CADENCE_CANNOT_MEET_24H not in build_contract(_snapshot()).get("reason_codes")


def test_lock_busy_exit_75_is_not_fresh_or_closed_window() -> None:
    service = load_shipped_service_text()
    assert LOCK_BUSY_EXIT in parse_success_exit_statuses(service)
    status, reasons = classify_status(
        has_evidence=True,
        current_lag_hours=2.0,
        lock_busy_no_close=True,
    )
    assert status != "FRESH"
    assert status == "DEGRADED"
    assert REASON_LOCK_BUSY_NO_CLOSE in reasons
    artifact = build_contract(
        _snapshot(
            windows=[_closed_window(closed_at="2026-08-20T12:00:00Z")],
            timer={
                "active": True,
                "last_run_at": "2026-08-20T12:00:00Z",
                "next_run_at": "2026-08-20T16:00:00Z",
                "last_exec_status": 75,
                "last_result": "success",
                "lock_busy": True,
                "on_calendar": "*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo",
            },
            as_of="2026-08-20T12:30:00Z",
        )
    )
    assert artifact["status"] != "FRESH"
    assert REASON_LOCK_BUSY_NO_CLOSE in artifact["reason_codes"]
    assert health_exit(artifact["status"]) != 0


def test_delayed_missed_reboot_and_overlap_are_named() -> None:
    missed = build_contract(
        _snapshot(
            timer={
                "active": True,
                "last_run_at": "2026-08-20T08:00:00Z",
                "next_run_at": "2026-08-20T12:00:00Z",
                "last_exec_status": 0,
                "on_calendar": "*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo",
            },
            as_of="2026-08-20T14:00:00Z",
        )
    )
    assert REASON_MISSED_TIMER in missed["reason_codes"] or REASON_TIMER_DELAYED in missed["reason_codes"]
    reboot = build_contract(_snapshot(reboot_without_persistent=True))
    assert REASON_REBOOT_CATCHUP_REQUIRED in reboot["reason_codes"]
    assert cadence_from_unit_text(TIMER_UNIT_PATH.read_text(encoding="utf-8"))["persistent"] is True
    overlap_status, _ = classify_status(
        has_evidence=True,
        current_lag_hours=1.0,
        lock_busy_no_close=True,
    )
    assert overlap_status != "FRESH"


def test_backup_unavailable_and_restore_mismatch_named() -> None:
    assert classify_backup(available=False) == REASON_BACKUP_UNAVAILABLE
    assert classify_backup(available=True, restore_hash_identical=False) == REASON_RESTORE_MISMATCH
    assert classify_backup(available=True, restore_hash_identical=True, latest_age_hours=2.0) is None
    assert classify_backup(available=True, latest_age_hours=40.0) == REASON_BACKUP_UNAVAILABLE
    missing = build_contract(_snapshot(backup={"available": False}))
    assert REASON_BACKUP_UNAVAILABLE in missing["reason_codes"]
    assert missing["backup_freshness"]["reason_code"] == REASON_BACKUP_UNAVAILABLE
    mismatch = build_contract(_snapshot(backup={"available": True, "restore_hash_identical": False}))
    assert REASON_RESTORE_MISMATCH in mismatch["reason_codes"]
    assert mismatch["status"] in STATUSES


def test_alerts_details_include_detectability_fields() -> None:
    alerts = _load_check_alerts()
    registry = alerts.AlertRegistry()
    artifact = build_contract(_snapshot())
    assert "checkpoint_health" in artifact
    assert "backup_freshness" in artifact
    alerts.check_pncp_contract_freshness(registry, contract=artifact)
    freshness = [a for a in registry.alerts if a["category"] == "freshness"]
    assert freshness
    details = freshness[0]["details"]
    assert "latest_successful_closed_window" in details
    assert "current_lag_hours" in details
    assert "next_run_at" in details
    assert "last_error" in details
    assert "backup_freshness" in details
    assert "checkpoint_health" in details


def test_every_4h_does_not_claim_cadence_cannot_meet_24h() -> None:
    four = resolve_effective_cadence({"on_calendar": "*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo"})
    assert four["max_inter_run_hours"] == 4.0
    status, reasons = classify_status(
        has_evidence=True,
        current_lag_hours=3.0,
        cadence_max_inter_run_hours=4.0,
    )
    assert status == "FRESH"
    assert REASON_CADENCE_CANNOT_MEET_24H not in reasons
    assert REASON_CADENCE_CANNOT_MEET_6H not in reasons
    weekly = resolve_effective_cadence({"on_calendar": "Mon,Wed,Fri *-*-* 06:00:00"})
    assert weekly["max_inter_run_hours"] == 72.0
    stale_status, stale_reasons = classify_status(
        has_evidence=True,
        current_lag_hours=3.0,
        cadence_max_inter_run_hours=72.0,
    )
    assert stale_status != "FRESH"
    assert REASON_CADENCE_CANNOT_MEET_24H in stale_reasons
    assert health_exit("FRESH") == 0
    assert health_exit("DEGRADED") == 1
    assert health_exit("STALE") == 2
    assert health_exit("UNKNOWN") == 2
