"""Refs #246 — durable idempotent jobs/attempts with lease and one terminal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.factory_spine.contracts import job_idempotency_key
from scripts.factory_spine.runtime import launch_spine
from scripts.factory_spine.store import FactoryStore


def _window() -> tuple[datetime, datetime, datetime, datetime]:
    start = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    return start, start + timedelta(hours=24), start + timedelta(hours=24), start


def test_issue_246_idempotent_enqueue_does_not_duplicate(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    start, end, deadline, nxt = _window()
    first, created = store.enqueue(
        entity_id=1,
        canonical_entity_key="extra-canonical-0001",
        source="pncp",
        capability="open_tenders",
        domain_key="pncp.gov.br",
        binding_version="v1",
        window_start=start,
        window_end=end,
        freshness_deadline=deadline,
        next_run_at=nxt,
    )
    second, created_again = store.enqueue(
        entity_id=1,
        canonical_entity_key="extra-canonical-0001",
        source="pncp",
        capability="open_tenders",
        domain_key="pncp.gov.br",
        binding_version="v1",
        window_start=start,
        window_end=end,
        freshness_deadline=deadline,
        next_run_at=nxt,
    )
    assert created is True
    assert created_again is False
    assert first["id"] == second["id"]
    assert first["idempotency_key"] == job_idempotency_key(
        canonical_entity_key="extra-canonical-0001",
        source="pncp",
        capability="open_tenders",
        window_start=start,
        window_end=end,
        binding_version="v1",
    )
    assert len(store._read_jobs()) == 1


def test_issue_246_single_terminal_transition_and_lease_expiry(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    start, end, deadline, nxt = _window()
    job, _ = store.enqueue(
        entity_id=2,
        canonical_entity_key="extra-canonical-0002",
        source="ciga_dom",
        capability="open_tenders",
        domain_key="ciga.sc.gov.br",
        binding_version="v1",
        window_start=start,
        window_end=end,
        freshness_deadline=deadline,
        next_run_at=nxt,
    )
    claimed = store.claim(worker_id="w1", now=start, lease_seconds=30)
    assert len(claimed) == 1
    assert claimed[0]["attempts"][-1]["run_id"].startswith("crawl-")
    finished = store.finish(job["id"], worker_id="w1", outcome="succeeded", now=start + timedelta(seconds=1))
    assert finished is True
    again = store.finish(job["id"], worker_id="w1", outcome="failed", now=start + timedelta(seconds=2))
    assert again is False
    assert store.inspect(job["id"])["status"] == "succeeded"

    other, _ = store.enqueue(
        entity_id=3,
        canonical_entity_key="extra-canonical-0003",
        source="sc_compras",
        capability="open_tenders",
        domain_key="compras.sc.gov.br",
        binding_version="v1",
        window_start=start,
        window_end=end,
        freshness_deadline=deadline,
        next_run_at=nxt,
        max_attempts=2,
    )
    store.claim(worker_id="w2", now=start, lease_seconds=1)
    expired = store.expire_leases(now=start + timedelta(seconds=5))
    assert expired == 1
    recovered = store.inspect(other["id"])
    assert recovered is not None
    assert recovered["status"] == "queued"
    assert recovered["attempts"][-1]["status"] == "lease_expired"
    assert recovered["attempts"][-1]["error_class"] == "LEASE_EXPIRED"


def test_issue_246_launch_spine_is_idempotent_across_runs(tmp_path: Path) -> None:
    first = launch_spine(tmp_path)
    second = launch_spine(tmp_path)
    assert first["ok"] is True
    assert second["ok"] is True
    assert first["created"] is True
    assert second["created"] is False
    assert first["job_id"] == second["job_id"]
    assert first["raw_pointer"]
    assert first["error_fingerprint"]
    assert first["error_class"] == "AUTH_BLOCKED"
    assert first["document_version_id"]
    assert second["document_version_id"] == first["document_version_id"]
    assert second["raw_sha256"] == first["raw_sha256"]


def test_issue_246_non_billable_pair_cannot_create_job(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    start, end, deadline, nxt = _window()
    with pytest.raises(ValueError, match="non-billable"):
        store.enqueue(
            entity_id=4,
            canonical_entity_key="extra-canonical-0004",
            source="pncp",
            capability="open_tenders",
            domain_key="pncp.gov.br",
            binding_version="v1",
            window_start=start,
            window_end=end,
            freshness_deadline=deadline,
            next_run_at=nxt,
            billable=False,
        )
