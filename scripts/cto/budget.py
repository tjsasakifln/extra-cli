"""Daily API budget tracking for CTO Autopilot."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.config import BudgetConfig
from scripts.cto.paths import budget_path


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_budget(root: Path | None = None) -> dict[str, Any]:
    path = budget_path(root)
    if not path.is_file():
        return {"day": _utc_day(), "api_calls": 0, "tokens": 0, "cycles": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"day": _utc_day(), "api_calls": 0, "tokens": 0, "cycles": 0}
    if data.get("day") != _utc_day():
        return {"day": _utc_day(), "api_calls": 0, "tokens": 0, "cycles": 0}
    return data


def save_budget(data: dict[str, Any], root: Path | None = None) -> None:
    path = budget_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def check_budget(cfg: BudgetConfig, root: Path | None = None) -> tuple[bool, str | None]:
    b = load_budget(root)
    if b.get("api_calls", 0) >= cfg.max_daily_api_calls:
        return False, f"max_daily_api_calls {cfg.max_daily_api_calls} reached"
    if b.get("tokens", 0) >= cfg.max_daily_tokens:
        return False, f"max_daily_tokens {cfg.max_daily_tokens} reached"
    if b.get("cycles", 0) >= cfg.max_cycles_per_run and cfg.max_cycles_per_run > 0:
        # cycles counter is per process run tracked separately; daily soft
        pass
    return True, None


def record_usage(
    *,
    api_calls: int = 0,
    tokens: int = 0,
    cycles: int = 0,
    root: Path | None = None,
) -> dict[str, Any]:
    b = load_budget(root)
    b["api_calls"] = int(b.get("api_calls") or 0) + api_calls
    b["tokens"] = int(b.get("tokens") or 0) + tokens
    b["cycles"] = int(b.get("cycles") or 0) + cycles
    save_budget(b, root)
    return b
