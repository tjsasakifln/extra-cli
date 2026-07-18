"""Unit tests for entity-level freshness coverage reporter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.coverage.entity_freshness import (
    EntityFreshnessRow,
    build_report,
    classify_entity,
)


def test_classify_never() -> None:
    status, within, hours = classify_entity(
        last_seen_at=None,
        now=datetime(2026, 7, 18, tzinfo=UTC),
        sla_hours=24,
    )
    assert status == "never"
    assert within is False
    assert hours is None


def test_classify_fresh_within_sla() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=6)
    status, within, hours = classify_entity(last_seen_at=last, now=now, sla_hours=24)
    assert status == "fresh"
    assert within is True
    assert hours is not None
    assert 5.9 < hours < 6.1


def test_classify_stale_beyond_sla() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=48)
    status, within, hours = classify_entity(last_seen_at=last, now=now, sla_hours=24)
    assert status == "stale"
    assert within is False
    assert hours is not None
    assert hours > 24


def test_classify_boundary_exactly_sla() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=24)
    status, within, hours = classify_entity(last_seen_at=last, now=now, sla_hours=24)
    assert status == "fresh"
    assert within is True
    assert hours is not None
    assert abs(hours - 24.0) < 1e-6


def test_build_report_empty_universe() -> None:
    report = build_report([], sla_hours=24, limitations=["unit"])
    assert report["denominator"] == 0
    assert report["numerator"] == 0
    assert report["pct"] == 0.0
    assert report["measurement_status"] == "READY_EMPTY_UNIVERSE"
    assert report["gaps_count"] == 0
    assert report["metric_id"] == "entity_freshness_coverage"
    assert report["kind"] == "coverage"


def test_build_report_mixed() -> None:
    rows = [
        EntityFreshnessRow(1, "A", "2026-07-18T10:00:00+00:00", 2.0, True, "fresh"),
        EntityFreshnessRow(2, "B", None, None, False, "never"),
        EntityFreshnessRow(3, "C", "2026-07-10T10:00:00+00:00", 200.0, False, "stale"),
    ]
    report = build_report(rows, sla_hours=24, limitations=[])
    assert report["denominator"] == 3
    assert report["numerator"] == 1
    assert abs(report["pct"] - 33.3333) < 0.01
    assert report["gaps_count"] == 2
    assert report["by_status"]["fresh"] == 1
    assert report["by_status"]["never"] == 1
    assert report["by_status"]["stale"] == 1
    assert report["within_sla_overall"] is False
    assert report["measurement_status"] == "READY"
    # entity-level (not source-level only)
    assert len(report["by_entity"]) == 3
    assert all("entity_id" in g for g in report["gaps"])
