"""Contracts for versioned transport policies and durable crawl diagnostics."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.crawl import pncp_crawler_adapter as pncp
from scripts.crawl.resilience.diagnostics import (
    FailureRecorder,
    classify_failure,
    event_from_failure,
    sanitize_url,
)
from scripts.crawl.resilience.domain_policy import DomainPolicyRegistry
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy


def test_domain_policy_resolves_checked_in_domain_and_default() -> None:
    registry = DomainPolicyRegistry.load()

    pncp_policy = registry.resolve("https://consulta.pncp.gov.br/api/consulta/v1/contratacoes")
    fallback = registry.resolve("https://public.example.test/data")

    assert pncp_policy.name == "pncp"
    assert pncp_policy.matched_suffix == "pncp.gov.br"
    assert pncp_policy.values["max_retries"] == 8
    assert len(pncp_policy.fingerprint) == 64
    assert fallback.name == "default"
    assert fallback.values["max_retries"] == 5


def test_domain_policy_rejects_invalid_registry(tmp_path: Path) -> None:
    invalid = tmp_path / "policy.json"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": "crawl-domain-policy/v1",
                "policy_version": "test",
                "default": {"connect_timeout": 1},
                "domains": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be numeric"):
        DomainPolicyRegistry.load(invalid)


@pytest.mark.parametrize(
    ("status", "error", "error_class", "transient"),
    [
        (403, "HTTP 403", "AUTH_BLOCKED", False),
        (404, "HTTP 404", "SOURCE_DRIFT", False),
        (429, "HTTP 429", "RATE_LIMITED", True),
        (504, "HTTP 504", "UPSTREAM_TRANSIENT", True),
        (None, requests.Timeout("timeout"), "TRANSPORT_TRANSIENT", True),
        (None, requests.ConnectionError("connection reset"), "TRANSPORT_TRANSIENT", True),
        (200, ValueError("schema parse failure"), "PARSE_OR_SCHEMA_DRIFT", False),
    ],
)
def test_failure_classification_matrix(
    status: int | None,
    error: object,
    error_class: str,
    transient: bool,
) -> None:
    result = classify_failure(http_status=status, error=error)
    assert result.error_class == error_class
    assert result.transient is transient
    assert result.next_action


def test_failure_event_redacts_url_message_and_nested_metadata(tmp_path: Path) -> None:
    recorder = FailureRecorder(tmp_path / "failures.jsonl")
    event = event_from_failure(
        source="pncp",
        run_id="run-1",
        request_scope="page=1",
        stage="fetch",
        error=("Bearer abc.def token=top-secret postgresql://crawl:db-password@db.internal:5432/extra"),
        http_status=403,
        url="https://user:pass@example.test/path?token=top-secret&safe=yes#fragment",
        page=1,
        metadata={
            "headers": {
                "Cookie": "sid=secret",
                "Accept": "application/json",
                "Authorization": "Basic dXNlcjpwYXNz",
            },
            "raw_reference": "cas://failure/body-sha",
            "raw_response_body": b"secret response body",
        },
    )

    projection = recorder.record(event)
    saved = json.loads((tmp_path / "failures.jsonl").read_text(encoding="utf-8"))
    serialized = json.dumps(saved, sort_keys=True)

    assert projection["db_persisted"] is False
    assert saved["url"] == "https://example.test/path?token=%3Credacted%3E&safe=yes"
    assert saved["metadata"]["headers"]["_redacted_keys"] == ["Authorization", "Cookie"]
    assert saved["metadata"]["raw_response_body"]["binary_redacted"] is True
    assert saved["metadata"]["raw_response_body"]["raw_archive_reference"] == "cas://failure/body-sha"
    assert "top-secret" not in serialized
    assert "db-password" not in serialized
    assert "abc.def" not in serialized
    assert "dXNlcjpwYXNz" not in serialized
    assert "secret response body" not in serialized


def test_failure_schema_rejects_secret_keys_recursively() -> None:
    sql = Path("db/migrations/078_crawl_failure_events.sql").read_text(encoding="utf-8")
    assert "crawl_metadata_has_secret_key(item_value)" in sql
    assert "lower(item_key) = ANY" in sql
    assert "NOT crawl_metadata_has_secret_key(metadata)" in sql


@pytest.mark.parametrize("url", ["http://host:bad/path", "http://[invalid/path"])
def test_sanitize_url_fails_closed_for_invalid_url(url: str) -> None:
    assert sanitize_url(url) == "<invalid-url>"


def test_failure_recorder_uses_postgresql_projection(tmp_path: Path) -> None:
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    event = event_from_failure(
        source="pncp",
        run_id="run-db",
        request_scope="page=2",
        stage="fetch",
        error="HTTP 504",
        http_status=504,
    )

    with patch("psycopg2.connect", return_value=connection) as connect:
        projection = FailureRecorder(
            tmp_path / "failures.jsonl",
            dsn="postgresql://test:test@127.0.0.1:5433/extra_test",
            require_db=True,
        ).record(event)

    connect.assert_called_once()
    cursor.execute.assert_called_once()
    assert "INSERT INTO crawl_failure_events" in cursor.execute.call_args.args[0]
    assert projection["db_persisted"] is True


@pytest.mark.database
@pytest.mark.integration
def test_failure_recorder_real_postgresql(tmp_path: Path) -> None:
    if not (
        os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
        or os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {"1", "true", "yes"}
    ):
        pytest.skip("REQUIRE_REAL_DB=1 or RESILIENCE_REQUIRE_DB=1 required")
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        pytest.skip("DATABASE_URL or LOCAL_DATALAKE_DSN not set")

    import psycopg2

    event = event_from_failure(
        source="diagnostic_integration",
        run_id="run-db-integration",
        request_scope="page=1",
        stage="fetch",
        error="HTTP 504",
        http_status=504,
    )
    FailureRecorder(tmp_path / "failures.jsonl", dsn=dsn, require_db=True).record(event)
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT error_class, transient, next_action
            FROM crawl_failure_events
            WHERE run_id = %s AND source = %s
            """,
            (event.run_id, event.source),
        )
        persisted = cursor.fetchone()

    assert persisted == ("UPSTREAM_TRANSIENT", True, "retry_with_circuit_breaker")


@pytest.mark.parametrize(
    ("effect", "expected_status", "expected_calls"),
    [
        (403, "auth_blocked", 1),
        (504, "error", 3),
        (requests.Timeout("timeout"), "error", 3),
        (requests.ConnectionError("connection reset"), "error", 3),
    ],
)
def test_http_policy_failure_matrix_does_not_loop_permanent_auth(
    effect: int | Exception,
    expected_status: str,
    expected_calls: int,
) -> None:
    session = MagicMock()
    if isinstance(effect, int):
        response = MagicMock(status_code=effect, headers={"content-type": "application/json"})
        session.get.return_value = response
    else:
        session.get.side_effect = effect
    policy = HttpResiliencePolicy(
        connect_timeout=1,
        read_timeout=2,
        max_retries=2,
        base_delay=0,
        max_delay=0,
        jitter=0,
    )

    result = pncp._http_get_json(
        "https://consulta.pncp.gov.br/test",
        session=session,
        sleeper=lambda _seconds: None,
        http_policy=policy,
    )

    assert result.status == expected_status
    assert session.get.call_count == expected_calls
    assert len(result.metadata["attempt_metrics"]) == expected_calls
    assert all("latency_ms" in row and "sleep_seconds" in row for row in result.metadata["attempt_metrics"])
