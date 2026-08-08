"""Warmbly-compatible HMAC-SHA256 for confenge.outcome.v1.

Header format (Warmbly PR #4 outcomes.go):
  X-Warmbly-Signature: t=<unix>,v1=<hex(hmac_sha256(secret, "<unix>." + body))>
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def sign_outcome_hmac(secret: str, ts_unix: int, body: bytes) -> str:
    msg = f"{ts_unix}.".encode() + body
    digest = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={ts_unix},v1={digest}"


def parse_signature_header(header: str) -> tuple[int | None, str | None]:
    t_unix: int | None = None
    sig: str | None = None
    for part in (header or "").split(","):
        part = part.strip()
        if part.startswith("t="):
            try:
                t_unix = int(part[2:])
            except ValueError:
                t_unix = None
        elif part.startswith("v1="):
            sig = part[3:]
    return t_unix, sig


def verify_outcome_hmac(
    secret: str,
    header: str,
    body: bytes,
    *,
    now: float | None = None,
    max_skew_seconds: int = 300,
) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty when ok."""
    if not secret:
        return False, "missing_secret"
    t_unix, sig = parse_signature_header(header)
    if t_unix is None or not sig:
        return False, "malformed_signature_header"
    now_ts = time.time() if now is None else float(now)
    skew = abs(now_ts - float(t_unix))
    if skew > max_skew_seconds:
        return False, f"timestamp_skew:{int(skew)}s"
    expected_header = sign_outcome_hmac(secret, t_unix, body)
    _, expected_sig = parse_signature_header(expected_header)
    if expected_sig is None:
        return False, "internal_sign_error"
    if not hmac.compare_digest(expected_sig, sig):
        return False, "bad_signature"
    return True, ""


def redact_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact PII-ish fields before logging."""
    redacted = dict(payload)
    for key in ("contact_email", "email", "phone", "name"):
        if key in redacted and redacted[key]:
            redacted[key] = "[REDACTED]"
    meta = redacted.get("metadata")
    if isinstance(meta, dict):
        m2 = dict(meta)
        for key in ("contact_email", "email", "phone", "raw_body", "message_body"):
            if key in m2 and m2[key]:
                m2[key] = "[REDACTED]"
        redacted["metadata"] = m2
    return redacted
