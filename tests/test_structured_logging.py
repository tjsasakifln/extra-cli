"""DoD §23 — structured logs: ts, level, service, source, run_id, no secrets."""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys

from scripts.lib.structured_logging import (
    assert_record_schema,
    contains_secret_leak,
    log_event,
    new_run_id,
    redact_secrets,
    setup_structured_logger,
)


def test_new_run_id_stable_shape() -> None:
    rid = new_run_id("svc")
    assert rid.startswith("svc-")
    assert len(rid) > 20


def test_structured_fields_present() -> None:
    buf = io.StringIO()
    logger, rid = setup_structured_logger(
        service="test-svc", source="unit", run_id="run-fixed-1", stream=buf
    )
    log_event(logger, logging.INFO, "hello", event="t")
    rec = json.loads(buf.getvalue().strip().splitlines()[0])
    assert assert_record_schema(rec) == []
    assert rec["service"] == "test-svc"
    assert rec["source"] == "unit"
    assert rec["run_id"] == "run-fixed-1"
    assert rec["level"] == "INFO"
    assert "T" in rec["ts"] and rec["ts"].endswith("Z")
    assert rec["msg"] == "hello"


def test_redact_password_and_dsn() -> None:
    assert "super" not in redact_secrets("password=super-secret")
    assert "[REDACTED]" in redact_secrets("password=super-secret")
    assert "user:pass" not in redact_secrets("postgres://user:pass@host/db")


def test_log_line_redacts_secrets() -> None:
    buf = io.StringIO()
    logger, _ = setup_structured_logger(
        service="sec", source="test", run_id="r1", stream=buf
    )
    logger.info("auth token=sk-abcdefghijklmnopqrstuvwxyz password=hunter2")
    logger.error("DATABASE_URL=postgres://u:p@localhost/extra")
    raw = buf.getvalue()
    assert "hunter2" not in raw
    assert "u:p@" not in raw
    assert not contains_secret_leak(raw)
    for line in raw.strip().splitlines():
        rec = json.loads(line)
        assert assert_record_schema(rec) == []


def test_cli_self_check() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.lib.structured_logging", "--self-check"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    body = json.loads(r.stdout)
    assert body["ok"] is True
    assert body["records"] >= 3
    assert body["sample"]["level"]
    assert body["sample"]["run_id"]
