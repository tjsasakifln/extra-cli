"""Canonical quality contract tests — ARCH-RESET PR F."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.quality.canonical_checks import (
    CRITICAL_CHECKS,
    check_duplicate_detection,
    check_freshness_editais,
    check_unknown_status_not_open,
    check_volume_drop_alert,
    run_all_fixture_suite,
)


def test_critical_checks_count_is_ten() -> None:
    assert len(CRITICAL_CHECKS) == 10


def test_freshness_fail_closed_without_timestamp() -> None:
    r = check_freshness_editais(last_success_at=None)
    assert r.ok is False
    assert r.severity == "blocker"


def test_freshness_ok_within_sla() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    r = check_freshness_editais(last_success_at=now - timedelta(hours=5), now=now, sla_hours=48)
    assert r.ok is True


def test_unknown_status_cannot_be_open() -> None:
    r = check_unknown_status_not_open([{"id": "x", "status": "unknown", "is_open": True}])
    assert r.ok is False


def test_volume_drop_blocks() -> None:
    r = check_volume_drop_alert(current=10, baseline=100, drop_ratio_threshold=0.5)
    assert r.ok is False


def test_duplicates_detected() -> None:
    r = check_duplicate_detection(["1", "2", "1"])
    assert r.ok is False


def test_fixture_suite_runs_all_ids() -> None:
    report = run_all_fixture_suite()
    ids = {r["check_id"] for r in report["results"]}
    assert set(CRITICAL_CHECKS) == ids
    assert report["engine"] == "python_native"
