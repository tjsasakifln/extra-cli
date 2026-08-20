"""Orchestrate CEIS + CNEP adapters into a fail-closed private payload."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from scripts.public_integrity.aggregator import aggregate
from scripts.public_integrity.cache import CacheLookup, IntegrityCache
from scripts.public_integrity.ceis import run_ceis
from scripts.public_integrity.clock import expires_at, iso, parse_clock
from scripts.public_integrity.cnep import run_cnep
from scripts.public_integrity.cnpj import is_valid_cnpj, normalize_cnpj
from scripts.public_integrity.hashing import attach_hash, digest
from scripts.public_integrity.models import (
    CONTRACTED_SOURCES,
    DEFAULT_LIMITATIONS,
    DEFAULT_TTL_SECONDS,
    FRESHNESS_POLICY,
    MAX_PAGES,
    MAX_RETRIES,
    PRODUCER_VERSION,
    SCHEMA_VERSION,
    SOURCE_SPECS,
    IntegrityState,
    SourceRun,
)
from scripts.public_integrity.redaction import install_log_redaction
from scripts.public_integrity.transport import Transport

LOGGER = install_log_redaction()


def _query_id(queried_cnpj: str, as_of: str) -> str:
    return (
        "pri1-"
        + digest(
            {
                "schema": SCHEMA_VERSION,
                "queried_cnpj": queried_cnpj,
                "as_of": as_of,
                "sources": list(CONTRACTED_SOURCES),
            }
        )[:16]
    )


def unused_source(source_id: str, *, captured_at: str, reasons: tuple[str, ...]) -> SourceRun:
    spec = SOURCE_SPECS[source_id]
    return SourceRun(
        source_id=source_id,
        official_url=spec["official_url"],
        api_url=spec["api_url"],
        authority=spec["authority"],
        status="UNKNOWN",
        pages_expected=None,
        pages_fetched=0,
        coverage_complete=False,
        raw_count=0,
        normalized_count=0,
        deduped_count=0,
        reason_codes=reasons,
        as_of=captured_at,
        error_class=reasons[0] if reasons else "source_unavailable",
        attempts=0,
        records=(),
    )


def _freshness(*, is_current: bool, status: str, ttl_seconds: int) -> dict[str, Any]:
    return {
        "policy": FRESHNESS_POLICY,
        "ttl_seconds": ttl_seconds,
        "status": status,
        "is_current": is_current,
    }


def _payload(
    *,
    queried_cnpj: str,
    checked_at: str,
    as_of: str,
    expires: str,
    freshness: dict[str, Any],
    aggregate_state: IntegrityState,
    sources: dict[str, Any],
    records: list[dict[str, Any]],
    limitations: list[str],
    reason_codes: list[str],
) -> dict[str, Any]:
    body = {
        "schema": SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
        "query_id": _query_id(queried_cnpj, as_of),
        "queried_cnpj": queried_cnpj,
        "checked_at": checked_at,
        "as_of": as_of,
        "expires_at": expires,
        "freshness": freshness,
        "aggregate_state": aggregate_state,
        "sources": sources,
        "records": records,
        "limitations": limitations,
        "reason_codes": reason_codes,
        "not_legal_conclusion": True,
        "producer_version": PRODUCER_VERSION,
        "contracted_sources": list(CONTRACTED_SOURCES),
    }
    return attach_hash(body)


def produce(
    queried_cnpj: str,
    *,
    transport: Transport,
    clock: datetime | str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    cache: IntegrityCache | None = None,
    cache_lookup: CacheLookup | None = None,
    max_retries: int = MAX_RETRIES,
    max_pages: int = MAX_PAGES,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Run contracted sources and return a private public-read-integrity/1.0 payload."""
    moment = parse_clock(clock)
    checked = iso(moment)
    expires = iso(expires_at(moment, ttl_seconds))
    LOGGER.info("public-read-integrity query started cnpj=%s", queried_cnpj)

    normalized = normalize_cnpj(queried_cnpj)
    if normalized is None:
        reasons = ("invalid_cnpj", "coverage_incomplete")
        runs = (
            unused_source("CEIS", captured_at=checked, reasons=reasons),
            unused_source("CNEP", captured_at=checked, reasons=reasons),
        )
        decision = aggregate(runs)
        digits = "".join(ch for ch in queried_cnpj if ch.isdigit())
        private_cnpj = digits if len(digits) == 14 else ("0" * 14)
        return _payload(
            queried_cnpj=private_cnpj,
            checked_at=checked,
            as_of=checked,
            expires=expires,
            freshness=_freshness(is_current=False, status="expired", ttl_seconds=ttl_seconds),
            aggregate_state="UNKNOWN",
            sources={run.source_id: run.as_source_dict() for run in runs},
            records=[],
            limitations=list(DEFAULT_LIMITATIONS),
            reason_codes=list(decision.reason_codes) + list(reasons),
        )

    stale_reasons: list[str] = []
    freshness_status = "current"
    is_current = True
    lookup = cache_lookup
    if cache is not None and lookup is None:
        lookup = cache.get(normalized, now=moment)
    if lookup is not None and lookup.hit and lookup.expired:
        stale_reasons.extend(["cache_expired", "stale_cache", "not_current"])
        freshness_status = "expired"
        is_current = False
    elif lookup is not None and lookup.hit and not lookup.expired:
        freshness_status = "current"
        is_current = True

    ceis = run_ceis(
        normalized,
        transport,
        captured_at=checked,
        max_retries=max_retries,
        max_pages=max_pages,
        sleeper=sleeper,
    )
    cnep = run_cnep(
        normalized,
        transport,
        captured_at=checked,
        max_retries=max_retries,
        max_pages=max_pages,
        sleeper=sleeper,
    )
    decision = aggregate((ceis, cnep))
    all_complete = (
        ceis.coverage_complete and cnep.coverage_complete and ceis.error_class is None and cnep.error_class is None
    )
    if all_complete:
        freshness_status = "current"
        is_current = True
        stale_reasons = []
    elif stale_reasons:
        freshness_status = "expired"
        is_current = False
        if decision.aggregate_state == "NO_MATCH_CONFIRMED":
            raise RuntimeError("expired_cache_must_not_confirm_absence")

    reason_codes = list(dict.fromkeys([*decision.reason_codes, *stale_reasons]))
    payload = _payload(
        queried_cnpj=normalized,
        checked_at=checked,
        as_of=checked,
        expires=expires,
        freshness=_freshness(is_current=is_current, status=freshness_status, ttl_seconds=ttl_seconds),
        aggregate_state=decision.aggregate_state,
        sources={run.source_id: run.as_source_dict() for run in decision.sources},
        records=[record.as_dict() for record in decision.records],
        limitations=list(DEFAULT_LIMITATIONS),
        reason_codes=reason_codes,
    )
    if cache is not None and is_current and all_complete:
        cache.put(normalized, payload, stored_at=moment, expires_at=expires_at(moment, ttl_seconds))
    LOGGER.info(
        "public-read-integrity query finished state=%s coverage_ceis=%s coverage_cnep=%s",
        payload["aggregate_state"],
        ceis.coverage_complete,
        cnep.coverage_complete,
    )
    return payload


def assert_valid_cnpj_or_unknown(value: str) -> bool:
    return is_valid_cnpj(value)
