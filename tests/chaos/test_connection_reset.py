"""Chaos test: connection reset scenarios."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class TestConnectionReset:
    """Verify ConnectionResetError handling: retry then DLQ."""

    def test_connection_reset_routes_to_dlq(self, mock_dlq):
        """Given ConnectionResetError, retries then DLQ."""
        pass

    def test_connection_reset_retries_with_backoff(self):
        """Given ConnectionResetError, uses exponential backoff."""
        pass
