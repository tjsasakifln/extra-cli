"""STUB: Exception classes for PNCP crawl modules.

Minimal definitions to enable imports from exceptions.
Full implementation deferred.
"""

from __future__ import annotations


class PNCPAPIError(Exception):
    """Base exception for PNCP API errors."""

    def __init__(self, message: str = "PNCP API error"):
        self.message = message
        super().__init__(self.message)


class PNCPRateLimitError(PNCPAPIError):
    """Raised when PNCP rate limit persists after retries."""

    def __init__(self, message: str = "PNCP rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message)


__all__ = [
    "PNCPAPIError",
    "PNCPRateLimitError",
]
