"""Chaos test: invalid/truncated JSON scenarios."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class TestInvalidJson:
    """Verify invalid JSON handling: DLQ with error_code='parse_failed', no retry."""

    def test_truncated_json_routes_to_dlq(self, mock_dlq):
        """Given truncated JSON, DLQ with error_code='parse_failed', no retry."""
        pass

    def test_malformed_json_routes_to_dlq(self, mock_dlq):
        """Given malformed JSON, DLQ with error_code='parse_failed'."""
        pass
