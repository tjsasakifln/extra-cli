"""One-command local resilience health summary."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.state import CheckpointStore, FileDLQ


def collect_health(config: ResilienceConfig | None = None) -> tuple[int, dict[str, Any]]:
    cfg = config or ResilienceConfig.from_env()
    latest_path = cfg.ops_path / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else {}
    checkpoints = CheckpointStore(cfg.checkpoint_path).pending()
    dlq = FileDLQ(cfg.dlq_path).pending()
    results = latest.get("results") or {}
    sources: dict[str, Any] = {}
    now = datetime.now(UTC)
    sla_hours = {"pncp": 24, "ciga_dom": 48, "sc_compras": 24}
    for source in ("pncp", "ciga_dom", "sc_compras"):
        source_path = cfg.ops_path / "latest_sources" / f"{source}.json"
        source_latest = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {}
        result = source_latest.get("result") or results.get(source) or {}
        attempted_at = source_latest.get("started_at") or (latest.get("started_at") if result else None)
        age_hours: float | None = None
        if attempted_at:
            try:
                age_hours = (now - datetime.fromisoformat(str(attempted_at).replace("Z", "+00:00"))).total_seconds() / 3600
            except ValueError:
                age_hours = None
        is_current = bool(result.get("satisfactory")) and age_hours is not None and age_hours <= sla_hours[source]
        source_cps = [cp for cp in checkpoints if cp.source == source]
        sources[source] = {
            "last_attempt": attempted_at,
            "last_success": attempted_at if result.get("satisfactory") else None,
            "status": result.get("status", "unknown"),
            "freshness": "current" if is_current else ("stale" if result.get("satisfactory") else "unknown"),
            "freshness_age_hours": round(age_hours, 3) if age_hours is not None else None,
            "freshness_sla_hours": sla_hours[source],
            "http_429": 1 if result.get("status") == "rate_limited" else 0,
            "partial": 1 if result.get("status") == "partial" else 0,
            "errors": len(result.get("errors") or []),
            "duration": source_latest.get("duration_seconds") or latest.get("duration_seconds"),
            "volume": result.get("records_persisted", 0),
            "checkpoint_pending": len(source_cps),
        }
    blocked = not latest or any(row["status"] in {"error", "auth_blocked", "rate_limited", "unknown"} or row["freshness"] == "stale" for row in sources.values())
    degraded = bool(checkpoints or dlq or any(row["status"] == "partial" for row in sources.values()))
    code = 2 if blocked else (1 if degraded else 0)
    return code, {"status": "blocked_or_stale" if code == 2 else ("degraded" if code == 1 else "healthy"), "exit_code": code, "checked_at": datetime.now(UTC).isoformat(), "sources": sources, "pending_checkpoints": len(checkpoints), "pending_dlq": len(dlq), "latest_run_id": latest.get("run_id")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Saúde consolidada da resiliência local")
    parser.add_argument("--json", action="store_true", help="Mantido por compatibilidade; saída sempre JSON")
    parser.parse_args(argv)
    code, report = collect_health()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
