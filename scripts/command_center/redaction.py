"""Secret redaction for logs and API responses."""

from __future__ import annotations

import re
from typing import Any

# Patterns that often carry credentials or full DSNs.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(postgresql|postgres|mysql|mongodb(\+srv)?)://[^\s\"']+"),
    re.compile(r"(?i)(dsn|database_url|local_datalake_dsn)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----)[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----)"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)ghp_[A-Za-z0-9]{20,}"),
)


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    sensitive_keys = {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "dsn",
        "database_url",
        "local_datalake_dsn",
        "client_ready_dsn",
        "source_dsn",
    }
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        lk = str(key).lower()
        if lk in sensitive_keys or any(s in lk for s in ("password", "secret", "token", "dsn")):
            cleaned[key] = "[REDACTED]" if value not in (None, "", []) else value
        elif isinstance(value, dict):
            cleaned[key] = redact_mapping(value)
        elif isinstance(value, str):
            cleaned[key] = redact_text(value)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_mapping(v) if isinstance(v, dict) else redact_text(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def env_presence(name: str) -> str:
    """Return status of a sensitive env var without revealing content."""
    import os

    raw = os.environ.get(name)
    if raw is None or raw == "":
        return "ausente"
    # Cheap validity heuristics without exposing value
    if name.upper().endswith("DSN") or "DATABASE" in name.upper():
        if "://" not in raw:
            return "inválida"
        return "configurada"
    if len(raw.strip()) < 4:
        return "inválida"
    return "configurada"
