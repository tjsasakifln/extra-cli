"""Canonical HTTP resilience policy shared by adapters and real clients."""

from __future__ import annotations

import os
import random
import warnings
from dataclasses import dataclass


def _num(name: str, default: str, cast: type[int] | type[float], minimum: float = 0) -> int | float:
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser numerico, recebido {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}, recebido {value}")
    return value


@dataclass(frozen=True)
class HttpResiliencePolicy:
    """Single source of truth for transport retries/timeouts.

    Precedence (highest first):
    1. Explicit constructor / call-site values
    2. RESILIENCE_* environment variables
    3. Legacy PNCP_* environment variables (deprecated; emits warning)
    4. Built-in defaults
    """

    connect_timeout: float = 10.0
    read_timeout: float = 120.0
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.2
    retry_after_fallback: float = 60.0
    request_delay: float = 0.5
    transient_statuses: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})

    @classmethod
    def from_env(cls) -> HttpResiliencePolicy:
        legacy_used: list[str] = []

        def prefer(resilience_name: str, legacy_name: str, default: str, cast: type[int] | type[float], minimum: float = 0) -> int | float:
            if os.getenv(resilience_name) is not None:
                return _num(resilience_name, default, cast, minimum)
            if os.getenv(legacy_name) is not None:
                legacy_used.append(legacy_name)
                return _num(legacy_name, default, cast, minimum)
            return _num(resilience_name, default, cast, minimum)

        policy = cls(
            connect_timeout=float(prefer("RESILIENCE_CONNECT_TIMEOUT", "PNCP_CONNECT_TIMEOUT", "10", float, 0.1)),
            read_timeout=float(prefer("RESILIENCE_READ_TIMEOUT", "PNCP_READ_TIMEOUT", "120", float, 0.1)),
            max_retries=int(prefer("RESILIENCE_MAX_RETRIES", "PNCP_MAX_RETRIES", "5", int, 0)),
            base_delay=float(prefer("RESILIENCE_BASE_DELAY", "PNCP_RETRY_BASE_DELAY", "1", float, 0)),
            max_delay=float(prefer("RESILIENCE_MAX_DELAY", "PNCP_RETRY_MAX_DELAY", "60", float, 0)),
            jitter=float(prefer("RESILIENCE_JITTER", "PNCP_RETRY_JITTER", "0.2", float, 0)),
            retry_after_fallback=float(prefer("RESILIENCE_RATE_LIMIT_FALLBACK", "PNCP_RATE_LIMIT_FALLBACK", "60", float, 0)),
            request_delay=float(prefer("RESILIENCE_REQUEST_DELAY", "PNCP_REQUEST_DELAY", "0.5", float, 0)),
        )
        if legacy_used:
            warnings.warn(
                "Variaveis legadas deprecadas em uso: "
                + ", ".join(sorted(set(legacy_used)))
                + ". Prefira RESILIENCE_*. Mapeamento temporario ativo.",
                DeprecationWarning,
                stacklevel=2,
            )
        if policy.max_delay < policy.base_delay:
            raise ValueError("max_delay deve ser >= base_delay")
        if policy.jitter > 1:
            raise ValueError("jitter deve estar entre 0 e 1")
        return policy

    def timeout_tuple(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)

    def retry_delay(self, attempt: int, retry_after: float | None = None, *, rng: random.Random | None = None) -> float:
        if retry_after is not None and retry_after >= 0:
            return float(min(self.max_delay, float(retry_after)))
        generator = rng or random.Random()  # noqa: S311 — retry jitter is not security-sensitive
        expo = float(min(self.max_delay, self.base_delay * (2**attempt)))
        if self.jitter <= 0:
            return expo
        low = max(0.0, expo * (1 - self.jitter))
        high = expo * (1 + self.jitter)
        sample: float = float(generator.uniform(low, high))
        return float(min(self.max_delay, sample))
