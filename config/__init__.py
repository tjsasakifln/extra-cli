"""Config package — re-exports settings and constants for all crawler modules.

``config.constants`` holds static defaults (RetryConfig, circuit breakers, timing).
``config.settings`` holds env-based settings (paths, URLs, credentials).

``__init__`` re-exports the names each crawler module expects so that::

    from config import RetryConfig, PNCP_TIMEOUT_PER_MODALITY, ...

works without errors.
"""

from config.constants import (
    BRASILAPI_CIRCUIT_BREAKER_COOLDOWN,
    # Circuit breaker — BrasilAPI
    BRASILAPI_CIRCUIT_BREAKER_THRESHOLD,
    CB_REDIS_TTL,
    COMPRASGOV_CIRCUIT_BREAKER_COOLDOWN,
    # Circuit breaker — ComprasGov
    COMPRASGOV_CIRCUIT_BREAKER_THRESHOLD,
    # Modalidades
    DEFAULT_MODALIDADES,
    IBGE_CIRCUIT_BREAKER_COOLDOWN,
    # Circuit breaker — IBGE
    IBGE_CIRCUIT_BREAKER_THRESHOLD,
    # Item inspection
    ITEM_INSPECTION_TIMEOUT,
    MODALIDADES_EXCLUIDAS,
    PCP_CIRCUIT_BREAKER_COOLDOWN,
    # Circuit breaker — PCP
    PCP_CIRCUIT_BREAKER_THRESHOLD,
    PNCP_BATCH_DELAY_S,
    PNCP_BATCH_SIZE,
    PNCP_CIRCUIT_BREAKER_COOLDOWN,
    # Circuit breaker — PNCP
    PNCP_CIRCUIT_BREAKER_THRESHOLD,
    PNCP_MODALITY_RETRY_BACKOFF,
    # PNCP timing / concurrency
    PNCP_TIMEOUT_PER_MODALITY,
    PNCP_TIMEOUT_PER_UF,
    PNCP_TIMEOUT_PER_UF_DEGRADED,
    # Redis
    USE_REDIS_CIRCUIT_BREAKER,
    # RetryConfig dataclass
    RetryConfig,
)

# Re-export env-based settings that crawler modules import.
# PNCP_MAX_PAGES is defined in settings.py with env-var override.
from config.settings import PNCP_MAX_PAGES
