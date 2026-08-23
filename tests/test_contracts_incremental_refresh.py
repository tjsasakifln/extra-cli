from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from scripts.crawl.contracts_crawler import CrawlCheckpoint
from scripts.crawl.run_contracts_90d_pilot import utc_today
from scripts.crawl.run_contracts_incremental import (
    current_incremental_window_key,
    reopen_current_window,
)


def test_pncp_operational_date_is_utc_across_brazil_midnight_boundary() -> None:
    brazil = timezone(-timedelta(hours=3))
    local_late_evening = datetime(2026, 8, 22, 23, 28, tzinfo=brazil)
    assert utc_today(local_late_evening) == date(2026, 8, 23)


def test_current_incremental_window_is_reopened_for_every_timer_slot() -> None:
    key = current_incremental_window_key(days=7, today=date(2026, 8, 22))
    assert key == "20260815_20260821"
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
