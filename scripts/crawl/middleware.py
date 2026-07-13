"""Request middleware for distributed tracing.

Provides:
- timing: context manager to measure operation duration.
- generate_request_id: creates a unique request ID (uuid4).
- request_id_var: ContextVar for propagating the current request ID.
- StructuredLogRecord: helper for structured log entries.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def generate_request_id() -> str:
    """Generate a unique request identifier using uuid4."""
    return uuid.uuid4().hex


class timing:  # noqa: N801
    """Context manager that records wall-clock duration.

    Usage::

        with timing() as t:
            do_something()
        logger.info("took %.2f ms", t.ms)
    """

    def __init__(self) -> None:
        self.start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> timing:
        self.start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.elapsed = time.perf_counter() - self.start

    @property
    def ms(self) -> float:
        """Return elapsed time in milliseconds."""
        return self.elapsed * 1000

    @property
    def seconds(self) -> float:
        """Return elapsed time in seconds."""
        return self.elapsed


def structured_log(
    logger: logging.Logger,
    level: int,
    event: str,
    **extra: Any,
) -> None:
    """Emit a structured log record with extra fields.

    Args:
        logger: Logger instance.
        level: Log level (e.g. logging.INFO).
        event: Event name (e.g. "page_fetched").
        **extra: Additional key-value pairs attached as ``extra_data``.

    Usage::

        structured_log(logger, logging.INFO, "page_fetched",
                       url="...", status=200, elapsed_ms=42.3)
    """
    logger.log(
        level,
        "EVENT=%s %s",
        event,
        " ".join(f"{k}={v!r}" for k, v in extra.items()),
        extra={"extra_data": {"event": event, **extra}},
    )


__all__ = [
    "generate_request_id",
    "request_id_var",
    "structured_log",
    "timing",
]
