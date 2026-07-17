"""Central validated configuration for resilient collection."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from scripts.crawl.resilience.http_policy import HttpResiliencePolicy

ResilienceEnvironment = Literal["test", "fixture", "development", "staging", "production"]
ExecutionMode = Literal["fixture", "live", "canary"]

LIVE_ENVIRONMENTS = frozenset({"development", "staging", "production"})
NON_LIVE_ENVIRONMENTS = frozenset({"test", "fixture"})


def _number(name: str, default: str, cast: type[int] | type[float], minimum: float = 0) -> int | float:
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser numerico, recebido {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}, recebido {value}")
    return value


def resolve_environment(explicit: str | None = None) -> ResilienceEnvironment:
    raw = (explicit or os.getenv("RESILIENCE_ENV") or "development").strip().lower()
    if raw not in {"test", "fixture", "development", "staging", "production"}:
        raise ValueError(f"RESILIENCE_ENV invalido: {raw!r}")
    return raw  # type: ignore[return-value]


def is_live_environment(env: str) -> bool:
    return env in LIVE_ENVIRONMENTS


@dataclass(frozen=True)
class ResilienceConfig:
    environment: ResilienceEnvironment
    execution_mode: ExecutionMode
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
    state_root: Path
    checkpoint_path: Path
    raw_path: Path
    dlq_path: Path
    evidence_path: Path
    ops_path: Path
    breaker_path: Path
    host: str = field(default_factory=lambda: socket.gethostname())
    require_db: bool = True

    @property
    def http_policy(self) -> HttpResiliencePolicy:
        return HttpResiliencePolicy(
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            max_retries=self.max_retries,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            jitter=self.jitter,
            retry_after_fallback=self.rate_limit_fallback,
            request_delay=self.request_delay,
        )

    def with_execution_mode(self, mode: ExecutionMode) -> ResilienceConfig:
        require_db = mode == "live" and is_live_environment(self.environment)
        return replace(self, execution_mode=mode, require_db=require_db)

    def artifact_metadata(self, *, source: str, run_id: str, commit_sha: str | None = None) -> dict[str, str]:
        from scripts.crawl.run_evidence import get_git_meta

        git = get_git_meta()
        return {
            "environment": self.environment,
            "execution_mode": self.execution_mode,
            "source": source,
            "run_id": run_id,
            "host": self.host,
            "commit_sha": commit_sha or str(git.get("git_sha") or git.get("commit") or "unknown"),
            "executor": os.getenv("RESILIENCE_EXECUTOR") or os.getenv("USER") or "unknown",
        }

    @classmethod
    def from_env(
        cls,
        *,
        environment: str | None = None,
        execution_mode: ExecutionMode | None = None,
        state_root: Path | None = None,
    ) -> ResilienceConfig:
        env = resolve_environment(environment)
        # Prefer explicit policy (re-reads env at call time — never import-time capture).
        policy = HttpResiliencePolicy.from_env()
        root = state_root or Path(os.getenv("RESILIENCE_STATE_PATH", "output/resilience"))
        # Environment isolation: never share live paths with fixture/test.
        env_root = root / env
        mode: ExecutionMode = execution_mode or ("fixture" if env in NON_LIVE_ENVIRONMENTS else "live")
        require_db = mode == "live" and env in LIVE_ENVIRONMENTS
        # Allow override for integration tests under test env with real DB.
        if os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {"1", "true", "yes"}:
            require_db = True
        if os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {"0", "false", "no"}:
            require_db = False

        cfg = cls(
            environment=env,
            execution_mode=mode,
            connect_timeout=policy.connect_timeout,
            read_timeout=policy.read_timeout,
            max_retries=policy.max_retries,
            base_delay=policy.base_delay,
            max_delay=policy.max_delay,
            jitter=policy.jitter,
            rate_limit_fallback=policy.retry_after_fallback,
            request_delay=policy.request_delay,
            page_size=int(_number("RESILIENCE_PAGE_SIZE", "50", int, 1)),
            max_pages=int(_number("RESILIENCE_MAX_PAGES", "200", int, 1)),
            circuit_breaker_threshold=int(_number("RESILIENCE_CIRCUIT_BREAKER_THRESHOLD", "5", int, 1)),
            circuit_breaker_cooldown=float(_number("RESILIENCE_CIRCUIT_BREAKER_COOLDOWN", "300", float, 1)),
            daily_request_budget=int(_number("RESILIENCE_DAILY_REQUEST_BUDGET", "5000", int, 1)),
            freshness_sla_hours=int(_number("RESILIENCE_FRESHNESS_SLA_HOURS", "24", int, 1)),
            state_root=root,
            checkpoint_path=Path(os.getenv("RESILIENCE_CHECKPOINT_PATH", str(env_root / "checkpoints"))),
            raw_path=Path(os.getenv("RESILIENCE_RAW_PATH", str(env_root / "raw"))),
            dlq_path=Path(os.getenv("RESILIENCE_DLQ_PATH", str(env_root / "dlq"))),
            evidence_path=Path(os.getenv("RESILIENCE_EVIDENCE_PATH", str(env_root / "evidence"))),
            ops_path=Path(os.getenv("RESILIENCE_OPS_PATH", str(env_root / "ops"))),
            breaker_path=Path(os.getenv("RESILIENCE_BREAKER_PATH", str(env_root / "breakers"))),
            require_db=require_db,
        )
        if cfg.max_delay < cfg.base_delay:
            raise ValueError("RESILIENCE_MAX_DELAY deve ser >= RESILIENCE_BASE_DELAY")
        if cfg.jitter > 1:
            raise ValueError("RESILIENCE_JITTER deve estar entre 0 e 1")
        return cfg
