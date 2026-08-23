"""Limited, observable population-convergence protocol for incremental windows.

The classifier is pure (``scripts.contracts_truth.classify_population_drift``).
This module applies one bounded tail pass over already-observed pages. It is
not a second crawler and never marks success from inserts alone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.contracts_truth import (
    DEFAULT_DRIFT_POLICY,
    DRIFT_CONVERGED,
    DRIFT_NEEDS_RETRY,
    DRIFT_OK,
    DRIFT_RECONCILE,
    DRIFT_SOURCE,
    MAX_CONVERGENCE_PASSES,
    PaginationReconcile,
    PaginationReport,
    PopulationDriftDecision,
    PopulationDriftPolicy,
    classify_population_drift,
)


@dataclass(frozen=True)
class ObservedPage:
    page: int
    total_registros: int | None
    total_paginas: int | None
    items: tuple[Mapping[str, Any], ...]


FetchPage = Callable[[int], ObservedPage | None]


@dataclass
class ConvergenceReport:
    decision: PopulationDriftDecision
    pagination: PaginationReport
    pass_count: int
    tail_pages_fetched: int
    elapsed_seconds: float
    window_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "pagination": self.pagination.to_dict(),
            "pass_count": self.pass_count,
            "tail_pages_fetched": self.tail_pages_fetched,
            "elapsed_seconds": self.elapsed_seconds,
            "window_complete": self.window_complete,
            "reason_codes": list(self.decision.reason_codes),
            "status": self.decision.status,
        }


def observe_pages(
    pages: Iterable[ObservedPage],
    reconcile: PaginationReconcile | None = None,
    *,
    tail: bool = False,
    id_field: str = "numeroControlePNCP",
) -> PaginationReconcile:
    acc = reconcile or PaginationReconcile()
    for page in pages:
        if tail:
            acc.observe_tail_page(
                total_registros=page.total_registros,
                total_paginas=page.total_paginas,
                items=page.items,
                id_field=id_field,
                page=page.page,
            )
        else:
            acc.observe_page(
                total_registros=page.total_registros,
                total_paginas=page.total_paginas,
                items=page.items,
                id_field=id_field,
                page=page.page,
            )
    return acc


def tail_page_numbers(
    *,
    first_total_paginas: int | None,
    last_total_paginas: int | None,
) -> tuple[int, ...]:
    last = int(last_total_paginas or 1)
    first = int(first_total_paginas or last)
    start = max(1, min(first, last))
    end = max(last, first)
    return tuple(range(start, end + 1))


def run_convergence(
    pages: Sequence[ObservedPage],
    *,
    fetch_page: FetchPage | None = None,
    persisted: int = 0,
    rejected: int = 0,
    timeout: bool = False,
    checkpoint_committed: bool = True,
    persistence_failed: bool = False,
    state_committed: bool = True,
    elapsed_seconds: float = 0.0,
    policy: PopulationDriftPolicy = DEFAULT_DRIFT_POLICY,
    id_field: str = "numeroControlePNCP",
    max_passes: int | None = None,
) -> ConvergenceReport:
    """Apply at most one extra tail pass when small monotonic growth is unproven."""
    cap = int(max_passes if max_passes is not None else min(policy.max_passes, MAX_CONVERGENCE_PASSES))
    reconcile = observe_pages(pages, id_field=id_field)
    reconcile.mark_first_pass_complete()
    if persisted:
        reconcile.record_persisted(persisted)
    if rejected:
        reconcile.record_rejected(rejected)

    first_report = reconcile.finish(
        pass_count=1,
        timeout=timeout,
        checkpoint_committed=checkpoint_committed,
        persistence_failed=persistence_failed,
        state_committed=state_committed,
        elapsed_seconds=elapsed_seconds,
        policy=policy,
        reconcile_counts=False,
    )
    tail_fetched = 0
    pass_count = 1
    if (
        first_report.allows_tail_pass
        and fetch_page is not None
        and not timeout
        and not persistence_failed
        and elapsed_seconds <= policy.max_seconds
        and cap >= 2
    ):
        for page_no in tail_page_numbers(
            first_total_paginas=reconcile.first_total_paginas,
            last_total_paginas=reconcile.last_total_paginas,
        ):
            fetched = fetch_page(page_no)
            if fetched is None:
                break
            observe_pages((fetched,), reconcile, tail=True, id_field=id_field)
            tail_fetched += 1
        pass_count = 2

    report = reconcile.finish(
        pass_count=pass_count,
        timeout=timeout,
        checkpoint_committed=checkpoint_committed,
        persistence_failed=persistence_failed,
        state_committed=state_committed,
        elapsed_seconds=elapsed_seconds,
        policy=policy,
        reconcile_counts=False,
    )
    decision = classify_population_drift(
        first_total_registros=reconcile.first_total_registros,
        last_total_registros=reconcile.last_total_registros,
        first_total_paginas=reconcile.first_total_paginas,
        last_total_paginas=reconcile.last_total_paginas,
        unique_ids=report.unique_ids,
        seen_ids=reconcile.seen_ids - reconcile.tail_ids,
        tail_ids=reconcile.tail_ids,
        totals_sequence=reconcile.totals_sequence,
        page_id_sequences=reconcile.page_id_sequences,
        pass_count=pass_count,
        persisted=None,
        fetched=None,
        rejected=0,
        timeout=timeout,
        checkpoint_committed=checkpoint_committed,
        persistence_failed=persistence_failed,
        state_committed=state_committed,
        elapsed_seconds=elapsed_seconds,
        policy=policy,
    )
    complete = decision.ok and report.ok and not timeout and not persistence_failed and state_committed
    return ConvergenceReport(
        decision=decision,
        pagination=report,
        pass_count=pass_count,
        tail_pages_fetched=tail_fetched,
        elapsed_seconds=elapsed_seconds,
        window_complete=complete,
    )


def format_window_error(decision: PopulationDriftDecision) -> str:
    first = decision.first_total_registros
    last = decision.last_total_registros
    codes = ",".join(decision.reason_codes)
    if decision.status == DRIFT_RECONCILE:
        return f"local_persistence_reconciliation:{codes}:totalRegistros {first} -> {last}"
    return f"source_population_drift:{decision.status}:{codes}:totalRegistros {first} -> {last}"


def classify_window_population(
    *,
    first_total_registros: int | None,
    last_total_registros: int | None,
    **kwargs: Any,
) -> PopulationDriftDecision:
    """Thin shipped wrapper so window completion and tests share one predicate."""
    return classify_population_drift(
        first_total_registros=first_total_registros,
        last_total_registros=last_total_registros,
        **kwargs,
    )


__all__ = [
    "ConvergenceReport",
    "DRIFT_CONVERGED",
    "DRIFT_NEEDS_RETRY",
    "DRIFT_OK",
    "DRIFT_SOURCE",
    "FetchPage",
    "ObservedPage",
    "classify_window_population",
    "format_window_error",
    "observe_pages",
    "run_convergence",
    "tail_page_numbers",
]
