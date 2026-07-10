"""
Retry decorator with exponential backoff for HTTP calls.

Usage:
    from lib.retry import retry_on_failure

    @retry_on_failure(max_retries=3, base_delay=1.0)
    def fetch_data(url):
        return httpx.get(url)
"""
from __future__ import annotations

import functools
import logging
import time

logger = logging.getLogger(__name__)


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (Exception,),
    retryable_status_codes: tuple = (429, 500, 502, 503, 504),
):
    """Decorator for retrying HTTP calls with exponential backoff.

    Args:
        max_retries: Maximum number of retries (total attempts = max_retries + 1).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        retryable_status_codes: HTTP status codes that trigger a retry.

    Returns:
        Decorated function with retry logic.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    # Check for retryable HTTP status codes if result has status_code
                    if hasattr(result, "status_code") and result.status_code in retryable_status_codes:
                        if attempt < max_retries:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            logger.warning(
                                "[retry] %s returned %d, retrying in %.1fs (attempt %d/%d)",
                                func.__name__,
                                result.status_code,
                                delay,
                                attempt + 1,
                                max_retries,
                            )
                            time.sleep(delay)
                            continue
                    return result
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            "[retry] %s failed: %s, retrying in %.1fs (attempt %d/%d)",
                            func.__name__,
                            e,
                            delay,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(delay)
                    else:
                        raise
            # Should not reach here, but just in case
            if last_exception is not None:
                raise last_exception
            return None  # pragma: no cover
        return wrapper
    return decorator
