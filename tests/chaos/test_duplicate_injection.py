"""Chaos test: duplicate submission scenarios."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class TestDuplicateInjection:
    """Verify dedup handles duplicate submissions correctly."""

    def test_duplicate_returns_unchanged(self):
        """Given duplicate submission, returns 'unchanged', no duplicate row."""
        pass

    def test_duplicate_updates_last_seen(self):
        """Given duplicate with update_last_seen strategy, updates timestamp."""
        pass
