"""Structured JSON logging for Extra Consultoria (DoD §23 observability).

Fields guaranteed on every record:
  ts, level, service, source, run_id, msg
Secrets (tokens, passwords, DSNs with credentials) are redacted.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

# Patterns that must never appear in cleartext in logs.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(api[_-]?key|token|secret|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(postgres|postgresql|mysql|mongodb)://[^\s]+"),
    re.compile(r"(?i)(aws_secret_access_key|private_key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
)


def new_run_id(prefix: str = "run") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def redact_secrets(text: str) -> str:
    """Replace secret-like substrings with [REDACTED]."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


class StructuredJsonFormatter(logging.Formatter):
    """Emit one JSON object per log line (newline-delimited JSON)."""

    def __init__(
        self,
        *,
        service: str,
        source: str,
        run_id: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.source = source
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "source": self.source,
            "run_id": self.run_id,
            "logger": record.name,
            "msg": redact_secrets(msg),
        }
        # Optional structured extras (never override core keys blindly)
        for key in ("entity_id", "fonte", "http_status", "duration_ms", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_structured_logger(
    *,
    service: str,
    source: str = "local",
    run_id: str | None = None,
    level: str | None = None,
    stream: Any | None = None,
) -> tuple[logging.Logger, str]:
    """Configure a structured logger. Returns (logger, run_id)."""
    rid = run_id or os.environ.get("EXTRA_RUN_ID") or new_run_id(service)
    log_level = (level or os.environ.get("EXTRA_LOG_LEVEL") or "INFO").upper()
    logger = logging.getLogger(f"extra.{service}")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        StructuredJsonFormatter(service=service, source=source, run_id=rid)
    )
    logger.addHandler(handler)
    return logger, rid


def log_event(
    logger: logging.Logger,
    level: int,
    msg: str,
    **fields: Any,
) -> None:
    """Log with optional structured fields (entity_id, fonte, etc.)."""
    logger.log(level, msg, extra=fields)


def assert_record_schema(record: dict[str, Any]) -> list[str]:
    """Return list of missing required fields (empty = OK)."""
    required = ("ts", "level", "service", "source", "run_id", "msg")
    return [k for k in required if k not in record or record[k] in (None, "")]


def contains_secret_leak(text: str) -> bool:
    """True if text still matches a secret pattern (for tests / scanners)."""
    return any(p.search(text) for p in _SECRET_PATTERNS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Emit structured JSON logs (DoD §23) and verify schema/redaction."
    )
    p.add_argument("--service", default="extra-cli")
    p.add_argument("--source", default="local")
    p.add_argument("--run-id", default=None)
    p.add_argument("--demo", action="store_true", help="Emit sample lines to stdout")
    p.add_argument("--self-check", action="store_true", help="Validate schema + redaction")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    import io

    buf = io.StringIO()
    logger, rid = setup_structured_logger(
        service=args.service,
        source=args.source,
        run_id=args.run_id,
        stream=buf if args.self_check else sys.stdout,
    )
    log_event(logger, logging.INFO, "structured logging active", event="boot")
    log_event(
        logger,
        logging.WARNING,
        "sample with secret password=super-secret-value token=abc",
        event="redaction_demo",
    )
    log_event(
        logger,
        logging.ERROR,
        "dsn leak postgres://user:pass@localhost:5432/db",
        event="redaction_demo",
    )

    if args.self_check:
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        parsed = [json.loads(ln) for ln in lines]
        missing = []
        for rec in parsed:
            missing.extend(assert_record_schema(rec))
        leaks = [rec for rec in parsed if contains_secret_leak(json.dumps(rec))]
        # Also ensure redacted text in msg
        redacted_ok = all(
            "super-secret-value" not in json.dumps(r)
            and "user:pass@" not in json.dumps(r)
            for r in parsed
        )
        result = {
            "ok": not missing and not leaks and redacted_ok and len(parsed) >= 3,
            "run_id": rid,
            "records": len(parsed),
            "missing_fields": missing,
            "secret_leaks": len(leaks),
            "redacted_ok": redacted_ok,
            "sample": parsed[0] if parsed else None,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 2

    if args.demo or True:
        # already emitted to stdout when not self-check
        if args.json:
            print(json.dumps({"run_id": rid, "service": args.service}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
