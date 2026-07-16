"""Base HTTP client and shared types for multi-source crawling.

Provides ``BaseHTTPClient`` with retry, circuit breaker, and Prometheus metrics,
plus legacy type definitions (``SourceCapability``, ``SourceMetadata``, etc.)
preserved for backward compatibility.
"""

from scripts.crawl.clients.base.base import (
    BaseHTTPClient,
    BaseHTTPError,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    HTTPClientError,
    HTTPRetryableError,
    InProcessCircuitBreaker,
    RetryConfig,
    SourceCapability,
    SourceMetadata,
    SourceStatus,
    UnifiedProcurement,
)

__all__ = [
    "BaseHTTPClient",
    "BaseHTTPError",
    "CircuitBreakerConfig",
    "CircuitBreakerOpen",
    "HTTPClientError",
    "HTTPRetryableError",
    "InProcessCircuitBreaker",
    "RetryConfig",
    "SourceCapability",
    "SourceMetadata",
    "SourceStatus",
    "UnifiedProcurement",
]
