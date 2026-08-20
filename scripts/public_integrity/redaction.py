"""Redact CNPJ from logs, public fixtures and exports."""

from __future__ import annotations

import logging
import re
from typing import Any

REDACTED = "[REDACTED_CNPJ]"
CNPJ_FORMATTED = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CNPJ_DIGITS = re.compile(r"\d{14}")


def redact_text(text: str) -> str:
    redacted = CNPJ_FORMATTED.sub(REDACTED, str(text))
    return CNPJ_DIGITS.sub(REDACTED, redacted)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy a payload with queried_cnpj and any 14-digit token redacted."""
    copied = redact_value(payload)
    if isinstance(copied, dict) and "queried_cnpj" in copied:
        copied["queried_cnpj"] = REDACTED
    return copied


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: redact_text(str(val)) for key, val in record.args.items()}
            else:
                record.args = tuple(redact_text(str(arg)) for arg in record.args)
        return True


def install_log_redaction(logger: logging.Logger | None = None) -> logging.Logger:
    target = logger or logging.getLogger("scripts.public_integrity")
    if not any(isinstance(existing, RedactingFilter) for existing in target.filters):
        target.addFilter(RedactingFilter())
    return target
