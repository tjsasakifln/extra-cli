"""Unit tests for monitor crawl date window defaults."""
from __future__ import annotations

from datetime import date

from scripts.crawl.monitor import resolve_crawl_date_window


def test_incremental_defaults_to_7_days() -> None:
    today = date(2026, 7, 18)
    d_from, d_to = resolve_crawl_date_window("incremental", today=today)
    assert d_to == today
    assert d_from == date(2026, 7, 11)


def test_full_defaults_to_30_days() -> None:
    today = date(2026, 7, 18)
    d_from, d_to = resolve_crawl_date_window("full", today=today)
    assert d_to == today
    assert d_from == date(2026, 6, 18)


def test_smoke_is_today_only() -> None:
    today = date(2026, 7, 18)
    d_from, d_to = resolve_crawl_date_window("smoke", today=today)
    assert d_from == d_to == today


def test_explicit_dates_win() -> None:
    d_from, d_to = resolve_crawl_date_window(
        "incremental",
        date_from="2026-01-01",
        date_to="2026-01-10",
        today=date(2026, 7, 18),
    )
    assert d_from == date(2026, 1, 1)
    assert d_to == date(2026, 1, 10)
