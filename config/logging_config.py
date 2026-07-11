"""Centralized logging configuration with JSON structured output.

Provides:
    - JSON-formatted log output for journald/systemd integration
    - Correlation ID propagation via contextvars for request tracing
    - Log rotation for production environments
    - Configurable log levels per module
    - Integration point for health_check.py

Usage:
    from config.logging_config import get_logger, set_correlation_id

    logger = get_logger(__name__)
    set_correlation_id()
    logger.info("Operation started", extra={"extra_data": {"key": "value"}})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Correlation ID support  (contextvars — thread-safe, async-safe)
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation ID (empty string if none set)."""
    return _correlation_id.get()


def set_correlation_id(cid: str | None = None) -> str:
    """Set the correlation ID for the current context.

    Args:
        cid: Explicit correlation ID (e.g. from an incoming request).
             If ``None``, a new 12-char hex ID is generated.

    Returns:
        The active correlation ID.
    """
    if cid is None:
        cid = uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


def reset_correlation_id() -> None:
    """Clear the correlation ID from the current context."""
    _correlation_id.set("")


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Format log records as newline-delimited JSON.

    Every log record produces a single JSON line with these fields:

    =============== ========================================================
    Field           Description
    =============== ========================================================
    ``timestamp``   ISO-8601 UTC
    ``level``       DEBUG, INFO, WARNING, ERROR, CRITICAL
    ``module``      Logger name (typically ``__name__``)
    ``correlation_id`` Current context correlation ID
    ``message``     Formatted log message
    ``extra_data``  Optional structured dict (from ``extra={}``)
    ``exc_info``    Exception traceback (only on ERROR+ if ``exc_info=True``)
    =============== ========================================================
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=datetime.UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "correlation_id": get_correlation_id() or "",
            "message": record.getMessage(),
        }

        # Include extra_data if provided by the caller
        if hasattr(record, "extra_data") and record.extra_data:
            try:
                log_entry["extra_data"] = record.extra_data
            except Exception:
                log_entry["extra_data"] = str(record.extra_data)

        # Include exception traceback for ERROR+
        if record.exc_info and record.exc_info[0] is not None:
            try:
                log_entry["exc_info"] = self.formatException(record.exc_info)
            except Exception:
                log_entry["exc_info"] = "Formatting error"

        try:
            return json.dumps(log_entry, ensure_ascii=False, default=str)
        except (TypeError, ValueError, OverflowError) as e:
            # Fallback: emit simplified record if serialization fails
            fallback = {
                "timestamp": datetime.fromtimestamp(record.created, tz=datetime.UTC).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "correlation_id": get_correlation_id() or "",
                "message": record.getMessage(),
                "_serialization_error": str(e),
            }
            return json.dumps(fallback, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

_LOG_DIR = os.environ.get(
    "LOG_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "logs"),
)
_DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
_LOG_FORMAT = os.environ.get("LOG_FORMAT", "json")
_LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
_LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """Return a configured logger instance.

    Args:
        name: Logger name (use ``__name__`` from the calling module).
        level: Override log level.  Defaults to ``LOG_LEVEL`` env var or ``INFO``.

    Returns:
        A ``logging.Logger`` that outputs JSON-structured records.
    """
    logger = logging.getLogger(name)
    effective_level = (level or _DEFAULT_LOG_LEVEL).upper()
    logger.setLevel(getattr(logging, effective_level, logging.INFO))

    # Avoid duplicate handlers on repeated calls
    if not logger.handlers:
        if _LOG_FORMAT == "json":
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            )

        app_env = os.environ.get("APP_ENV", "dev")
        if app_env == "prod":
            # Production: file with rotation
            log_file = os.path.join(_LOG_DIR, f"{name.replace('.', '_')}.log")
            try:
                os.makedirs(_LOG_DIR, exist_ok=True)
                handler: logging.Handler = logging.handlers.RotatingFileHandler(
                    filename=log_file,
                    maxBytes=_LOG_MAX_BYTES,
                    backupCount=_LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
            except (OSError, PermissionError, FileNotFoundError) as e:
                # Fallback to stderr if file rotation setup fails
                handler = logging.StreamHandler(sys.stderr)
                handler.setLevel(logging.DEBUG)
                handler.setFormatter(
                    logging.Formatter(
                        "LOG_FILE_FAILURE[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                    ),
                )
                # Emit a one-time warning via the handler itself
                handler.format(
                    logging.LogRecord(
                        name, logging.WARNING, __file__, 0,
                        "File logging unavailable (%s) — falling back to stderr", (str(e),),
                        None, None,
                    ),
                )
        else:
            # Development: stderr (captured by systemd/journald in service mode)
            handler = logging.StreamHandler(sys.stderr)

        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
