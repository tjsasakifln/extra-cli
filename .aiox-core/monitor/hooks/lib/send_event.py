#!/usr/bin/env python3
"""
Send event to AIOX Monitor server.
Non-blocking with short timeout to avoid slowing Claude.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

SERVER_URL = os.environ.get("AIOX_MONITOR_URL", "http://localhost:4001")
TIMEOUT_MS = int(os.environ.get("AIOX_MONITOR_TIMEOUT_MS", "500"))


def validated_server_url(value: str) -> str | None:
    """Return a normalized HTTP(S) monitor URL, or None for unsafe input."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return value.rstrip("/")


def send_event(event_type: str, data: dict[str, Any]) -> bool:
    """
    Send event to AIOX Monitor server.

    Args:
        event_type: Hook event type (PreToolUse, PostToolUse, etc.)
        data: Event data from Claude hook

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        server_url = validated_server_url(SERVER_URL)
        if server_url is None:
            return False
        payload = json.dumps({
            "type": event_type,
            "timestamp": int(time.time() * 1000),
            "data": data
        }).encode("utf-8")

        req = urllib.request.Request(  # noqa: S310 - validated HTTP(S) URL with hostname
            f"{server_url}/events",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        urllib.request.urlopen(  # noqa: S310 - request URL validated above
            req, timeout=TIMEOUT_MS / 1000
        )
        return True

    except Exception:
        # Silent fail - never block Claude
        return False
