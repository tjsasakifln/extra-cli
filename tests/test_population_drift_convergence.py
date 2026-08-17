"""Drive the shipped population-drift classifier and limited tail convergence.

No reimplementation, no hardcoded 44515/44517 special case.
"""

from __future__ import annotations

from scripts.contracts_truth import (
    DEFAULT_DRIFT_POLICY,
    DRIFT_CONVERGED,
    DRIFT_NEEDS_RETRY,
    DRIFT_OK,
    DRIFT_RECONCILE,
    DRIFT_SOURCE,
    REASON_CRASH_BEFORE_COMMIT,
    REASON_DUPLICATE_CONFLICT,
    REASON_GROWTH_UNPROVEN,
    REASON_JUMP,
    REASON_MONOTONIC_GROWTH,
    REASON_OSCILLATION,
    REASON_PERSIST_FAIL,
    REASON_REORDER_OMIT,
    REASON_SHRINK,
    REASON_STABLE,
    REASON_TIMEOUT_AFTER,
    REASON_TIMEOUT_BEFORE,
    PaginationReconcile,
    classify_population_drift,
    growth_within_budget,
)
from scripts.crawl.population_convergence import ObservedPage, run_convergence
from scripts.crawl.run_contracts_90d_pilot import evaluate_window_completion


def _items(*ids: str) -> tuple[dict[str, str], ...]:
    return tuple({"numeroControlePNCP": item} for item in ids)


def _page(number: int, total: int, pages: int, *ids: str) -> ObservedPage:
    return ObservedPage(
        page=number,
        total_registros=total,
        total_paginas=pages,
        items=_items(*ids),
    )


def test_policy_is_explicit_and_does_not_hardcode_historic_totals() -> None:
    assert DEFAULT_DRIFT_POLICY.growth_budget_abs == 8
    assert DEFAULT_DRIFT_POLICY.growth_budget_ratio == 0.01
    assert DEFAULT_DRIFT_POLICY.max_passes == 2
    source = __import__("inspect").getsource(classify_population_drift)
    assert "44515" not in source
    assert "44517" not in source
    assert growth_within_budget(10_000, 10_002)
    assert not growth_within_budget(10_000, 10_020)
    assert not growth_within_budget(80, 95)


def test_plus_two_during_crawl_converges_after_tail() -> None:
    first = [_page(1, 10_000, 2, "a", "b"), _page(2, 10_002, 2, "c", "d")]

    def fetch(page: int) -> ObservedPage:
        if page == 2:
            return _page(2, 10_002, 2, "c", "d", "e", "f")
        return _page(1, 10_002, 2, "a", "b")

    report = run_convergence(first, fetch_page=fetch, persisted=6, rejected=0)
    assert report.decision.status == DRIFT_CONVERGED
    assert report.window_complete is True
    assert REASON_MONOTONIC_GROWTH in report.decision.reason_codes
    assert report.tail_pages_fetched >= 1
    assert report.decision.new_ids_seen >= 2


def test_plus_two_without_tail_is_needs_retry_not_success() -> None:
    reconcile = PaginationReconcile()
    reconcile.observe_page(total_registros=10_000, total_paginas=2, items=_items("a"), page=1)
    reconcile.observe_page(total_registros=10_002, total_paginas=2, items=_items("b"), page=2)
    reconcile.record_persisted(2)
    report = reconcile.finish()
    assert report.ok is False
    assert report.status == DRIFT_NEEDS_RETRY
    assert REASON_GROWTH_UNPROVEN in report.reason_codes
    assert report.allows_tail_pass is True


def test_repeated_growth_inside_budget_then_outside() -> None:
    inside = classify_population_drift(
        first_total_registros=20_000,
        last_total_registros=20_004,
        unique_ids=20_000,
        pass_count=1,
    )
    assert inside.status == DRIFT_NEEDS_RETRY
    assert inside.allows_tail_pass is True

    outside = classify_population_drift(
        first_total_registros=20_000,
        last_total_registros=20_040,
        unique_ids=20_000,
        pass_count=1,
    )
    assert outside.status == DRIFT_SOURCE
    assert REASON_JUMP in outside.reason_codes
    assert outside.allows_tail_pass is False
    assert outside.ok is False


