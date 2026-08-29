"""Reconcile expected vs observed. Stock coverage is not freshness coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.national_coverage.hashing import content_hash
from scripts.national_coverage.models import (
    DEFAULT_FRESHNESS_WINDOW_HOURS,
    SCHEMA_VERSION,
    CorpusSnapshot,
    CoverageRecord,
    CoverageRequest,
    FreshnessCoverage,
    MappingStats,
    PartitionState,
    StockCoverage,
    VersionedUniverse,
)
from scripts.national_coverage.partitions import count_by_status, expected_queried_closed
from scripts.national_coverage.verdict import decide_verdict


def _parse_as_of(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def measure_freshness(
    *,
    mapping: MappingStats,
    as_of: str,
    window_hours: float,
) -> FreshnessCoverage:
    cutoff = _parse_as_of(as_of)
    window = timedelta(hours=window_hours)
    fresh = stale = unknown = 0
    for record in mapping.records:
        if record.status not in {"MAPPED", "ALIAS"}:
            continue
        if not record.last_seen or cutoff is None:
            unknown += 1
            continue
        last = _parse_as_of(record.last_seen)
        if last is None:
            unknown += 1
            continue
        if cutoff - last <= window:
            fresh += 1
        else:
            stale += 1
    return FreshnessCoverage(
        window_hours=window_hours,
        as_of=as_of,
        fresh_found=fresh,
        stale_found=stale,
        unknown_freshness=unknown,
    )


def reconcile(
    *,
    universe: VersionedUniverse,
    partitions: tuple[PartitionState, ...],
    corpus: CorpusSnapshot | None,
    mapping: MappingStats,
    request: CoverageRequest,
    freshness_window_hours: float = DEFAULT_FRESHNESS_WINDOW_HOURS,
    freshness_as_of: str | None = None,
    measured: bool = True,
) -> CoverageRecord:
    expected, queried, closed = expected_queried_closed(partitions)
    by_status = count_by_status(partitions)
    observed_found = by_status.get("FOUND", 0)
    stock = StockCoverage(
        expected=expected,
        observed_found=observed_found,
        unobserved=max(expected - observed_found, 0),
    )
    freshness = measure_freshness(
        mapping=mapping,
        as_of=freshness_as_of or (corpus.as_of if corpus else universe.as_of),
        window_hours=freshness_window_hours,
    )
    verdict, authorized, reasons = decide_verdict(
        universe=universe,
        partitions=partitions,
        request=request,
        measured=measured,
    )
    identity_issues = mapping.unmapped + mapping.duplicate + mapping.conflict
    if authorized and identity_issues > 0:
        authorized = False
        verdict = "PARTIAL"
        reasons = tuple([*reasons, "unresolved_publisher_identities", f"unresolved_identity_count:{identity_issues}"])
    if authorized and freshness.stale_found > 0:
        authorized = False
        verdict = "PARTIAL"
        reasons = tuple([*reasons, "stale_universe"])
    source_cutoff = _parse_as_of(universe.cutoff)
    freshness_cutoff = _parse_as_of(freshness.as_of)
    if (
        authorized
        and source_cutoff is not None
        and freshness_cutoff is not None
        and freshness_cutoff - source_cutoff > timedelta(hours=freshness.window_hours)
    ):
        authorized = False
        verdict = "PARTIAL"
        reasons = tuple([*reasons, "source_cutoff_stale"])
    seed = {
        "schema_version": SCHEMA_VERSION,
        "national_universe_id": universe.national_universe_id,
        "catalog_hash": universe.catalog_hash,
        "raw_hash": universe.raw_hash,
        "universe_kind": universe.universe_kind,
        "official_status": universe.official_status,
        "expected": expected,
        "queried": queried,
        "closed": closed,
        "by_status": by_status,
        "verdict": verdict,
        "national_claim_authorized": authorized,
        "reason_codes": list(reasons),
        "request": {
            "geography": request.geography,
            "period": request.period,
            "source": request.source,
            "grain": request.grain,
        },
        "mapping": {
            "mapped": mapping.mapped,
            "unmapped": mapping.unmapped,
            "duplicate": mapping.duplicate,
            "conflict": mapping.conflict,
        },
        "stock": {
            "expected": stock.expected,
            "observed_found": stock.observed_found,
            "unobserved": stock.unobserved,
        },
        "freshness": {
            "window_hours": freshness.window_hours,
            "fresh_found": freshness.fresh_found,
            "stale_found": freshness.stale_found,
            "unknown_freshness": freshness.unknown_freshness,
        },
        "corpus_hash": corpus.snapshot_hash if corpus else None,
    }
    return CoverageRecord(
        schema_version=SCHEMA_VERSION,
        universe=universe,
        partitions=partitions,
        expected_count=expected,
        queried_count=queried,
        closed_count=closed,
        by_status=by_status,
        corpus=corpus,
        mapping=mapping,
        stock=stock,
        freshness=freshness,
        verdict=verdict,
        national_claim_authorized=authorized,
        reason_codes=reasons,
        request=request,
        content_hash=content_hash(seed),
    )
