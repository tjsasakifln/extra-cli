#!/usr/bin/env python3
"""Durable systemd OnFailure recorder with best-effort webhook delivery.

This module intentionally uses only the Python standard library. It records and
fsyncs the failure before touching the network, so a broken application venv or
webhook cannot erase the alert evidence or fail the OnFailure unit.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path("/var/lib/extra-consultoria/alerts/onfailure.jsonl")


def _append_durable(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record_service_failure(
    *,
    service: str,
    host: str,
    ledger: Path,
    webhook_url: str | None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    event = {
        "at": at,
        "event": "service_failed",
        "service": service,
        "host": host,
        "project": "extra-cli",
    }
    _append_durable(ledger, event)

    result: dict[str, Any] = {"durable": True, "delivered": False, "ledger": str(ledger)}
    if not webhook_url:
        result["delivery"] = "not_configured"
        return result

    if urllib.parse.urlsplit(webhook_url).scheme.lower() not in {"http", "https"}:
        reason = "unsupported webhook URL scheme"
        _append_durable(
            ledger,
            {
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "event": "delivery_failed",
                "service": service,
                "host": host,
                "channel": "webhook",
                "reason": reason,
            },
        )
        result.update({"delivery": "failed", "reason": reason})
        return result

    request = urllib.request.Request(  # noqa: S310 - scheme allowlisted above
        webhook_url,
        data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            status = int(getattr(response, "status", 200))
        if 200 <= status < 300:
            result.update({"delivered": True, "delivery": "webhook", "http_status": status})
            return result
        reason = f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        reason = f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = f"{type(exc).__name__}: {exc}"

    _append_durable(
        ledger,
        {
            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "event": "delivery_failed",
            "service": service,
            "host": host,
            "channel": "webhook",
            "reason": reason,
        },
    )
    result.update({"delivery": "failed", "reason": reason})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(os.getenv("ALERT_ONFAILURE_LEDGER", str(DEFAULT_LEDGER))),
    )
    args = parser.parse_args(argv)
    result = record_service_failure(
        service=args.service,
        host=args.host,
        ledger=args.ledger,
        webhook_url=os.getenv("WEBHOOK_URL"),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
