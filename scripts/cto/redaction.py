"""Centralized secret redaction for logs, evidence JSON, HTML, and exceptions."""
from __future__ import annotations

import re
from typing import Any

# Patterns that look like API keys / tokens / passwords.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*['\"]?([^\s'\"\\]+)"),
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b", re.I),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]

REDACTED = "[REDACTED]"

# Env var names that must never appear with values in outputs.
SENSITIVE_ENV_KEYS = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "EXA_API_KEY",
        "CONTEXT7_API_KEY",
        "N8N_API_KEY",
        "CLICKUP_API_KEY",
        "DOM_SC_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    }
)


def redact_text(text: str) -> str:
    """Redact secrets from free text."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
        else:
            out = pat.sub(REDACTED, out)
    for key in SENSITIVE_ENV_KEYS:
        out = re.sub(
            rf"(?i)({re.escape(key)}\s*[=:]\s*)([^\s'\"\\]+)",
            rf"\1{REDACTED}",
            out,
        )
    return out


def redact_obj(value: Any) -> Any:
    """Deep-redact dict/list/str structures for evidence dumps."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).upper() in SENSITIVE_ENV_KEYS or any(
                s in str(k).lower() for s in ("api_key", "secret", "token", "password")
            ):
                cleaned[k] = REDACTED
            else:
                cleaned[k] = redact_obj(v)
        return cleaned
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def safe_exception_message(exc: BaseException) -> str:
    """Format exception without leaking secrets."""
    return redact_text(f"{type(exc).__name__}: {exc}")
