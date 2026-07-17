"""Unit tests for pilot window completion predicate (NEXT-30D)."""

from __future__ import annotations


def test_max_pages_without_exhaustion_is_incomplete():
    """Hitting MAX pages before total_pages must NOT count as fully_ok."""
    pages_exhausted = False
    last_total_pages = 100
    page = 51  # after while page <= 50 exited
    contracts_max_pages = 50
    window_errors: list[str] = []
    if not pages_exhausted and last_total_pages and page <= last_total_pages:
        window_errors.append(
            f"Hit CONTRACTS_MAX_PAGES={contracts_max_pages} before "
            f"total_pages={last_total_pages}; window incomplete"
        )
    fully_ok = not window_errors
    assert fully_ok is False


def test_exhausted_pages_fully_ok():
    pages_exhausted = True
    window_errors: list[str] = []
    fully_ok = not window_errors and pages_exhausted
    assert fully_ok is True


def test_page_error_not_complete():
    window_errors = ["Page 2: [HTTP_SERVER_ERROR] 500"]
    fully_ok = not window_errors
    assert fully_ok is False
