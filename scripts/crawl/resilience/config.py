"""Central validated configuration for resilient collection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _number(name: str, default: str, cast: type[int] | type[float], minimum: float = 0) -> int | float:
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser numerico, recebido {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}, recebido {value}")
    return value


@dataclass(frozen=True)
class ResilienceConfig:
    connect_timeout: float
    read_timeout: float
    max_retries: int
    base_delay: float
    max_delay: float
    jitter: float
    rate_limit_fallback: float
    request_delay: float
    page_size: int
    max_pages: int
    circuit_breaker_threshold: int
    circuit_breaker_cooldown: float
    daily_request_budget: int
    freshness_sla_hours: int
    checkpoint_path: Path
    raw_path: Path
    dlq_path: Path
    evidence_path: Path
    ops_path: Path

    @classmethod
    def from_env(cls) -> ResilienceConfig:
        state_root = Path(os.getenv("RESILIENCE_STATE_PATH", "output/resilience"))
        cfg = cls(
            connect_timeout=float(_number("RESILIENCE_CONNECT_TIMEOUT", "10", float, 0.1)),
            read_timeout=float(_number("RESILIENCE_READ_TIMEOUT", "120", float, 0.1)),
            max_retries=int(_number("RESILIENCE_MAX_RETRIES", "5", int, 0)),
            base_delay=float(_number("RESILIENCE_BASE_DELAY", "1", float, 0)),
            max_delay=float(_number("RESILIENCE_MAX_DELAY", "60", float, 0)),
            jitter=float(_number("RESILIENCE_JITTER", "0.2", float, 0)),
            rate_limit_fallback=float(_number("RESILIENCE_RATE_LIMIT_FALLBACK", "60", float, 0)),
            request_delay=float(_number("RESILIENCE_REQUEST_DELAY", "0.5", float, 0)),
            page_size=int(_number("RESILIENCE_PAGE_SIZE", "50", int, 1)),
            max_pages=int(_number("RESILIENCE_MAX_PAGES", "200", int, 1)),
            circuit_breaker_threshold=int(_number("RESILIENCE_CIRCUIT_BREAKER_THRESHOLD", "5", int, 1)),
            circuit_breaker_cooldown=float(_number("RESILIENCE_CIRCUIT_BREAKER_COOLDOWN", "300", float, 1)),
            daily_request_budget=int(_number("RESILIENCE_DAILY_REQUEST_BUDGET", "5000", int, 1)),
            freshness_sla_hours=int(_number("RESILIENCE_FRESHNESS_SLA_HOURS", "24", int, 1)),
            checkpoint_path=Path(os.getenv("RESILIENCE_CHECKPOINT_PATH", str(state_root / "checkpoints"))),
            raw_path=Path(os.getenv("RESILIENCE_RAW_PATH", str(state_root / "raw"))),
            dlq_path=Path(os.getenv("RESILIENCE_DLQ_PATH", str(state_root / "dlq"))),
            evidence_path=Path(os.getenv("RESILIENCE_EVIDENCE_PATH", str(state_root / "evidence"))),
            ops_path=Path(os.getenv("RESILIENCE_OPS_PATH", str(state_root / "ops"))),
        )
        if cfg.max_delay < cfg.base_delay:
            raise ValueError("RESILIENCE_MAX_DELAY deve ser >= RESILIENCE_BASE_DELAY")
        if cfg.jitter > 1:
            raise ValueError("RESILIENCE_JITTER deve estar entre 0 e 1")
        return cfg