def test_repeated_growth_second_pass_still_unproven_hits_pass_limit() -> None:
    decision = classify_population_drift(
        first_total_registros=20_000,
        last_total_registros=20_003,
        unique_ids=20_000,
        pass_count=2,
    )
    assert decision.status == DRIFT_NEEDS_RETRY
    assert decision.allows_tail_pass is False
    assert "convergence_pass_limit" in decision.reason_codes


def test_shrink_is_refused() -> None:
    decision = classify_population_drift(
        first_total_registros=500,
        last_total_registros=498,
        unique_ids=498,
        totals_sequence=(500, 499, 498),
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_SHRINK in decision.reason_codes
    assert decision.ok is False


def test_oscillation_is_refused() -> None:
    decision = classify_population_drift(
        first_total_registros=100,
        last_total_registros=100,
        unique_ids=100,
        totals_sequence=(100, 102, 100),
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_OSCILLATION in decision.reason_codes


def test_duplicate_page_same_ids_is_idempotent() -> None:
    reconcile = PaginationReconcile()
    reconcile.observe_page(total_registros=2, total_paginas=1, items=_items("a", "b"), page=1)
    reconcile.observe_page(total_registros=2, total_paginas=1, items=_items("a", "b"), page=1)
    reconcile.record_persisted(4)
    report = reconcile.finish()
    assert report.status == DRIFT_OK
    assert report.ok is True
    assert report.duplicate_ids == 2


def test_duplicate_page_conflicting_ids_fails() -> None:
    decision = classify_population_drift(
        first_total_registros=2,
        last_total_registros=2,
        unique_ids=3,
        seen_ids=("a", "b", "c"),
        page_id_sequences=((1, ("a", "b")), (1, ("a", "c"))),
        persisted=3,
        fetched=4,
        rejected=0,
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_DUPLICATE_CONFLICT in decision.reason_codes


def test_reordered_page_same_set_is_ok() -> None:
    decision = classify_population_drift(
        first_total_registros=3,
        last_total_registros=3,
        unique_ids=3,
        seen_ids=("a", "b", "c"),
        page_id_sequences=((1, ("a", "b", "c")), (1, ("c", "b", "a"))),
        persisted=6,
        fetched=6,
        rejected=0,
    )
    assert decision.status == DRIFT_OK
    assert REASON_REORDER_OMIT not in decision.reason_codes


def test_reordered_page_that_omits_id_fails() -> None:
    decision = classify_population_drift(
        first_total_registros=3,
        last_total_registros=3,
        unique_ids=2,
        seen_ids=("a", "c"),
        page_id_sequences=((1, ("a", "b", "c")), (1, ("c", "a"))),
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_REORDER_OMIT in decision.reason_codes


def test_new_item_on_tail_is_proven() -> None:
    first = [_page(1, 8_000, 2, "1", "2"), _page(2, 8_001, 2, "3", "4")]

    def fetch(page: int) -> ObservedPage:
        if page == 2:
            return _page(2, 8_001, 2, "3", "4", "5")
        return _page(1, 8_001, 2, "1", "2")

    report = run_convergence(first, fetch_page=fetch, persisted=5)
    assert report.decision.status == DRIFT_CONVERGED
    assert report.pagination.unique_ids >= 5
    assert report.window_complete is True


def test_timeout_before_checkpoint_is_refused() -> None:
    decision = classify_population_drift(
        first_total_registros=10,
        last_total_registros=10,
        unique_ids=4,
        timeout=True,
        checkpoint_committed=False,
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_TIMEOUT_BEFORE in decision.reason_codes
    assert decision.ok is False


def test_timeout_after_checkpoint_is_needs_retry() -> None:
    decision = classify_population_drift(
        first_total_registros=10,
        last_total_registros=10,
        unique_ids=10,
        timeout=True,
        checkpoint_committed=True,
        state_committed=False,
        persisted=10,
        fetched=10,
    )
    assert decision.status == DRIFT_NEEDS_RETRY
    assert REASON_TIMEOUT_AFTER in decision.reason_codes
    assert decision.ok is False


def test_replay_same_snapshot_is_deterministic_and_not_duplicative() -> None:
    pages = (_page(1, 3, 1, "x", "y", "z"),)
    first = run_convergence(pages, persisted=3)
    second = run_convergence(pages, persisted=3)
    assert first.decision.to_dict() == second.decision.to_dict()
    assert first.decision.status == DRIFT_OK
    reconcile = PaginationReconcile()
    reconcile.observe_page(total_registros=3, total_paginas=1, items=_items("x", "y", "z"), page=1)
    reconcile.observe_page(total_registros=3, total_paginas=1, items=_items("x", "y", "z"), page=1)
    reconcile.record_persisted(6)
    replay = reconcile.finish()
    assert replay.status == DRIFT_OK
    assert replay.unique_ids == 3
    assert replay.duplicate_ids == 3


def test_persistence_failure_never_succeeds() -> None:
    decision = classify_population_drift(
        first_total_registros=8,
        last_total_registros=8,
        unique_ids=8,
        persistence_failed=True,
        persisted=0,
        fetched=8,
    )
    assert decision.status == DRIFT_SOURCE
    assert REASON_PERSIST_FAIL in decision.reason_codes
    assert decision.ok is False


def test_stable_source_is_ok() -> None:
    reconcile = PaginationReconcile()
    reconcile.observe_page(total_registros=2, total_paginas=1, items=_items("a", "b"), page=1)
    reconcile.record_persisted(2)
    report = reconcile.finish()
    assert report.ok is True
    assert report.status == DRIFT_OK
    assert REASON_STABLE in report.reason_codes


def test_crash_after_inserts_before_state_commit_is_not_success() -> None:
    decision = classify_population_drift(
        first_total_registros=12,
        last_total_registros=12,
        unique_ids=12,
        persisted=12,
        fetched=12,
        state_committed=False,
    )
    assert decision.status == DRIFT_NEEDS_RETRY
    assert REASON_CRASH_BEFORE_COMMIT in decision.reason_codes
    assert decision.ok is False


def test_inserts_alone_do_not_mark_success() -> None:
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=2,
        page=2,
        max_pages=10,
        first_total_registros=10_000,
        last_total_registros=10_002,
        persisted=2,
        fetched=2,
    )
    assert fully_ok is False
    assert any("source_population_drift" in err for err in errors)


def test_legacy_80_to_95_still_fails_closed() -> None:
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=2,
        page=2,
        max_pages=10,
        first_total_registros=80,
        last_total_registros=95,
    )
    assert fully_ok is False
    assert any("source_population_drift" in err for err in errors)

    drift = PaginationReconcile()
    drift.observe_page(total_registros=80, total_paginas=8, items=[{"numeroControlePNCP": "1"}])
    drift.observe_page(total_registros=95, total_paginas=10, items=[{"numeroControlePNCP": "2"}])
    drift.record_persisted(2)
    drifted = drift.finish()
    assert drifted.ok is False
    assert drifted.status == DRIFT_SOURCE


def test_fetched_not_equal_persisted_is_reconcile_failed() -> None:
    reconcile = PaginationReconcile()
    reconcile.observe_page(total_registros=2, total_paginas=1, items=_items("a", "b"))
    reconcile.record_persisted(1)
    report = reconcile.finish()
    assert report.ok is False
    assert report.status == DRIFT_RECONCILE


def test_evaluate_converged_window_can_complete() -> None:
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=2,
        page=2,
        max_pages=10,
        first_total_registros=10_000,
        last_total_registros=10_002,
        seen_ids=[f"id-{i}" for i in range(10_000)],
        tail_ids=["new-1", "new-2"],
        unique_ids=10_002,
        pass_count=2,
    )
    assert fully_ok is True
    assert errors == []
