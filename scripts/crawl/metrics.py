"""Prometheus metrics for circuit breaker and crawl operations.

Replaces previous stub with real Prometheus counters, histograms, and gauges.
All metric names prefixed with ``ec_`` (Extra Consultoria) for namespace clarity.
"""

from __future__ import annotations

from enum import IntEnum

from prometheus_client import Counter, Gauge, Histogram


class CBStateEnum(IntEnum):
    """Circuit breaker state enum matching prometheus gauge values."""

    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


# --- Circuit breaker metrics ---

# Circuit breaker open duration (seconds) per source
CB_OPEN_DURATION = Histogram(
    "ec_cb_open_duration_seconds",
    "Duration circuit breaker remained open before transitioning",
    ["source"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, float("inf")),
)

# Circuit breaker state gauge (0=closed, 1=open, 2=half-open)
# NOTE: Despite the name, this is a Gauge, not an enum.
# circuit_breaker.py uses CIRCUIT_BREAKER_STATE.labels(...).set().
CB_STATE_GAUGE = Gauge(
    "ec_cb_state",
    "Circuit breaker state per source (0=closed, 1=open, 2=half-open)",
    ["source"],
)

# Backward-compatible alias: circuit_breaker.py imports CIRCUIT_BREAKER_STATE
# as a Gauge with .labels().set() interface.
CIRCUIT_BREAKER_STATE = CB_STATE_GAUGE

# --- Crawl operation metrics ---

CRAWL_DURATION = Histogram(
    "ec_crawl_duration_seconds",
    "Duration of crawl operations per source and phase",
    ["source", "phase"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, float("inf")),
)

CRAWL_RECORDS_TOTAL = Counter(
    "ec_crawl_records_total",
    "Total records processed per source and phase",
    ["source", "phase"],
)

CRAWL_ERRORS_TOTAL = Counter(
    "ec_crawl_errors_total",
    "Total errors encountered per source, phase, and error type",
    ["source", "phase", "error_type"],
)

CRAWL_BYTES_TOTAL = Counter(
    "ec_crawl_bytes_total",
    "Total bytes fetched per source",
    ["source"],
)

# --- HTTP client metrics ---

HTTP_REQUEST_DURATION = Histogram(
    "ec_http_request_duration_seconds",
    "HTTP request duration per source and status code",
    ["source", "method", "status"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf")),
)

HTTP_REQUESTS_TOTAL = Counter(
    "ec_http_requests_total",
    "Total HTTP requests per source and method",
    ["source", "method"],
)

HTTP_RETRIES_TOTAL = Counter(
    "ec_http_retries_total",
    "Total HTTP retries per source and status code",
    ["source", "status"],
)

# --- DLQ metrics ---

DLQ_COUNT = Gauge(
    "ec_dlq_count",
    "Current DLQ entries pending replay per source",
    ["source"],
)

DLQ_REPLAYED_TOTAL = Counter(
    "ec_dlq_replayed_total",
    "Total DLQ entries that have been replayed per source",
    ["source"],
)

DLQ_PURGED_TOTAL = Counter(
    "ec_dlq_purged_total",
    "Total DLQ entries purged per source",
    ["source"],
)

# --- Watermark metrics ---

WATERMARK_COMMITS_TOTAL = Counter(
    "ec_watermark_commits_total",
    "Total watermark commits per source",
    ["source"],
)

WATERMARK_AGE_SECONDS = Gauge(
    "ec_watermark_age_seconds",
    "Age of most recent watermark per source as seconds since epoch",
    ["source"],
)

# --- Connection pool metrics ---

POOL_ACTIVE_CONNECTIONS = Gauge(
    "ec_pool_active_connections",
    "Currently active connections per pool",
    ["pool_name"],
)

POOL_WAITING_REQUESTS = Gauge(
    "ec_pool_waiting_requests",
    "Currently waiting requests per pool",
    ["pool_name"],
)

__all__ = [
    "CBStateEnum",
    "CB_OPEN_DURATION",
    "CB_STATE_GAUGE",
    "CIRCUIT_BREAKER_STATE",
    "CRAWL_DURATION",
    "CRAWL_RECORDS_TOTAL",
    "CRAWL_ERRORS_TOTAL",
    "CRAWL_BYTES_TOTAL",
    "HTTP_REQUEST_DURATION",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_RETRIES_TOTAL",
    "DLQ_COUNT",
    "DLQ_REPLAYED_TOTAL",
    "DLQ_PURGED_TOTAL",
    "WATERMARK_COMMITS_TOTAL",
    "WATERMARK_AGE_SECONDS",
    "POOL_ACTIVE_CONNECTIONS",
    "POOL_WAITING_REQUESTS",
]
