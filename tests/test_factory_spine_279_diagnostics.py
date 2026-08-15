"""Refs #279 — structured per-request/page failure, no secrets persisted."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from scripts.factory_spine.store import FactoryStore


@pytest.mark.parametrize(
    ("status", "error", "error_class", "transient"),
    [
        (403, "HTTP 403", "AUTH_BLOCKED", False),
        (404, "HTTP 404 drift", "SOURCE_DRIFT", False),
        (429, "HTTP 429", "RATE_LIMITED", True),
        (504, "HTTP 504", "UPSTREAM_TRANSIENT", True),
        (None, requests.Timeout("timeout"), "TRANSPORT_TRANSIENT", True),
        (200, ValueError("json parse failed"), "PARSE_OR_SCHEMA_DRIFT", False),
        (200, RuntimeError("persist failed writing cas"), "PERSIST_FAILURE", False),
    ],
)
def test_issue_279_structured_failure_matrix(
    tmp_path: Path,
    status: int | None,
    error: object,
    error_class: str,
    transient: bool,
) -> None:
    store = FactoryStore(tmp_path)
    recorded = store.record_structured_failure(
        source="pncp",
        run_id="run-diag",
        request_scope="entity-1:page-2",
        stage="fetch",
        error=error,
        http_status=status,
        url="https://pncp.gov.br/api?token=super-secret&pagina=2",
        page=2,
        cursor="pagina=2",
        attempt_no=3,
        job_id=88,
        crawl_job_attempt_id=12,
        metadata={"authorization": "Bearer super-secret", "password": "hunter2"},
    )
    event = recorded["event"]
    assert event["source"] == "pncp"
    assert event["error_class"] == error_class
    assert event["transient"] is transient
    assert event["page"] == 2
    assert event["cursor"] == "pagina=2"
    assert event["attempt_no"] == 3
    assert event["next_action"]
    assert event["url"] is not None
    assert "super-secret" not in json.dumps(event)
    assert "hunter2" not in json.dumps(event)
    assert "super-secret" not in (event["url"] or "")
    assert "redacted" in (event["url"] or "")
    persisted = (tmp_path / "failures.jsonl").read_text(encoding="utf-8")
    assert "super-secret" not in persisted
    assert recorded["fingerprint"]
