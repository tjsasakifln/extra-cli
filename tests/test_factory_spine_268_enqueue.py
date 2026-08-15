"""Refs #268 — continuous enqueue from freshness and applicability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.factory_spine.contracts import (
    DEFAULT_SOURCES,
    canonical_entity_ids,
    plan_freshness_enqueue,
)
from scripts.factory_spine.runtime import apply_freshness_plan
from scripts.factory_spine.store import FactoryStore


def test_issue_268_dry_plan_covers_1093_ids_and_keeps_next_run() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    universe = canonical_entity_ids()
    pairs = [
        {
            "canonical_entity_key": entity_id,
            "entity_id": index,
            "source": source,
            "capability": "open_tenders",
            "applicability": "APPLICABLE" if source != "transparencia" else "NOT_APPLICABLE",
            "reason": "applicable_by_current_rule" if source != "transparencia" else "no_own_portal",
            "binding_version": "fresh-v1",
        }
        for index, entity_id in enumerate(universe, start=1)
        for source in DEFAULT_SOURCES
    ]
    decisions = plan_freshness_enqueue(pairs, now=now)
    assert len(decisions) == 1093 * 4
    assert {item.canonical_entity_key for item in decisions} == set(universe)
    assert all(item.next_run_at >= now for item in decisions)
    assert all(not item.billable for item in decisions if item.applicability == "NOT_APPLICABLE")
    assert sum(item.billable for item in decisions) == 1093 * 3


def test_issue_268_reenqueue_is_idempotent(tmp_path: Path) -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    store = FactoryStore(tmp_path)
    pairs = [
        {
            "canonical_entity_key": "extra-canonical-0001",
            "entity_id": 1,
            "source": "pncp",
            "capability": "open_tenders",
            "applicability": "APPLICABLE",
            "reason": "freshness_due",
            "binding_version": "fresh-v1",
        }
    ]
    first = apply_freshness_plan(store, plan_freshness_enqueue(pairs, now=now, expected_entities=1), now=now)
    second = apply_freshness_plan(store, plan_freshness_enqueue(pairs, now=now, expected_entities=1), now=now)
    assert first["queued"] == 1
    assert second["queued"] == 0
    assert second["existing"] == 1
    assert first["fully_reconciled"] is True
    assert len(store._read_jobs()) == 1


def test_issue_268_blocked_has_limited_recheck_not_infinite() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    decisions = plan_freshness_enqueue(
        [
            {
                "canonical_entity_key": "extra-canonical-0001",
                "entity_id": 1,
                "source": "pncp",
                "applicability": "BLOCKED",
                "reason": "captcha",
                "binding_version": "fresh-v1",
            }
        ],
        now=now,
        expected_entities=1,
        recheck_blocked_hours=72,
    )
    assert decisions[0].action == "recheck_blocked"
    assert decisions[0].billable is False
    assert decisions[0].next_run_at == now + timedelta(hours=72)
    with pytest.raises(ValueError, match="universe mismatch"):
        plan_freshness_enqueue([], now=now, expected_entities=1093)
