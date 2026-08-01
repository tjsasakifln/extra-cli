"""Error classification for entity×source collection attempts.

Classes are operational (not free-text). Used for circuit breaker, DLQ,
backoff policy and observability. Never treat silent absence as success.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any


class ErrorClass(StrEnum):
    NONE = "none"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    SOURCE_BLOCKED = "source_blocked"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    DOCUMENT_NOT_FOUND = "document_not_found"
    PARSING = "parsing"
    CORRUPT_FILE = "corrupt_file"
    NETWORK = "network"
    TIMEOUT = "timeout"
    CAPACITY = "capacity"
    UNKNOWN = "unknown"


# Status/HTTP/message patterns → class (order matters: first match wins)
_PATTERNS: list[tuple[ErrorClass, re.Pattern[str]]] = [
    (ErrorClass.RATE_LIMIT, re.compile(r"\b(429|rate.?limit|too many requests|throttl)\b", re.I)),
    (ErrorClass.AUTHENTICATION, re.compile(r"\b(401|403|unauthor|forbidden|auth|credential|login)\b", re.I)),
    (
        ErrorClass.DOCUMENT_NOT_FOUND,
        re.compile(r"\b(404|not.?found|gone|410|inexistente|não publicado|nao publicado)\b", re.I),
    ),
    (ErrorClass.SOURCE_BLOCKED, re.compile(r"\b(captcha|blocked|waf|cloudflare|access.?denied|ban(ned)?)\b", re.I)),
    (
        ErrorClass.CORRUPT_FILE,
        re.compile(r"\b(corrupt|empty.?file|zero.?byte|html.?disguised|mime.?mismatch|invalid.?pdf)\b", re.I),
    ),
    (ErrorClass.PARSING, re.compile(r"\b(parse|parsing|decode|json.?error|xml.?error|malformed)\b", re.I)),
    (ErrorClass.TIMEOUT, re.compile(r"\b(timeout|timed.?out|deadline)\b", re.I)),
    (ErrorClass.NETWORK, re.compile(r"\b(connection|connect|reset|dns|ssl|tls|network|unreachable|econn)\b", re.I)),
    (ErrorClass.CAPACITY, re.compile(r"\b(capacity|disk.?full|enospc|oom|memory|backpressure)\b", re.I)),
    (ErrorClass.TRANSIENT, re.compile(r"\b(500|502|503|504|temporary|retry|unavailable)\b", re.I)),
    (ErrorClass.PERMANENT, re.compile(r"\b(400|422|invalid.?request|schema|permanent|unsupported)\b", re.I)),
]

# Status codes that map without message scan
_HTTP_MAP: dict[int, ErrorClass] = {
    400: ErrorClass.PERMANENT,
    401: ErrorClass.AUTHENTICATION,
    403: ErrorClass.AUTHENTICATION,
    404: ErrorClass.DOCUMENT_NOT_FOUND,
    410: ErrorClass.DOCUMENT_NOT_FOUND,
    422: ErrorClass.PERMANENT,
    429: ErrorClass.RATE_LIMIT,
    500: ErrorClass.TRANSIENT,
    502: ErrorClass.TRANSIENT,
    503: ErrorClass.TRANSIENT,
    504: ErrorClass.TIMEOUT,
}


def classify_error(
    *,
    status: str | None = None,
    error: str | None = None,
    http_status: int | None = None,
    exception_type: str | None = None,
) -> ErrorClass:
    """Classify a failure. Empty success signals return NONE."""
    if not status and not error and http_status is None and not exception_type:
        return ErrorClass.NONE

    if http_status is not None and http_status in _HTTP_MAP:
        return _HTTP_MAP[http_status]

    blob = " ".join(str(x) for x in (status, error, exception_type, http_status) if x is not None and str(x).strip())
    if not blob.strip():
        return ErrorClass.NONE

    # Explicit operational statuses from our pipeline
    st = (status or "").lower()
    if st in {"success", "success_nonzero", "success_zero", "ok"}:
        return ErrorClass.NONE
    if "not_queried" in st or st in {"not_queried", "not_queried_budget"}:
        return ErrorClass.CAPACITY
    if "rate" in st:
        return ErrorClass.RATE_LIMIT
    if "auth" in st:
        return ErrorClass.AUTHENTICATION
    if "corrupt" in st or "quarantine" in st:
        return ErrorClass.CORRUPT_FILE
    if "parse" in st:
        return ErrorClass.PARSING
    if "timeout" in st:
        return ErrorClass.TIMEOUT
    if "blocked" in st:
        return ErrorClass.SOURCE_BLOCKED
    if "connection" in st or "network" in st:
        return ErrorClass.NETWORK

    for cls, pat in _PATTERNS:
        if pat.search(blob):
            return cls
    return ErrorClass.UNKNOWN


def is_retryable(error_class: ErrorClass | str) -> bool:
    cls = ErrorClass(str(error_class)) if not isinstance(error_class, ErrorClass) else error_class
    return cls in {
        ErrorClass.TRANSIENT,
        ErrorClass.RATE_LIMIT,
        ErrorClass.NETWORK,
        ErrorClass.TIMEOUT,
        ErrorClass.CAPACITY,
        ErrorClass.UNKNOWN,
    }


def should_open_circuit(error_class: ErrorClass | str) -> bool:
    cls = ErrorClass(str(error_class)) if not isinstance(error_class, ErrorClass) else error_class
    return cls in {
        ErrorClass.RATE_LIMIT,
        ErrorClass.SOURCE_BLOCKED,
        ErrorClass.AUTHENTICATION,
        ErrorClass.TRANSIENT,
        ErrorClass.NETWORK,
        ErrorClass.TIMEOUT,
    }


def should_dead_letter(error_class: ErrorClass | str, consecutive_failures: int, *, threshold: int = 5) -> bool:
    cls = ErrorClass(str(error_class)) if not isinstance(error_class, ErrorClass) else error_class
    if cls in {ErrorClass.PERMANENT, ErrorClass.DOCUMENT_NOT_FOUND, ErrorClass.CORRUPT_FILE, ErrorClass.PARSING}:
        return consecutive_failures >= 2
    return consecutive_failures >= threshold


def classify_from_result(result: dict[str, Any] | None) -> ErrorClass:
    if not result:
        return ErrorClass.UNKNOWN
    return classify_error(
        status=str(result.get("status") or "") or None,
        error=str(result.get("error") or result.get("last_error") or "") or None,
        http_status=result.get("http_status") if isinstance(result.get("http_status"), int) else None,
        exception_type=str(result.get("exception_type") or "") or None,
    )
