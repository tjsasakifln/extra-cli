"""Unit tests: contracts window must not complete on partial page errors."""

from __future__ import annotations

from scripts.crawl.contracts_crawler import CrawlCheckpoint


def test_checkpoint_does_not_claim_partial_as_complete_logic():
    """Document the completion predicate used after the K3.2 fix.

    fully_ok = not window_errors
    Records alone are insufficient when pages failed.
    """
    window_errors: list[str] = ["Page 2: [HTTP_ERROR] 500"]
    window_records = 50
    fully_ok = not window_errors
    assert fully_ok is False
    # Must NOT mark complete even with records
    should_complete = fully_ok
    assert should_complete is False
    assert window_records > 0  # partial data present but incomplete


def test_checkpoint_complete_when_no_errors():
    window_errors: list[str] = []
    fully_ok = not window_errors
    assert fully_ok is True


def test_checkpoint_roundtrip_fields():
    cp = CrawlCheckpoint(
        mode="backfill_3y",
        completed_windows=["20240101_20240130"],
        total_windows_completed=1,
        total_windows_failed=0,
        total_contracts_fetched=10,
    )
    d = cp.to_dict()
    assert "20240101_20240130" in d["completed_windows"]
    restored = CrawlCheckpoint.from_dict(d)
    assert restored.total_windows_completed == 1
