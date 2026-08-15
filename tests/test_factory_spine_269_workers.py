"""Refs #269 — concurrent workers with lease, heartbeat and backpressure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.crawl.worker import AdmissionLimits, admission_blockers
from scripts.factory_spine.contracts import DEFAULT_SOURCES, RankedJob, rank_claim_candidates
from scripts.factory_spine.store import FactoryStore


def test_issue_269_two_workers_do_not_claim_the_same_job(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    store.enqueue(
        entity_id=1,
        canonical_entity_key="extra-canonical-0001",
        source="pncp",
        capability="open_tenders",
        domain_key="pncp.gov.br",
        binding_version="v1",
        window_start=now,
        window_end=now + timedelta(hours=24),
        freshness_deadline=now + timedelta(hours=24),
        next_run_at=now,
        domain_concurrency_limit=1,
    )
    first = store.claim(worker_id="w-a", now=now, lease_seconds=60)
    second = store.claim(worker_id="w-b", now=now, lease_seconds=60)
    assert len(first) == 1
    assert second == []
    assert store.heartbeat(first[0]["id"], worker_id="w-a", cursor={"page": 2}, now=now + timedelta(seconds=5))
    assert store.heartbeat(first[0]["id"], worker_id="w-b", now=now + timedelta(seconds=6)) is False
    interrupted = store.finish(
        first[0]["id"],
        worker_id="w-a",
        outcome="interrupted",
        cursor={"page": 2},
        now=now + timedelta(seconds=7),
    )
    assert interrupted is True
    recovered = store.inspect(first[0]["id"])
    assert recovered is not None
    assert recovered["status"] == "queued"
    assert recovered["cursor"]["page"] == 2
    assert recovered["last_outcome"] == "interrupted"


def test_issue_269_backpressure_blocks_admission() -> None:
    blockers = admission_blockers(
        AdmissionLimits(max_load_per_cpu=0.9),
        load_average=8.0,
        cpu_count=4,
        memory_ratio=0.5,
        disk_ratio=0.5,
    )
    assert blockers == ["cpu_pressure"]


def test_issue_269_4372_pairs_have_no_domain_starvation() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    jobs: list[RankedJob] = []
    job_id = 1
    for entity in range(1, 1094):
        for source in DEFAULT_SOURCES:
            jobs.append(
                RankedJob(
                    id=job_id,
                    domain_key=source,
                    priority=0,
                    freshness_deadline=now + timedelta(hours=entity),
                    next_run_at=now,
                    status="queued",
                    domain_concurrency_limit=1,
                )
            )
            job_id += 1
    assert len(jobs) == 4372
    remaining = {job.id: job for job in jobs}
    claimed_ids: list[int] = []
    seen_domains: set[str] = set()
    while remaining:
        batch = rank_claim_candidates(list(remaining.values()), now=now, limit=4)
        assert batch, "queued jobs remained but ranking returned none"
        domains = [job.domain_key for job in batch]
        assert len(domains) == len(set(domains))
        seen_domains.update(domains)
        for job in batch:
            claimed_ids.append(job.id)
            del remaining[job.id]
    assert len(claimed_ids) == 4372
    assert len(set(claimed_ids)) == 4372
    assert seen_domains == set(DEFAULT_SOURCES)
