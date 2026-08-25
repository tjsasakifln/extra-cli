from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from scripts.crawl.contracts_crawler import CrawlCheckpoint
from scripts.crawl.run_contracts_90d_pilot import utc_today
from scripts.crawl.run_contracts_incremental import (
    current_incremental_window_key,
    current_incremental_window_keys,
    reopen_current_window,
    reopen_incremental_windows,
)


def test_pncp_operational_date_is_utc_across_brazil_midnight_boundary() -> None:
    brazil = timezone(-timedelta(hours=3))
    local_late_evening = datetime(2026, 8, 22, 23, 28, tzinfo=brazil)
    assert utc_today(local_late_evening) == date(2026, 8, 23)


def test_current_incremental_window_is_reopened_for_every_timer_slot() -> None:
    key = current_incremental_window_key(days=7, today=date(2026, 8, 22))
    assert key == "20260821_20260821"
    checkpoint = CrawlCheckpoint(
        mode="full",
        completed_windows=["20260807_20260814", key],
        last_error="old source population drift",
    )

    assert reopen_current_window(checkpoint, window_key=key) is True
    assert checkpoint.completed_windows == ["20260807_20260814"]
    # The old failure remains until a real successful crawl clears it. Removing
    # the completed marker alone must never manufacture a healthy state.
    assert checkpoint.last_error == "old source population drift"


def test_reopen_is_idempotent_after_a_failed_attempt() -> None:
    checkpoint = CrawlCheckpoint(mode="full", completed_windows=[])
    assert reopen_current_window(checkpoint, window_key="20260815_20260821") is False
    assert checkpoint.completed_windows == []


def test_all_daily_overlap_windows_are_reopened_for_every_timer_slot() -> None:
    keys = current_incremental_window_keys(days=7, today=date(2026, 8, 22))
    assert keys == [
        "20260815_20260815",
        "20260816_20260816",
        "20260817_20260817",
        "20260818_20260818",
        "20260819_20260819",
        "20260820_20260820",
        "20260821_20260821",
    ]
    checkpoint = CrawlCheckpoint(
        mode="full",
        completed_windows=["20260701_20260730", *keys],
    )

    assert reopen_incremental_windows(checkpoint, window_keys=keys) == keys
    assert checkpoint.completed_windows == ["20260701_20260730"]
