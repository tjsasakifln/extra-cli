from __future__ import annotations

import importlib
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import scripts.freshness_gate as freshness_gate
from scripts.freshness_gate import (
    CriticalSourceSpec,
    _get_conn,
    _status_from_snapshot,
    evaluate_source,
)


def _spec() -> CriticalSourceSpec:
    return CriticalSourceSpec(
        source_name="pncp",
        purpose="editais_abertos",
        run_source="pncp",
        table_name="pncp_raw_bids",
        data_source="pncp",
        recent_window_hours=24,
        freshness_sla_hours=24,
        business_date_column="data_publicacao",
    )


def test_status_fresh_when_run_and_data_within_sla() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    status, reason = _status_from_snapshot(
        now=now,
        last_success_at=now - timedelta(hours=2),
        last_ingested_at=now - timedelta(hours=1),
        freshness_sla_hours=24,
    )
    assert status == "fresh"
    assert reason is None


def test_status_never_without_successful_run() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    status, reason = _status_from_snapshot(
        now=now,
        last_success_at=None,
        last_ingested_at=None,
        freshness_sla_hours=24,
    )
    assert status == "never"
    assert "No successful ingestion run" in reason


def test_status_stale_when_success_too_old() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    status, reason = _status_from_snapshot(
        now=now,
        last_success_at=now - timedelta(hours=30),
        last_ingested_at=now - timedelta(hours=1),
        freshness_sla_hours=24,
    )
    assert status == "stale"
    assert "above SLA" in reason


def test_status_stale_when_no_persisted_records() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    status, reason = _status_from_snapshot(
        now=now,
        last_success_at=now - timedelta(hours=2),
        last_ingested_at=None,
        freshness_sla_hours=24,
    )
    assert status == "stale"
    assert "no persisted active records" in reason


def test_evaluate_source_uses_run_and_data_snapshots() -> None:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    spec = _spec()

    with (
        patch(
            "scripts.freshness_gate._run_snapshot",
            return_value={
                "last_success_at": now - timedelta(hours=3),
                "successful_runs": 7,
                "total_runs": 9,
            },
        ),
        patch(
            "scripts.freshness_gate._data_snapshot",
            return_value={
                "last_ingested_at": now - timedelta(hours=2),
                "latest_business_date": now - timedelta(hours=4),
                "recent_records": 123,
                "total_records": 999,
            },
        ),
    ):
        row = evaluate_source(conn=object(), spec=spec, now=now)

    assert row["source"] == "pncp"
    assert row["freshness_status"] == "fresh"
    assert row["recent_records"] == 123
    assert row["successful_runs"] == 7
    assert row["failure_reason"] is None


def test_get_conn_wraps_connection_error() -> None:
    with patch("scripts.freshness_gate.psycopg2.connect", side_effect=Exception("db down")):
        try:
            _get_conn("postgresql://invalid")
        except RuntimeError as exc:
            assert "Failed to connect to local datalake" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError on connection failure")


def test_get_conn_sets_autocommit() -> None:
    fake_conn = MagicMock()
    fake_conn.autocommit = False
    with patch("scripts.freshness_gate.psycopg2.connect", return_value=fake_conn):
        conn = _get_conn("postgresql://ok")
    assert conn is fake_conn
    assert conn.autocommit is True


def test_sla_env_overrides_are_loaded() -> None:
    old_pncp = os.environ.get("FRESHNESS_SLA_PNCP_HOURS")
    old_contracts = os.environ.get("FRESHNESS_SLA_CONTRACTS_HOURS")
    try:
        os.environ["FRESHNESS_SLA_PNCP_HOURS"] = "12"
        os.environ["FRESHNESS_SLA_CONTRACTS_HOURS"] = "240"
        reloaded = importlib.reload(freshness_gate)
        specs = {spec.source_name: spec for spec in reloaded.CRITICAL_SOURCES}
        assert specs["pncp"].freshness_sla_hours == 12
        assert specs["contracts"].freshness_sla_hours == 240
    finally:
        if old_pncp is None:
            os.environ.pop("FRESHNESS_SLA_PNCP_HOURS", None)
        else:
            os.environ["FRESHNESS_SLA_PNCP_HOURS"] = old_pncp
        if old_contracts is None:
            os.environ.pop("FRESHNESS_SLA_CONTRACTS_HOURS", None)
        else:
            os.environ["FRESHNESS_SLA_CONTRACTS_HOURS"] = old_contracts
        importlib.reload(freshness_gate)
