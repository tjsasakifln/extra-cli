"""Adversarial coverage for multi-source budget ceiling and entity×source state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.process_documents.collect import (
    aggregate_multi_source_result,
    collect_entity,
    record_entity_visits,
)
from scripts.process_documents.entity_queue import (
    EntityQueueEntry,
    SourceQueueEntry,
    _migrate_legacy_visits,
    apply_multi_source_attempt,
    drain_decision,
    load_entity_queue,
    save_entity_queue,
    select_batch_by_source_lag,
)
from scripts.process_documents.source_budget import allocate_source_budgets
from scripts.process_documents.statuses import DocumentRunStatus


def test_three_sources_sum_budgets_le_entity_max():
    sources = ["pncp", "ciga_ckan", "sc_compras"]
    for max_p in (1, 2, 3, 5, 10, 11, 30):
        alloc = allocate_source_budgets(sources, max_processes=max_p)
        assert alloc["sum_budgets"] <= max_p
        assert sum(alloc["budgets"].values()) == alloc["sum_budgets"]
        assert set(alloc["budgets"]) == set(sources)
        for s, b in alloc["budgets"].items():
            assert b >= 0
        # sources with 0 are not_queried_budget
        for s in alloc["not_queried_budget"]:
            assert alloc["budgets"][s] == 0


def test_per_source_caps_do_not_exceed_global():
    alloc = allocate_source_budgets(
        ["pncp", "ciga_ckan", "sc_compras"],
        max_processes=10,
        per_source_caps={"pncp": 2, "ciga_ckan": 2, "sc_compras": 2},
    )
    assert alloc["sum_budgets"] <= 10
    assert alloc["budgets"]["pncp"] <= 2
    assert alloc["budgets"]["ciga_ckan"] <= 2
    assert alloc["budgets"]["sc_compras"] <= 2


def test_aggregate_success_plus_timeout_is_partial():
    sources = ["pncp", "ciga_ckan"]
    results = [
        {
            "source_id": "pncp",
            "status": DocumentRunStatus.SUCCESS_NONZERO.value,
            "documents_downloaded": 2,
            "documents": [{"id": 1}, {"id": 2}],
        },
        {
            "source_id": "ciga_ckan",
            "status": DocumentRunStatus.TIMEOUT.value,
            "errors": ["timeout"],
            "documents": [],
        },
    ]
    merged = aggregate_multi_source_result("ent-1", sources, results)
    assert merged["status"] == DocumentRunStatus.PARTIAL.value
    assert merged["source_results"]["pncp"]["status"] == DocumentRunStatus.SUCCESS_NONZERO.value
    assert merged["source_results"]["ciga_ckan"]["status"] == DocumentRunStatus.TIMEOUT.value


def test_success_zero_scope_incomplete_not_full_success():
    sources = ["pncp"]
    results = [
        {
            "source_id": "pncp",
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "scope_complete": False,
            "documents": [],
        }
    ]
    merged = aggregate_multi_source_result("ent-1", sources, results)
    assert merged["status"] == DocumentRunStatus.PARTIAL.value


def test_success_nonzero_requires_all_consulted_sources():
    sources = ["pncp", "sc_compras"]
    results = [
        {"source_id": "pncp", "status": DocumentRunStatus.SUCCESS_NONZERO.value, "documents": [1]},
        {"source_id": "sc_compras", "status": DocumentRunStatus.SUCCESS_NONZERO.value, "documents": [2]},
    ]
    merged = aggregate_multi_source_result("ent-1", sources, results)
    assert merged["status"] == DocumentRunStatus.SUCCESS_NONZERO.value


def test_not_queried_budget_never_counts_as_zero():
    sources = ["pncp", "ciga_ckan", "sc_compras"]
    results = [
        {"source_id": "pncp", "status": DocumentRunStatus.SUCCESS_NONZERO.value, "documents": [1]},
        {"source_id": "ciga_ckan", "status": DocumentRunStatus.NOT_QUERIED_BUDGET.value},
        {"source_id": "sc_compras", "status": DocumentRunStatus.NOT_QUERIED_BUDGET.value},
    ]
    merged = aggregate_multi_source_result("ent-1", sources, results)
    assert DocumentRunStatus.SUCCESS_ZERO.value not in (
        merged["source_results"]["ciga_ckan"]["status"],
        merged["source_results"]["sc_compras"]["status"],
    )
    assert "ciga_ckan" in merged["sources_not_queried_budget"]
    # only pncp consulted successfully → aggregate SUCCESS_NONZERO among consulted
    assert merged["status"] == DocumentRunStatus.SUCCESS_NONZERO.value


def test_source_success_does_not_clear_sibling_failure_lag():
    e = EntityQueueEntry(canonical_id="e1")
    t0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    e = apply_multi_source_attempt(
        e,
        source_results={
            "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
            "ciga_ckan": {"status": DocumentRunStatus.TIMEOUT.value, "errors": ["t"]},
        },
        attempted_at=t0,
        aggregate_status=DocumentRunStatus.PARTIAL.value,
    )
    assert e.sources_state["pncp"].last_success_at is not None
    assert e.sources_state["ciga_ckan"].last_success_at is None
    assert e.sources_state["ciga_ckan"].consecutive_failures >= 1
    assert e.last_success_at is None  # entity lag remains
    # second run: only healthy source would not clear ciga lag
    e = apply_multi_source_attempt(
        e,
        source_results={
            "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
            "ciga_ckan": {"status": DocumentRunStatus.TIMEOUT.value},
        },
        attempted_at=t0 + timedelta(hours=1),
        aggregate_status=DocumentRunStatus.PARTIAL.value,
    )
    assert e.sources_state["ciga_ckan"].last_success_at is None
    assert e.sources_state["ciga_ckan"].consecutive_failures >= 2


def test_queue_restart_preserves_entity_source_state(tmp_path: Path):
    e = EntityQueueEntry(canonical_id="e1")
    apply_multi_source_attempt(
        e,
        source_results={
            "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
            "sc_compras": {"status": DocumentRunStatus.TIMEOUT.value},
        },
        aggregate_status=DocumentRunStatus.PARTIAL.value,
    )
    save_entity_queue({"e1": e}, meta_root=tmp_path)
    q2 = load_entity_queue(meta_root=tmp_path)
    assert "pncp" in q2["e1"].sources_state
    assert q2["e1"].sources_state["pncp"].last_success_at is not None
    assert q2["e1"].sources_state["sc_compras"].last_success_at is None


def test_legacy_checkpoint_migration(tmp_path: Path):
    leg = tmp_path / "checkpoints"
    leg.mkdir(parents=True)
    path = leg / "incremental_visits.json"
    path.write_text(
        '{"entities": {"e1": {"last_visited_at": "2026-07-01T00:00:00+00:00", '
        '"last_status": "SUCCESS_ZERO", "sources": ["pncp"]}}}',
        encoding="utf-8",
    )
    out = _migrate_legacy_visits(path)
    assert "e1" in out
    assert out["e1"].last_attempt_at is not None
    # success only if status was valid success
    assert out["e1"].last_success_at is not None


def test_two_runs_select_distinct_batches_by_source_lag():
    now = datetime(2026, 8, 1, tzinfo=UTC)

    class _E:
        def __init__(self, cid: str) -> None:
            self.canonical_id = cid
            self.razao_social = cid

    targets = [_E("a"), _E("b")]
    queue = {
        "a": EntityQueueEntry(
            canonical_id="a",
            sources_state={
                "pncp": SourceQueueEntry(
                    canonical_id="a",
                    source_id="pncp",
                    last_success_at=(now - timedelta(hours=1)).isoformat(),
                )
            },
        ),
        "b": EntityQueueEntry(
            canonical_id="b",
            sources_state={
                "pncp": SourceQueueEntry(
                    canonical_id="b",
                    source_id="pncp",
                    last_success_at=None,
                )
            },
        ),
    }
    batch1 = select_batch_by_source_lag(targets, queue, limit=1, now=now)  # type: ignore[arg-type]
    assert batch1[0].canonical_id == "b"  # never succeeded first
    queue["b"].sources_state["pncp"].last_success_at = now.isoformat()
    queue["a"].sources_state["pncp"].last_success_at = (now - timedelta(hours=48)).isoformat()
    batch2 = select_batch_by_source_lag(targets, queue, limit=1, now=now)  # type: ignore[arg-type]
    assert batch2[0].canonical_id == "a"


def test_drain_wall_time_and_capacity():
    stop, reason = drain_decision(
        overdue_remaining=5,
        batches_done=1,
        entities_done=10,
        max_batches=1,
        max_entities=100,
        wall_seconds=1.0,
        max_wall_seconds=3600,
    )
    assert stop is True
    assert reason == "PARTIAL_CAPACITY_EXHAUSTED"

    stop2, reason2 = drain_decision(
        overdue_remaining=5,
        batches_done=0,
        entities_done=0,
        max_batches=10,
        max_entities=100,
        wall_seconds=100.0,
        max_wall_seconds=10.0,
    )
    assert stop2 is True
    assert reason2 == "PARTIAL_CAPACITY_EXHAUSTED"

    cont, r = drain_decision(
        overdue_remaining=5,
        batches_done=0,
        entities_done=0,
        max_batches=10,
        max_entities=100,
        wall_seconds=1.0,
        max_wall_seconds=10.0,
    )
    assert cont is False
    assert r == "continue"


def test_healthy_source_does_not_mask_stale_source_in_queue(tmp_path: Path):
    """After mixed result, stale source remains overdue while healthy is not."""
    e = EntityQueueEntry(canonical_id="e1")
    t0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    apply_multi_source_attempt(
        e,
        source_results={
            "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
            "ciga_ckan": {"status": DocumentRunStatus.TIMEOUT.value},
        },
        attempted_at=t0,
        aggregate_status=DocumentRunStatus.PARTIAL.value,
    )
    save_entity_queue({"e1": e}, meta_root=tmp_path)
    # record_entity_visits path
    record_entity_visits(
        ["e1"],
        statuses={"e1": DocumentRunStatus.PARTIAL.value},
        sources_by_entity={"e1": ["pncp", "ciga_ckan"]},
        results_by_entity={
            "e1": {
                "status": DocumentRunStatus.PARTIAL.value,
                "source_results": {
                    "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
                    "ciga_ckan": {"status": DocumentRunStatus.TIMEOUT.value},
                },
            }
        },
        meta_root=tmp_path,
        visited_at=(t0 + timedelta(hours=2)).isoformat(),
    )
    q = load_entity_queue(meta_root=tmp_path)
    assert q["e1"].sources_state["ciga_ckan"].last_success_at is None
    assert q["e1"].sources_state["pncp"].last_success_at is not None


def test_idempotent_after_crash_between_collect_and_persist(tmp_path: Path):
    """Re-applying the same multi-source result does not invent extra successes."""
    e = EntityQueueEntry(canonical_id="e1")
    payload = {
        "pncp": {"status": DocumentRunStatus.SUCCESS_NONZERO.value},
        "ciga_ckan": {"status": DocumentRunStatus.TIMEOUT.value},
    }
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    apply_multi_source_attempt(e, source_results=payload, attempted_at=t0, aggregate_status="partial")
    # crash before save — re-apply same
    e2 = EntityQueueEntry(canonical_id="e1")
    apply_multi_source_attempt(e2, source_results=payload, attempted_at=t0, aggregate_status="partial")
    assert e2.sources_state["pncp"].last_success_at is not None
    assert e2.sources_state["ciga_ckan"].last_success_at is None
    save_entity_queue({"e1": e2}, meta_root=tmp_path)
    # second persist same payload
    record_entity_visits(
        ["e1"],
        statuses={"e1": "partial"},
        results_by_entity={"e1": {"status": "partial", "source_results": payload}},
        meta_root=tmp_path,
        visited_at=t0.isoformat(),
    )
    q = load_entity_queue(meta_root=tmp_path)
    assert q["e1"].sources_state["ciga_ckan"].last_success_at is None


def test_collect_entity_budget_allocation_with_stubs(monkeypatch):
    """Three applicable sources; budgets sum <= max_processes; zero-budget is NOT_QUERIED_BUDGET."""
    from scripts.process_documents import collect as col

    class FakeEnt:
        canonical_id = "ent-x"
        platforms = ["pncp", "ciga_ckan", "sc_compras"]
        access_status = "collected"
        activity_status = "active"

    class FakeAdapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def collect(self, entity, **kwargs):
            return {
                "source_id": self.name,
                "portal_family": self.name,
                "status": DocumentRunStatus.SUCCESS_NONZERO.value,
                "documents": [{"x": 1}],
                "documents_downloaded": 1,
                "documents_unchanged": 0,
                "documents_failed": 0,
                "processes_seen": int(kwargs.get("max_processes") or 0),
                "max_processes_received": int(kwargs.get("max_processes") or 0),
            }

    monkeypatch.setattr(col, "resolve_applicable_sources", lambda e, prefer_pncp=True: ["pncp", "ciga_ckan", "sc_compras"])
    monkeypatch.setattr(col, "get_adapter", lambda family: FakeAdapter(family))

    # max_processes=2 across 3 sources → some get 0 or 1, sum <= 2
    out = collect_entity(FakeEnt(), max_processes=2, download=False, multi_source=True)  # type: ignore[arg-type]
    assert isinstance(out, dict)
    alloc = out["budget_allocation"]
    assert alloc["sum_budgets"] <= 2
    assert sum(alloc["budgets"].values()) <= 2
    # budgets granted to adapters match
    for src, rd in out["source_results"].items():
        b = alloc["budgets"][src]
        if b == 0:
            assert rd["status"] == DocumentRunStatus.NOT_QUERIED_BUDGET.value
        else:
            assert rd.get("max_processes_budget") == b
            assert rd.get("processes_seen") == b
