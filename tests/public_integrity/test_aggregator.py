"""Pure aggregator: NO_MATCH_CONFIRMED only with full coverage and empty records."""

from __future__ import annotations

from scripts.public_integrity.aggregator import aggregate
from scripts.public_integrity.models import ObservedRecord, SourceRun


def _run(
    source_id: str,
    *,
    status: str,
    complete: bool,
    records: tuple[ObservedRecord, ...] = (),
    reasons: tuple[str, ...] = (),
    error_class: str | None = None,
    pages_fetched: int = 1,
) -> SourceRun:
    return SourceRun(
        source_id=source_id,
        official_url="https://portaldatransparencia.gov.br/sancoes/" + source_id.lower(),
        api_url="https://api.portaldatransparencia.gov.br/api-de-dados/" + source_id.lower(),
        authority="CGU",
        status=status,  # type: ignore[arg-type]
        pages_expected=pages_fetched if complete else None,
        pages_fetched=pages_fetched,
        coverage_complete=complete,
        raw_count=len(records),
        normalized_count=len(records),
        deduped_count=len(records),
        reason_codes=reasons,
        as_of="2026-08-01T12:00:00+00:00",
        error_class=error_class,
        attempts=1,
        records=records,
    )


def _record(official_id: str = "9001") -> ObservedRecord:
    return ObservedRecord(
        source_id="CEIS",
        official_id=official_id,
        record_type="Impedimento de licitar e contratar",
        authority="Orgao",
        start_date="2024-03-01",
        end_date=None,
        observed_status="Impedimento de licitar e contratar",
        source_url="https://portaldatransparencia.gov.br/sancoes/ceis",
        captured_at="2026-08-01T12:00:00+00:00",
        original={"id": official_id},
    )


def test_both_complete_empty_is_no_match() -> None:
    decision = aggregate(
        (
            _run("CEIS", status="NO_MATCH_CONFIRMED", complete=True),
            _run("CNEP", status="NO_MATCH_CONFIRMED", complete=True),
        )
    )
    assert decision.aggregate_state == "NO_MATCH_CONFIRMED"
    assert decision.records == ()


def test_timeout_never_no_match() -> None:
    decision = aggregate(
        (
            _run("CEIS", status="UNKNOWN", complete=False, reasons=("timeout",), error_class="timeout"),
            _run("CNEP", status="NO_MATCH_CONFIRMED", complete=True),
        )
    )
    assert decision.aggregate_state != "NO_MATCH_CONFIRMED"
    assert decision.aggregate_state in {"PARTIAL", "UNKNOWN"}


def test_matches_from_one_source_survive_degraded_peer() -> None:
    decision = aggregate(
        (
            _run("CEIS", status="MATCHES_FOUND", complete=True, records=(_record(),)),
            _run("CNEP", status="UNKNOWN", complete=False, reasons=("timeout",), error_class="timeout"),
        )
    )
    assert decision.aggregate_state == "PARTIAL"
    assert decision.records
    assert decision.records[0].official_id == "9001"
