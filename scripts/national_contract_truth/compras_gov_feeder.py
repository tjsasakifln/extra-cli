"""#251 — Compras.gov 14.133 + legado feeder fail-closed contract.

Error, credential failure and blocks never become ZERO.
Silent MAX_PAGES truncation is FAILED. Legacy without CNPJ stays REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

OPEN_WINDOW_START = date(2025, 1, 1)
SCOPE_14133 = "lei_14133"
SCOPE_LEGADO = "legado"

FetchStatus = Literal["OK", "ZERO", "FAILED"]
PaginationStatus = Literal["COMPLETE", "ZERO", "FAILED", "PAGINATION_TRUNCATED"]
RecordDisposition = Literal["ACCEPT", "REVIEW", "REJECT"]


class ComprasGovIngestError(RuntimeError):
    """Raised when a Compras.gov ingest must not be reported as success/zero."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class FetchOutcome:
    status: FetchStatus
    record_count: int
    reason: str


@dataclass(frozen=True)
class PaginationVerdict:
    status: PaginationStatus
    pages_fetched: int
    pages_expected: int | None
    reason: str

    @property
    def is_success(self) -> bool:
        return self.status in ("COMPLETE", "ZERO")


@dataclass(frozen=True)
class ScopeIngest:
    scope: str
    pagination: PaginationVerdict
    dispositions: tuple[RecordDisposition, ...]


def default_open_window(
    snapshot: date,
    *,
    has_native_open_status: bool,
) -> tuple[date, date] | None:
    """When the source has no native open-status filter, use 2025-01-01..snapshot."""
    if has_native_open_status:
        return None
    if snapshot < OPEN_WINDOW_START:
        return snapshot, snapshot
    return OPEN_WINDOW_START, snapshot


def classify_fetch(
    *,
    http_status: int | None,
    records: list[Any] | None,
    error: str | None,
) -> FetchOutcome:
    """HTTP/credential/block errors are FAILED, never ZERO."""
    count = len(records or [])
    if error or http_status is None or http_status >= 400:
        return FetchOutcome(status="FAILED", record_count=count, reason=error or f"http_{http_status}")
    if count == 0:
        return FetchOutcome(status="ZERO", record_count=0, reason="empty_ok")
    return FetchOutcome(status="OK", record_count=count, reason="page_ok")


def reconcile_pagination(
    *,
    pages_fetched: int,
    pages_expected: int | None,
    max_pages: int,
    last_fetch: FetchOutcome,
    has_more: bool,
) -> PaginationVerdict:
    """Pagination must reach the declared total. MAX_PAGES is never a silent success."""
    if last_fetch.status == "FAILED":
        return PaginationVerdict(
            status="FAILED",
            pages_fetched=pages_fetched,
            pages_expected=pages_expected,
            reason=last_fetch.reason,
        )
    if has_more and pages_fetched >= max_pages:
        return PaginationVerdict(
            status="PAGINATION_TRUNCATED",
            pages_fetched=pages_fetched,
            pages_expected=pages_expected,
            reason="max_pages_silent_truncation",
        )
    if pages_expected is not None and pages_fetched < pages_expected:
        return PaginationVerdict(
            status="PAGINATION_TRUNCATED",
            pages_fetched=pages_fetched,
            pages_expected=pages_expected,
            reason="pages_fetched_lt_expected",
        )
    if last_fetch.status == "ZERO" and pages_fetched <= 1:
        return PaginationVerdict(
            status="ZERO",
            pages_fetched=pages_fetched,
            pages_expected=pages_expected or 0,
            reason="empty_ok",
        )
    return PaginationVerdict(
        status="COMPLETE",
        pages_fetched=pages_fetched,
        pages_expected=pages_expected,
        reason="exhausted",
    )


def classify_legacy_record(record: dict[str, Any]) -> RecordDisposition:
    """Legado without CNPJ remains unmatched/REVIEW. It is never silently accepted as identified."""
    cnpj = "".join(ch for ch in str(record.get("orgao_cnpj") or record.get("cnpj") or "") if ch.isdigit())
    if len(cnpj) == 14:
        return "ACCEPT"
    return "REVIEW"


def ingest_scope(
    scope: str,
    pagination: PaginationVerdict,
    records: list[dict[str, Any]],
) -> ScopeIngest:
    if not pagination.is_success:
        raise ComprasGovIngestError(pagination.status, pagination.reason)
    if scope == SCOPE_LEGADO:
        dispositions = tuple(classify_legacy_record(record) for record in records)
    else:
        dispositions = tuple("ACCEPT" if record.get("orgao_cnpj") else "REJECT" for record in records)
    return ScopeIngest(scope=scope, pagination=pagination, dispositions=dispositions)
