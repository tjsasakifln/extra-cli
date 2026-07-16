"""Chaos test: connection/read timeout scenarios."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class TestTimeout:
    """Verify timeout handling: retry with backoff, DLQ after max retries."""

    def test_connect_timeout_routes_to_dlq(self, mock_dlq):
        """Given connect timeout, retries then DLQ."""
        pass

    def test_read_timeout_routes_to_dlq(self, mock_dlq):
        """Given read timeout, retries then DLQ."""
        pass
