"""Static constants for crawler modules — RetryConfig, circuit breakers, timing.

This file contains ALL non-env-based constants that crawler modules import
from the ``config`` package.  Env-based settings live in ``config/settings.py``.
Both are re-exported via ``config/__init__.py``.

Values here are safe defaults derived from production usage across
scripts/crawl/*.py.  They are tunable at deployment via settings.py /
environment variables if needed in the future (Story TD-5.4).
"""

from dataclasses import dataclass, field

# ============================================================================
# RetryConfig — exponential backoff dataclass
# ============================================================================


@dataclass
class RetryConfig:
    """Exponential-backoff retry configuration for PNCP HTTP clients.

    Used by:
    - ``scripts/crawl/retry.py``  → ``calculate_delay(attempt, config)``
    - ``scripts/crawl/async_client.py`` → ``AsyncPNCPClient(config=…)``
    - ``scripts/crawl/sync_client.py`` → ``PNCPClient(config=…)``
    - ``scripts/crawl/circuit_breaker.py`` → re-export only
    """

    base_delay: float = 2.0
    """Base delay in seconds (doubles each attempt)."""

    exponential_base: int = 2
    """Exponent base for backoff growth."""

    max_delay: float = 60.0
    """Maximum delay cap (never sleep longer than this)."""

    jitter: bool = True
    """Apply ±50% random jitter to prevent thundering herd."""

    connect_timeout: float = 10.0
    """Connection timeout for httpx (used in async_client.py)."""

    read_timeout: float = 30.0
    """Read timeout for httpx (used in async_client.py)."""

    max_retries: int = 3
    """Maximum number of retry attempts (used by both sync and async clients)."""

    timeout: float = 30.0
    """Total request timeout in seconds (used by sync_client.py)."""

    retryable_status_codes: tuple = field(default_factory=lambda: (429, 500, 502, 503, 504))
    """HTTP status codes that trigger a retry."""

    retryable_exceptions: tuple = field(default_factory=lambda: (TimeoutError, ConnectionError))
    """Exception types that trigger a retry."""


# ============================================================================
# Modalidades (publication modalities)
# ============================================================================

DEFAULT_MODALIDADES: list[int] = [4, 5, 6, 7]
"""Default PNCP modalities for search (aligned with INGESTION_MODALIDADES).

Codes:
    4 = Concorrencia
    5 = Concurso
    6 = Pregao Eletronico
    7 = Pregao Presencial
"""

MODALIDADES_EXCLUIDAS: set[int] = {8, 9, 14}
"""Modalities excluded from crawls (aligned with collect-report-data.py).

Codes:
     8 = Leilao
     9 = Dialogo Competitivo
    14 = Manifestacao de Interesse
"""


# ============================================================================
# Circuit Breaker Thresholds (threshold, cooldown_seconds)
# ============================================================================

# Primary sources — higher tolerance (5 failures, 60s cooldown)
PNCP_CIRCUIT_BREAKER_THRESHOLD: int = 5
PNCP_CIRCUIT_BREAKER_COOLDOWN: int = 60

PCP_CIRCUIT_BREAKER_THRESHOLD: int = 5
PCP_CIRCUIT_BREAKER_COOLDOWN: int = 60

COMPRASGOV_CIRCUIT_BREAKER_THRESHOLD: int = 5
COMPRASGOV_CIRCUIT_BREAKER_COOLDOWN: int = 60

# Secondary sources — lower tolerance (3 failures, 30s cooldown)
BRASILAPI_CIRCUIT_BREAKER_THRESHOLD: int = 3
BRASILAPI_CIRCUIT_BREAKER_COOLDOWN: int = 30

IBGE_CIRCUIT_BREAKER_THRESHOLD: int = 3
IBGE_CIRCUIT_BREAKER_COOLDOWN: int = 30


# ============================================================================
# PNCP Timing / Concurrency
# ============================================================================

PNCP_TIMEOUT_PER_MODALITY: float = 20.0
"""Per-modality timeout in seconds (safe default from retry._SAFE_PER_MODALITY)."""

PNCP_MODALITY_RETRY_BACKOFF: float = 2.0
"""Backoff between modality retries, in seconds."""

PNCP_TIMEOUT_PER_UF: float = 30.0
"""Per-UF timeout in seconds (safe default from retry._SAFE_PER_UF)."""

PNCP_TIMEOUT_PER_UF_DEGRADED: float = 45.0
"""Per-UF timeout when circuit breaker is degraded (50% headroom above normal)."""

PNCP_BATCH_SIZE: int = 5
"""Number of UFs per batch (aligned with INGESTION_BATCH_SIZE_UFS)."""

PNCP_BATCH_DELAY_S: float = 2.0
"""Delay between UF batches in seconds (aligned with INGESTION_BATCH_DELAY_S)."""


# ============================================================================
# Redis (shared circuit breaker across workers)
# ============================================================================

USE_REDIS_CIRCUIT_BREAKER: bool = False
"""Whether to use RedisCircuitBreaker instead of in-memory (opt-in, default off)."""

CB_REDIS_TTL: int = 300
"""TTL in seconds for Redis circuit breaker keys (5 minutes)."""


# ============================================================================
# Item inspection timeout (used by async_client.fetch_bid_items)
# ============================================================================

ITEM_INSPECTION_TIMEOUT: float = 10.0
"""Timeout in seconds for individual bid-item inspection requests."""
