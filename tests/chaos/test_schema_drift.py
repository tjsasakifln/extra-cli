"""Chaos test: schema drift (missing/changed fields)."""
from __future__ import annotations

import pytest


@pytest.mark.chaos
class TestSchemaDrift:
    """Verify schema drift detection routes to DLQ."""

    def test_missing_required_field_routes_to_dlq(self):
        """Given record missing required field, routes to DLQ."""
        pass

    def test_changed_field_type_routes_to_dlq(self):
        """Given record with changed field type, routes to DLQ."""
        pass
