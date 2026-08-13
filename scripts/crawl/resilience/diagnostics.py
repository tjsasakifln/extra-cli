"""Sanitized, reproducible failure events for request/page attempts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_KEYS = re.compile(r"(?i)(token|secret|password|passwd|authorization|cookie|api[-_]?key|dsn)")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_BASIC_AUTH = re.compile(r"(?i)basic\s+[A-Za-z0-9+/=]+")
_CREDENTIAL_HEADER = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*[^\r\n]+"
)
_DSN = re.compile(r"(?i)(postgres(?:ql)?://)([^\s/@:]+)(?::[^\s/@]*)?@")
_BODY_KEYS = re.compile(r"(?i)(raw[_-]?)?(response[_-]?)?(body|content|payload)$")


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(str(url))
    except ValueError:
        return "<invalid-url>"
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        return "<invalid-url>"
    if port:
        host = f"{host}:{port}"
    query = [
        (key, "<redacted>" if _SENSITIVE_KEYS.search(key) else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, host, parsed.path, urlencode(query), ""))


def sanitize_text(value: Any) -> str:
    text = str(value)
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _BASIC_AUTH.sub("Basic <redacted>", text)
    text = _CREDENTIAL_HEADER.sub(lambda match: f"{match.group(1)}: <redacted>", text)
    text = _DSN.sub(r"\1<redacted>@", text)
    text = re.sub(r"(?i)(token|secret|password|api[-_]?key)=([^&\s]+)", r"\1=<redacted>", text)
    return text[:2000]


@dataclass(frozen=True)
class FailureClassification:
    error_class: str
    transient: bool
    next_action: str


def classify_failure(*, http_status: int | None, error: Any) -> FailureClassification:
    message = str(error).lower()
    if http_status in {401, 403} or "captcha" in message or "login required" in message:
        return FailureClassification("AUTH_BLOCKED", False, "human_review_source_access")
    if http_status == 404:
        return FailureClassification("SOURCE_DRIFT", False, "rediscover_official_surface")
    if http_status == 429:
        return FailureClassification("RATE_LIMITED", True, "retry_after_policy_delay")
    if http_status is not None and 500 <= http_status <= 599:
        return FailureClassification("UPSTREAM_TRANSIENT", True, "retry_with_circuit_breaker")
    if "timeout" in message or "connection" in message or "reset" in message:
        return FailureClassification("TRANSPORT_TRANSIENT", True, "retry_with_circuit_breaker")
    if "json" in message or "parse" in message or "schema" in message:
        return FailureClassification("PARSE_OR_SCHEMA_DRIFT", False, "inspect_and_update_adapter")
    return FailureClassification("UNCLASSIFIED_FAILURE", False, "inspect_failure")


@dataclass(frozen=True)
class FailureEvent:
    source: str
    run_id: str
    request_scope: str
    stage: str
    error_class: str
    transient: bool
    next_action: str
    message: str
    url: str | None = None
    http_status: int | None = None
    page: int | None = None
    cursor: str | None = None
    attempt_no: int = 1
    job_id: int | None = None
    crawl_job_attempt_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def fingerprint(self) -> str:
        canonical = "|".join(
            [self.source, self.request_scope, self.stage, self.error_class, str(self.http_status), self.message]
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["url"] = sanitize_url(self.url)
        record["message"] = sanitize_text(self.message)
        record["metadata"] = sanitize_mapping(self.metadata)
        record["fingerprint"] = self.fingerprint
        return record


def sanitize_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        redacted_keys: list[str] = []
        raw_reference = value.get("raw_reference") or value.get("raw_uri")
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEYS.search(name):
                redacted_keys.append(name)
                continue
            if _BODY_KEYS.search(name) and isinstance(item, (bytes, bytearray, memoryview)):
                marker = _binary_marker(bytes(item))
                marker["raw_archive_reference"] = (
                    sanitize_text(raw_reference) if raw_reference else "<required-outside-diagnostics>"
                )
                sanitized[name] = marker
                continue
            sanitized[name] = sanitize_mapping(item)
        if redacted_keys:
            sanitized["_redacted_keys"] = sorted(redacted_keys, key=str.casefold)
        return sanitized
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _binary_marker(bytes(value))
    return value


def _binary_marker(value: bytes) -> dict[str, Any]:
    return {
        "binary_redacted": True,
        "sha256": hashlib.sha256(value).hexdigest(),
        "size_bytes": len(value),
    }


class FailureRecorder:
    """Append sanitized local evidence and project it to PostgreSQL when required."""

    def __init__(self, path: Path, *, dsn: str | None = None, require_db: bool = False):
        self.path = path
        self.dsn = dsn
        self.require_db = require_db

    def record(self, event: FailureEvent) -> dict[str, Any]:
        record = event.to_record()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        persisted = False
        if self.dsn:
            self._record_postgres(record)
            persisted = True
        elif self.require_db:
            raise RuntimeError("failure_event_database_required_but_dsn_missing")
        return {"fingerprint": record["fingerprint"], "path": str(self.path), "db_persisted": persisted}

    def _record_postgres(self, record: dict[str, Any]) -> None:
        import psycopg2

        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawl_failure_events (
                    source, run_id, job_id, crawl_job_attempt_id, request_scope,
                    stage, page, cursor, error_class, http_status, attempt_no,
                    transient, next_action, sanitized_url, message,
                    error_fingerprint, metadata, observed_at
                ) VALUES (
                    %(source)s, %(run_id)s, %(job_id)s, %(crawl_job_attempt_id)s,
                    %(request_scope)s, %(stage)s, %(page)s, %(cursor)s,
                    %(error_class)s, %(http_status)s, %(attempt_no)s,
                    %(transient)s, %(next_action)s, %(url)s, %(message)s,
                    %(fingerprint)s, %(metadata)s::jsonb, %(observed_at)s::timestamptz
                )
                ON CONFLICT (run_id, source, request_scope, attempt_no, error_fingerprint)
                DO UPDATE SET observed_at = EXCLUDED.observed_at,
                              metadata = crawl_failure_events.metadata || EXCLUDED.metadata
                """,
                {**record, "metadata": json.dumps(record["metadata"], ensure_ascii=False)},
            )


def event_from_failure(
    *,
    source: str,
    run_id: str,
    request_scope: str,
    stage: str,
    error: Any,
    http_status: int | None = None,
    url: str | None = None,
    page: int | None = None,
    cursor: str | None = None,
    attempt_no: int = 1,
    metadata: dict[str, Any] | None = None,
) -> FailureEvent:
    classification = classify_failure(http_status=http_status, error=error)
    return FailureEvent(
        source=source,
        run_id=run_id,
        request_scope=request_scope,
        stage=stage,
        error_class=classification.error_class,
        transient=classification.transient,
        next_action=classification.next_action,
        message=sanitize_text(error),
        url=url,
        http_status=http_status,
        page=page,
        cursor=cursor,
        attempt_no=attempt_no,
        metadata=metadata or {},
    )
