"""Shared pagination-complete runner. Adapters stay source-specific at parse."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.public_integrity.dedupe import dedupe_records
from scripts.public_integrity.models import (
    MAX_PAGES,
    MAX_RETRIES,
    SOURCE_SPECS,
    IntegrityState,
    ObservedRecord,
    SourceRun,
    TransportResponse,
)
from scripts.public_integrity.normalize import normalize_record
from scripts.public_integrity.retry import fetch_with_retry
from scripts.public_integrity.transport import Transport


def _as_page_list(body: Any) -> tuple[list[Any] | None, str | None]:
    if body is None:
        return None, "schema_drift"
    if isinstance(body, list):
        return body, None
    if isinstance(body, dict):
        for key in ("data", "registros", "items"):
            nested = body.get(key)
            if isinstance(nested, list):
                return nested, None
        return None, "schema_drift"
    return None, "schema_drift"


def _source_status(
    *, coverage_complete: bool, records: tuple[ObservedRecord, ...], reasons: tuple[str, ...]
) -> IntegrityState:
    if coverage_complete and records:
        return "MATCHES_FOUND"
    if coverage_complete and not records:
        return "NO_MATCH_CONFIRMED"
    if records:
        return "PARTIAL"
    if reasons:
        return "UNKNOWN"
    return "UNKNOWN"


def run_cadastro(
    source_id: str,
    queried_cnpj: str,
    transport: Transport,
    *,
    captured_at: str,
    type_path: tuple[str, ...],
    max_retries: int = MAX_RETRIES,
    max_pages: int = MAX_PAGES,
    sleeper: Callable[[float], None] | None = None,
) -> SourceRun:
    spec = SOURCE_SPECS[source_id]
    reasons: list[str] = []
    raw_items: list[Any] = []
    parsed: list[ObservedRecord] = []
    pages_fetched = 0
    coverage_complete = False
    error_class: str | None = None
    attempts = 0
    pages_expected: int | None = None

    for page in range(1, max_pages + 1):
        params = {spec["query_param"]: queried_cnpj, "pagina": page}
        response: TransportResponse = fetch_with_retry(
            transport,
            source_id=source_id,
            path=spec["path"],
            params=params,
            max_retries=max_retries,
            sleeper=sleeper,
        )
        attempts = max(attempts, response.attempts)
        pages_fetched += 1

        if response.error_class in {"timeout"}:
            error_class = "timeout"
            reasons.append("timeout")
            reasons.append("pagination_incomplete")
            break
        if response.error_class in {"rate_limit_exhausted", "rate_limit"} or response.status_code == 429:
            error_class = "rate_limit_exhausted"
            reasons.extend(["rate_limit_exhausted", "retry_exhausted", "pagination_incomplete"])
            break
        if response.error_class in {"http_5xx"} or response.status_code >= 500:
            error_class = "http_5xx"
            reasons.extend(["http_5xx", "retry_exhausted", "pagination_incomplete"])
            break
        if response.error_class in {"source_unavailable", "network"}:
            error_class = "source_unavailable"
            reasons.extend(["source_unavailable", "pagination_incomplete"])
            break
        if response.status_code not in {200, 204}:
            error_class = "source_unavailable"
            reasons.extend(["source_unavailable", "pagination_incomplete"])
            break

        page_list, drift = _as_page_list(response.body)
        if drift or page_list is None:
            error_class = "schema_drift"
            reasons.extend(["schema_drift", "pagination_incomplete"])
            break
        if len(page_list) == 0:
            coverage_complete = True
            pages_expected = pages_fetched
            break
        raw_items.extend(page_list)
        page_parsed = 0
        page_failed = 0
        for item in page_list:
            record = normalize_record(
                item,
                source_id=source_id,
                source_url=spec["official_url"],
                captured_at=captured_at,
                type_path=type_path,
            )
            if record is None:
                page_failed += 1
                continue
            parsed.append(record)
            page_parsed += 1
        if page_failed:
            error_class = "parse_incomplete"
            reasons.extend(["parse_incomplete", "coverage_incomplete"])
            coverage_complete = False
            break
        if page == max_pages:
            error_class = "page_cap_hit"
            reasons.extend(["page_cap_hit", "pagination_incomplete"])
            break
    else:
        error_class = "page_cap_hit"
        reasons.extend(["page_cap_hit", "pagination_incomplete"])

    unique = tuple(dict.fromkeys(reasons))
    if error_class is not None:
        coverage_complete = False
        pages_expected = None
    if not coverage_complete and "pagination_incomplete" not in unique and unique:
        unique = (*unique, "pagination_incomplete")

    deduped, dedupe_codes = dedupe_records(tuple(parsed))
    unique = tuple(dict.fromkeys([*unique, *dedupe_codes]))
    status = _source_status(
        coverage_complete=coverage_complete and error_class is None,
        records=deduped,
        reasons=unique,
    )

    return SourceRun(
        source_id=source_id,
        official_url=spec["official_url"],
        api_url=spec["api_url"],
        authority=spec["authority"],
        status=status,
        pages_expected=pages_expected,
        pages_fetched=pages_fetched,
        coverage_complete=coverage_complete,
        raw_count=len(raw_items),
        normalized_count=len(parsed),
        deduped_count=len(deduped),
        reason_codes=unique,
        as_of=captured_at if pages_fetched else None,
        error_class=error_class,
        attempts=attempts,
        records=deduped,
    )
