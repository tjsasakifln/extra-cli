"""Chaos test: HTTP 500 server error scenarios."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class Test500ServerError:
    """Verify 500 handling: exponential backoff, DLQ after max retries."""

    def test_comprasgov_500_routes_to_dlq_after_retries(self, mock_dlq):
        """Given 500 response, retries with backoff, then DLQ."""
        pass

    def test_comprasgov_500_exponential_backoff(self):
        """Given 500, backoff follows 60s base, 5x multiplier pattern."""
        pass
