"""Environment and policy configuration for CTO Autopilot."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.cto.paths import policies_path, repo_root


def _load_dotenv(root: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Does not override existing env."""
    env_file = (root or repo_root()) / ".env"
    if not env_file.is_file():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        return


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    reasoning_effort: str = "high"
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    max_retries: int = 3

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class BudgetConfig:
    max_cycles_per_run: int = 1
    max_repair_attempts: int = 2
    max_daily_api_calls: int = 100
    max_daily_tokens: int = 500_000
    min_confidence: float = 0.55
    grok_max_turns: int = 30


@dataclass
class CTOConfig:
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    budgets: BudgetConfig = field(default_factory=BudgetConfig)
    policies: dict[str, Any] = field(default_factory=dict)
    root: Path = field(default_factory=repo_root)


def load_policies(root: Path | None = None) -> dict[str, Any]:
    path = policies_path(root)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_config(root: Path | None = None) -> CTOConfig:
    root = root or repo_root()
    _load_dotenv(root)
    policies = load_policies(root)
    budgets_pol = policies.get("budgets") or {}
    executor = policies.get("executor") or {}

    deepseek = DeepSeekConfig(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high"),
        max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
        timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120")),
        max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
    )
    budgets = BudgetConfig(
        max_cycles_per_run=int(
            os.getenv("CTO_MAX_CYCLES_PER_RUN", budgets_pol.get("max_cycles_per_run", 1))
        ),
        max_repair_attempts=int(
            os.getenv(
                "CTO_MAX_REPAIR_ATTEMPTS",
                budgets_pol.get("max_repair_attempts", executor.get("max_repair_attempts", 2)),
            )
        ),
        max_daily_api_calls=int(
            os.getenv("CTO_MAX_DAILY_API_CALLS", budgets_pol.get("max_daily_api_calls", 100))
        ),
        max_daily_tokens=int(
            os.getenv("CTO_MAX_DAILY_TOKENS", budgets_pol.get("max_daily_tokens", 500_000))
        ),
        min_confidence=float(
            os.getenv("CTO_MIN_CONFIDENCE", budgets_pol.get("min_confidence", 0.55))
        ),
        grok_max_turns=int(os.getenv("GROK_MAX_TURNS", executor.get("max_turns", 30))),
    )
    return CTOConfig(deepseek=deepseek, budgets=budgets, policies=policies, root=root)
