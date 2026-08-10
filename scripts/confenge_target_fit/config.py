"""Runtime configuration for target-fit continuous refresh.

Conservative defaults sized for a single VPS co-located with PNCP ingestion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


@dataclass(frozen=True)
class TargetFitRefreshConfig:
    """All knobs are env-overridable; defaults prefer safety over throughput."""

    # Modes: SHADOW | ACTIVE | CANARY | AUTO_PAUSE
    async_mode: str = "SHADOW"

    # Worker backpressure
    workers: int = 1  # sequential claim loop; raise carefully
    batch_size: int = 50
    lock_ttl_seconds: int = 300
    max_attempts: int = 5
    base_backoff_seconds: float = 30.0
    max_backoff_seconds: float = 3600.0

    # CDC
    cdc_lookback_minutes: int = 180
    cdc_max_companies_per_cycle: int = 5000

    # Freshness (watermark lag, not blind wall-clock TTL)
    max_watermark_lag_seconds: int = 7200  # 2h → DEGRADED
    stale_blocks_send: bool = True

    # Reconciliation
    reconcile_page_size: int = 500

    # Canary (ACTIVE only applies for company_key hash % 100 < canary_percent)
    canary_percent: int = 5

    # Anomaly guards (fraction of class distribution change in one cycle)
    anomaly_class_delta_fraction: float = 0.25
    anomaly_min_population: int = 200
    anomaly_auto_pause: bool = True

    # Priority fairness: every N high-priority claims, process 1 low-priority
    fairness_every: int = 10

    # DSN resolution
    state_dsn_env: str = "LOCAL_DATALAKE_DSN"
    source_dsn_env: str = "LOCAL_DATALAKE_DSN"

    # Artifacts (runtime; not committed daily dumps)
    artifact_root: str = "artifacts/confenge/target-fit"

    # SLO documentation value (not enforced as hard kill)
    reclass_slo_minutes: int = 30

    @classmethod
    def from_env(cls) -> TargetFitRefreshConfig:
        return cls(
            async_mode=_str("TARGET_FIT_ASYNC_MODE", "SHADOW").upper(),
            workers=max(1, _int("TARGET_FIT_WORKERS", 1)),
            batch_size=max(1, _int("TARGET_FIT_BATCH_SIZE", 50)),
            lock_ttl_seconds=max(30, _int("TARGET_FIT_LOCK_TTL_SECONDS", 300)),
            max_attempts=max(1, _int("TARGET_FIT_MAX_ATTEMPTS", 5)),
            base_backoff_seconds=_float("TARGET_FIT_BASE_BACKOFF_SECONDS", 30.0),
            max_backoff_seconds=_float("TARGET_FIT_MAX_BACKOFF_SECONDS", 3600.0),
            cdc_lookback_minutes=max(1, _int("TARGET_FIT_CDC_LOOKBACK_MINUTES", 180)),
            cdc_max_companies_per_cycle=max(
                1, _int("TARGET_FIT_CDC_MAX_COMPANIES", 5000)
            ),
            max_watermark_lag_seconds=max(
                60, _int("TARGET_FIT_MAX_WATERMARK_LAG_SECONDS", 7200)
            ),
            stale_blocks_send=_str("TARGET_FIT_STALE_BLOCKS_SEND", "1")
            not in {"0", "false", "False", "no"},
            reconcile_page_size=max(10, _int("TARGET_FIT_RECONCILE_PAGE_SIZE", 500)),
            canary_percent=max(0, min(100, _int("TARGET_FIT_CANARY_PERCENT", 5))),
            anomaly_class_delta_fraction=_float(
                "TARGET_FIT_ANOMALY_CLASS_DELTA", 0.25
            ),
            anomaly_min_population=_int("TARGET_FIT_ANOMALY_MIN_POP", 200),
            anomaly_auto_pause=_str("TARGET_FIT_ANOMALY_AUTO_PAUSE", "1")
            not in {"0", "false", "False", "no"},
            fairness_every=max(1, _int("TARGET_FIT_FAIRNESS_EVERY", 10)),
            state_dsn_env=_str("TARGET_FIT_STATE_DSN_ENV", "LOCAL_DATALAKE_DSN"),
            source_dsn_env=_str("TARGET_FIT_SOURCE_DSN_ENV", "LOCAL_DATALAKE_DSN"),
            artifact_root=_str(
                "TARGET_FIT_ARTIFACT_ROOT", "artifacts/confenge/target-fit"
            ),
            reclass_slo_minutes=max(5, _int("TARGET_FIT_RECLASS_SLO_MINUTES", 30)),
        )

    def resolve_state_dsn(self, explicit: str | None = None) -> str:
        if explicit:
            return explicit
        for key in (
            "CONFENGE_TARGET_FIT_STATE_DSN",
            "CONFENGE_COMMERCIAL_STATE_DSN",
            self.state_dsn_env,
            "LOCAL_DATALAKE_DSN",
            "DATABASE_URL",
        ):
            val = os.environ.get(key)
            if val:
                return val
        raise RuntimeError(
            "No state DSN. Set CONFENGE_TARGET_FIT_STATE_DSN or LOCAL_DATALAKE_DSN."
        )

    def resolve_source_dsn(self, explicit: str | None = None) -> str:
        if explicit:
            return explicit
        for key in (
            "CONFENGE_TARGET_FIT_SOURCE_DSN",
            "CONFENGE_UNIVERSE_DSN",
            "CONFENGE_COMMERCIAL_SOURCE_DSN",
            self.source_dsn_env,
            "LOCAL_DATALAKE_DSN",
            "DATABASE_URL",
        ):
            val = os.environ.get(key)
            if val:
                return val
        raise RuntimeError(
            "No source DSN. Set CONFENGE_TARGET_FIT_SOURCE_DSN or LOCAL_DATALAKE_DSN."
        )
