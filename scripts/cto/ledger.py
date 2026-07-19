"""Append-only ledger for CTO Autopilot transitions and API usage."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.paths import ledger_path
from scripts.cto.redaction import redact_obj


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_ledger(
    event_type: str,
    payload: dict[str, Any],
    *,
    root: Path | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Append a redacted event to the ledger. Returns the event."""
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = redact_obj(payload)
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    event = {
        "ts": _utc_now(),
        "event_type": event_type,
        "cycle_id": cycle_id,
        "payload_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "payload": body,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def read_ledger(root: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    path = ledger_path(root)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
