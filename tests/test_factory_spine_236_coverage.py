"""Refs #236 — ente×fonte matrix is fail-closed; absence is never zero."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.factory_spine.contracts import (
    COVERAGE_TERMINALS,
    assert_publishable_coverage,
    canonical_entity_ids,
    publish_coverage_cell,
    reconcile_coverage_artifacts,
)


def test_issue_236_absence_of_execution_is_never_zero() -> None:
    with pytest.raises(ValueError, match="absence of execution"):
        assert_publishable_coverage("ZERO_CONFIRMED", executed=False)
    with pytest.raises(ValueError, match="absence of execution"):
        publish_coverage_cell(
            canonical_entity_key="extra-canonical-0001",
            source="pncp",
            status="ZERO_CONFIRMED",
            executed=False,
            applicability=True,
            applicability_reason="not-run",
        )


def test_issue_236_zero_confirmed_requires_complete_raw_proof() -> None:
    with pytest.raises(ValueError, match="ZERO_CONFIRMED requires"):
        publish_coverage_cell(
            canonical_entity_key="extra-canonical-0001",
            source="pncp",
            status="ZERO_CONFIRMED",
            executed=True,
            applicability=True,
            applicability_reason="query_ran",
            request_completed=True,
            scope_complete=True,
            pagination_reconciled=False,
            records_observed=0,
        )
    cell = publish_coverage_cell(
        canonical_entity_key="extra-canonical-0001",
        source="pncp",
        status="ZERO_CONFIRMED",
        executed=True,
        applicability=True,
        applicability_reason="complete_empty_scope",
        request_completed=True,
        scope_complete=True,
        pagination_reconciled=True,
        records_observed=0,
        raw_uri="cas://raw-http/ab",
        raw_sha256="a" * 64,
        history=({"status": "FAILED", "checked_at": "2026-08-01T00:00:00+00:00"},),
    )
    assert cell["status"] in COVERAGE_TERMINALS
    assert cell["history"][0]["status"] == "FAILED"


def test_issue_236_excel_manifest_kpi_reconcile_1093_ids() -> None:
    universe = canonical_entity_ids()
    checked = datetime(2026, 8, 15, tzinfo=UTC)
    cells = [
        publish_coverage_cell(
            canonical_entity_key=entity_id,
            source="pncp",
            status="BLOCKED",
            executed=True,
            applicability=True,
            applicability_reason="probe_blocked_pending_recheck",
            request_completed=True,
            http_statuses=(403,),
            checked_at=checked,
            next_action="human_review_source_access",
        )
        for entity_id in universe
    ]
    artifacts = reconcile_coverage_artifacts(universe, cells)
    assert artifacts["kpi"]["entity_count"] == 1093
    assert len(artifacts["manifest_ids"]) == 1093
    assert artifacts["manifest_ids"] == tuple(sorted(universe))
    assert len(artifacts["excel_rows"]) == 1093
    assert set(row["canonical_entity_key"] for row in artifacts["excel_rows"]) == set(universe)
    assert artifacts["kpi"]["by_status"]["BLOCKED"] == 1093
