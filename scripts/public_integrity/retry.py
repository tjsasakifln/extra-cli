"""Bounded retry. Exhausted 429/5xx/timeout stay observable; never become a miss."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.public_integrity.models import MAX_RETRIES, TransportResponse
from scripts.public_integrity.transport import Transport


def _should_retry(response: TransportResponse) -> bool:
    if response.error_class in {"timeout", "network", "rate_limit", "http_5xx"}:
        return True
    if response.status_code == 429:
        return True
    if response.status_code >= 500:
        return True
    return False


def _reason_for(response: TransportResponse) -> str:
    if response.error_class == "timeout":
        return "timeout"
    if response.error_class == "network":
        return "source_unavailable"
    if response.status_code == 429 or response.error_class == "rate_limit":
        return "rate_limit_exhausted"
    if response.status_code >= 500 or response.error_class == "http_5xx":
        return "http_5xx"
    if response.error_class:
        return response.error_class
    return "retry_exhausted"


def fetch_with_retry(
    transport: Transport,
    *,
    source_id: str,
    path: str,
    params: dict[str, Any],
    max_retries: int = MAX_RETRIES,
    sleeper: Callable[[float], None] | None = None,
) -> TransportResponse:
    """Retry timeout/429/5xx up to max_retries extra attempts. Sleep is injectable."""
    pause = sleeper or (lambda _seconds: None)
    last = TransportResponse(status_code=0, body=None, error_class="source_unavailable", attempts=0)
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        last = transport.fetch(source_id=source_id, path=path, params=params)
        last = TransportResponse(
            status_code=last.status_code,
            body=last.body,
            error_class=last.error_class,
            headers=last.headers,
            attempts=attempt,
        )
        if not _should_retry(last):
            return last
        if attempt >= total_attempts:
            break
        pause(0)
    return TransportResponse(
        status_code=last.status_code,
        body=last.body,
        error_class=_reason_for(last),
        headers=last.headers,
        attempts=last.attempts,
    )
