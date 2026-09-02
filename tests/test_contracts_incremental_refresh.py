from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from scripts.crawl.contracts_crawler import CrawlCheckpoint
from scripts.crawl.run_contracts_90d_pilot import utc_today
from scripts.crawl.run_contracts_incremental import (
    EXIT_RETRYABLE_SOURCE,
    current_incremental_window_key,
    current_incremental_window_keys,
    reopen_current_window,
    reopen_incremental_windows,
    retry_exit_for_report,
    run_with_one_retry,
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


def test_only_known_transient_source_failures_request_a_bounded_service_retry() -> None:
    drift = {
        "windows": [{"errors": ["source_population_drift:totalRegistros 8667 -> 8772"]}]
    }
    timeout = {"windows": [{"errors": ["connection_failed while reading PNCP"]}]}
    mixed = {
        "windows": [
            {"errors": ["source_population_drift: totalRegistros 8 -> 9", "upsert failed"]}
        ]
    }

    assert retry_exit_for_report(drift) == EXIT_RETRYABLE_SOURCE
    assert retry_exit_for_report(timeout) == EXIT_RETRYABLE_SOURCE
    assert retry_exit_for_report(mixed) == 1
    assert retry_exit_for_report({"windows": []}) == 1
    assert retry_exit_for_report({"windows": [{"errors": ["upsert failed: statement timeout"]}]}) == 1
    assert retry_exit_for_report({"windows": [{"errors": ["local checkpoint timeout"]}]}) == 1
    assert retry_exit_for_report(
        {"windows": [{"errors": ["Page 10: [connection_failed] Network read timed out"]}]}
    ) == EXIT_RETRYABLE_SOURCE
    assert retry_exit_for_report(
        {"windows": [{"errors": ["Page 5: [HTTP_RATE_LIMIT] 429"]}]}
    ) == EXIT_RETRYABLE_SOURCE
    assert retry_exit_for_report({"windows": [{"errors": ["http_rate_limit: 429"]}]}) == EXIT_RETRYABLE_SOURCE


def test_runner_retries_exactly_once_and_never_retries_structural_or_final_77() -> None:
    calls: list[int] = []
    sleeps: list[int] = []

    def sequence(*results: int):
        values = iter(results)
        return lambda: calls.append(1) or next(values)

    assert run_with_one_retry(sequence(EXIT_RETRYABLE_SOURCE, 0), sleep=sleeps.append) == 0
    assert len(calls) == 2 and sleeps == [300]
    calls.clear()
    sleeps.clear()
    assert run_with_one_retry(sequence(1), sleep=sleeps.append) == 1
    assert len(calls) == 1 and sleeps == []
    calls.clear()
    assert run_with_one_retry(sequence(EXIT_RETRYABLE_SOURCE, EXIT_RETRYABLE_SOURCE), sleep=sleeps.append) == EXIT_RETRYABLE_SOURCE
    assert len(calls) == 2 and sleeps == [300]
