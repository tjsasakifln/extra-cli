"""PNCP open-opportunity pagination proof partitioned by entity.

pages_expected must equal pages_fetched for a complete scope. Each page keeps
a sanitized URL, HTTP status, fetched_at, raw URI and SHA-256. Applicable
entities finish FOUND or ZERO_CONFIRMED only with a complete query.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SLA_HOURS = 4
SLA_HARD_HOURS = 24
SECRET_QUERY_KEYS = frozenset({"token", "access_token", "api_key", "apikey", "authorization", "sig"})

EntityVerdict = Literal["FOUND", "ZERO_CONFIRMED", "SCOPE_INCOMPLETE"]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in SECRET_QUERY_KEYS]
    return urlunparse(parsed._replace(query=urlencode(query)))


@dataclass(frozen=True)
class PageRecord:
    url: str
    status: int
    fetched_at: str
    raw_uri: str
    sha256: str
    page: int
    records: int


@dataclass(frozen=True)
class ScopeProof:
    ente_id: str
    window: str
    modalidade: str | None
    pages_expected: int
    pages_fetched: int
    pages: tuple[PageRecord, ...]
    found_count: int
    query_complete: bool

    @property
    def pages_match(self) -> bool:
        return self.pages_expected == self.pages_fetched == len(self.pages)

    @property
    def verdict(self) -> EntityVerdict:
        if not self.query_complete or not self.pages_match:
            return "SCOPE_INCOMPLETE"
        if self.found_count > 0:
            return "FOUND"
        return "ZERO_CONFIRMED"


def record_page(
    *,
    url: str,
    status: int,
    body: bytes,
    page: int,
    records: int,
    fetched_at: str | None = None,
) -> PageRecord:
    digest = sha256_bytes(body)
    return PageRecord(
        url=sanitize_url(url),
        status=status,
        fetched_at=fetched_at or _utc_now().isoformat().replace("+00:00", "Z"),
        raw_uri=f"cas://pncp/{digest}",
        sha256=digest,
        page=page,
        records=records,
    )


def prove_scope(
    *,
    ente_id: str,
    window: str,
    modalidade: str | None,
    pages_expected: int,
    pages: list[PageRecord],
    found_count: int,
    query_complete: bool,
) -> ScopeProof:
    if pages_expected < 0:
        raise ValueError("pages_expected must be >= 0")
    return ScopeProof(
        ente_id=ente_id,
        window=window,
        modalidade=modalidade,
        pages_expected=pages_expected,
        pages_fetched=len(pages),
        pages=tuple(pages),
        found_count=found_count,
        query_complete=query_complete,
    )


def sla_status(discovered_at: datetime, published_at: datetime) -> dict[str, Any]:
    lag_hours = (discovered_at - published_at).total_seconds() / 3600.0
    return {
        "lag_hours": lag_hours,
        "within_slo": lag_hours <= SLA_HOURS,
        "within_hard_limit": lag_hours <= SLA_HARD_HOURS,
        "breach": lag_hours > SLA_HARD_HOURS,
    }


def closing_requery(candidates: list[str], requery_hits: set[str]) -> dict[str, Any]:
    """Candidates are reconsulted at window close."""
    missing = [c for c in candidates if c not in requery_hits]
    return {
        "candidates": list(candidates),
        "reconfirmed": sorted(requery_hits),
        "missing": missing,
        "complete": not missing,
    }


def proof_report(scopes: list[ScopeProof]) -> dict[str, Any]:
    return {
        "scopes": [
            {
                **asdict(scope),
                "pages_match": scope.pages_match,
                "verdict": scope.verdict,
            }
            for scope in scopes
        ],
        "sla_hours": SLA_HOURS,
        "sla_hard_hours": SLA_HARD_HOURS,
        "related": ["#34", "#40"],
        "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
    }


def expected_pages(total_registros: int, page_size: int) -> int:
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    if total_registros == 0:
        return 1
    return (total_registros + page_size - 1) // page_size
