"""Exception hierarchy for crawl, transform, upsert, coverage, and config errors.

Each exception carries error_code, message, details, and a recoverable flag
to support structured error handling in data pipelines.

Retains backward-compatible aliases: PNCPAPIError, PNCPRateLimitError.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain exception hierarchy
# ---------------------------------------------------------------------------


class CrawlError(Exception):
    """Base for crawl-related failures (network, API, timeout, parse)."""

    def __init__(
        self,
        message: str = "Crawl operation failed",
        error_code: str = "CRAWL_ERROR",
        details: str | None = None,
        recoverable: bool = True,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(self.message)


class TransformError(Exception):
    """Base for data transformation / normalization failures."""

    def __init__(
        self,
        message: str = "Transform operation failed",
        error_code: str = "TRANSFORM_ERROR",
        details: str | None = None,
        recoverable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(self.message)


class UpsertError(Exception):
    """Base for database upsert / persistence failures."""

    def __init__(
        self,
        message: str = "Upsert operation failed",
        error_code: str = "UPSERT_ERROR",
        details: str | None = None,
        recoverable: bool = True,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(self.message)


class CoverageError(Exception):
    """Base for coverage assessment / validation failures."""

    def __init__(
        self,
        message: str = "Coverage check failed",
        error_code: str = "COVERAGE_ERROR",
        details: str | None = None,
        recoverable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(self.message)


class ConfigError(Exception):
    """Base for configuration / settings failures."""

    def __init__(
        self,
        message: str = "Configuration error",
        error_code: str = "CONFIG_ERROR",
        details: str | None = None,
        recoverable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# Backward-compatible aliases (original PNCP stubs)
# ---------------------------------------------------------------------------


class PNCPAPIError(CrawlError):
    """Backward-compatible alias: PNCP API error -> CrawlError."""

    def __init__(self, message: str = "PNCP API error"):
        super().__init__(message=message, error_code="PNCP_API_ERROR")


class PNCPRateLimitError(PNCPAPIError):
    """Backward-compatible alias: PNCP rate limit error."""

    def __init__(self, message: str = "PNCP rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message=message)


__all__ = [
    "ConfigError",
    "CoverageError",
    "CrawlError",
    "PNCPAPIError",
    "PNCPRateLimitError",
    "TransformError",
    "UpsertError",
]
