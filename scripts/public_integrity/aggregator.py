"""Pure fail-closed aggregator. NO_MATCH_CONFIRMED requires full coverage + empty."""

from __future__ import annotations

from scripts.public_integrity.dedupe import dedupe_records
from scripts.public_integrity.models import (
    CONTRACTED_SOURCES,
    AggregateDecision,
    IntegrityState,
    SourceRun,
)


def _codes(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for group in groups:
        for item in group:
            if item not in seen:
                seen.append(item)
    return tuple(seen)


def aggregate(source_runs: tuple[SourceRun, ...] | list[SourceRun]) -> AggregateDecision:
    by_id = {run.source_id: run for run in source_runs}
    ordered = tuple(by_id[source_id] for source_id in CONTRACTED_SOURCES if source_id in by_id)
    missing = tuple(source_id for source_id in CONTRACTED_SOURCES if source_id not in by_id)

    extra_reasons: list[str] = ["uncontracted_source_ignored"]
    if missing:
        extra_reasons.extend(["source_unavailable", "coverage_incomplete"])

    records, dedupe_codes = dedupe_records(tuple(record for run in ordered for record in run.records))
    all_present = len(ordered) == len(CONTRACTED_SOURCES)
    all_complete = all_present and all(run.coverage_complete and run.error_class is None for run in ordered)
    any_complete = any(run.coverage_complete and run.error_class is None for run in ordered)
    any_records = bool(records)
    source_reasons = _codes(*(run.reason_codes for run in ordered), tuple(extra_reasons), dedupe_codes)

    state: IntegrityState
    reasons: list[str]
    if all_complete and any_records:
        state = "MATCHES_FOUND"
        reasons = list(source_reasons)
    elif all_complete and not any_records:
        state = "NO_MATCH_CONFIRMED"
        reasons = list(source_reasons) + ["missing_value_not_negative"]
    elif any_complete or any_records:
        state = "PARTIAL"
        reasons = list(source_reasons) + ["coverage_incomplete"]
        if not all_complete:
            reasons.append("pagination_incomplete")
    else:
        state = "UNKNOWN"
        reasons = list(source_reasons) + ["coverage_incomplete"]

    if state == "NO_MATCH_CONFIRMED":
        if not all_complete:
            raise RuntimeError("no_match_without_full_coverage")
        if any_records:
            raise RuntimeError("no_match_with_records")

    return AggregateDecision(
        aggregate_state=state,
        reason_codes=_codes(tuple(reasons)),
        records=records,
        sources=ordered,
    )
