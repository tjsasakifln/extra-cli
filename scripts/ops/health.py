"""Honest operational health — live by default; fixtures never greenwash live."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.registry import lookup
from scripts.crawl.resilience.config import ResilienceConfig, is_live_environment, resolve_environment
from scripts.crawl.resilience.state import CheckpointStore, FileDLQ, RunHistory

PRIORITY_SOURCES = ("pncp", "ciga_dom", "sc_compras")


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _sla_hours(source: str, fallback: int = 24) -> float:
    try:
        info = lookup(source if source != "ciga_dom" else "ciga_ckan")
        return float(info.freshness_sla_hours)
    except Exception:
        # ciga_dom may not be registered under that exact name
        try:
            if source == "ciga_dom":
                return float(lookup("ciga_ckan").freshness_sla_hours)
        except Exception:
            return float(fallback)
        return float(fallback)


def _freshness_triple(
    *,
    collection_at: datetime | None,
    content_max: datetime | None,
    operational_at: datetime | None,
    sla_hours: float,
    now: datetime,
    has_content_ts: bool,
) -> dict[str, Any]:
    def age_status(ts: datetime | None) -> str:
        if ts is None:
            return "unknown"
        age = (now - ts).total_seconds() / 3600
        return "current" if age <= sla_hours else "stale"

    collection_freshness = age_status(collection_at)
    if not has_content_ts:
        content_freshness = "unknown"
    else:
        content_freshness = age_status(content_max)
    # Operational freshness is min(collection, content) honesty:
    # recent fetch of old content → operational stale.
    if operational_at is None:
        operational_freshness = "unknown"
    elif content_freshness == "stale":
        operational_freshness = "stale"
    elif content_freshness == "unknown":
        # Cannot claim operational current without content basis for live.
        operational_freshness = "unknown" if collection_freshness == "current" else collection_freshness
    else:
        operational_freshness = age_status(operational_at)
        if collection_freshness == "stale":
            operational_freshness = "stale"

    basis = []
    if collection_at:
        basis.append("last_complete_collection")
    if has_content_ts:
        basis.append("source_content_max_timestamp")
    else:
        basis.append("content_timestamp_unavailable")
    return {
        "collection_freshness": collection_freshness,
        "content_freshness": content_freshness,
        "operational_freshness": operational_freshness,
        "freshness_basis": ",".join(basis),
    }


def collect_health(
    config: ResilienceConfig | None = None,
    *,
    env: str | None = None,
    include_fixture: bool = False,
) -> tuple[int, dict[str, Any]]:
    target_env = resolve_environment(env) if env else (config.environment if config else resolve_environment())
    cfg = config or ResilienceConfig.from_env(environment=target_env)
    # Force ops path for requested env.
    if env and cfg.environment != target_env:
        cfg = ResilienceConfig.from_env(environment=target_env)

    live_query = is_live_environment(target_env) and not include_fixture
    latest_path = cfg.ops_path / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else {}
    history = RunHistory(cfg.ops_path / "run_history")
    checkpoints = CheckpointStore(cfg.checkpoint_path)
    dlq = FileDLQ(cfg.dlq_path)
    now = datetime.now(UTC)
    sources: dict[str, Any] = {}
    inconsistencies: list[str] = []

    # Live default: ignore fixture environment artifacts entirely.
    if live_query:
        mode = latest.get("execution_mode") or latest.get("mode")
        environment = latest.get("environment")
        if mode in {"controlled_fixture", "fixture"} or environment in {"fixture", "test"}:
            latest = {}
        if not latest:
            # No live evidence at all.
            report = {
                "status": "no_live_evidence",
                "exit_code": 2,
                "checked_at": now.isoformat(),
                "environment": target_env,
                "execution_mode": "live",
                "sources": {},
                "pending_checkpoints": 0,
                "pending_dlq": 0,
                "latest_run_id": None,
                "claim": "no live operational evidence",
            }
            return 2, report

    for source in PRIORITY_SOURCES:
        source_path = cfg.ops_path / "latest_sources" / f"{source}.json"
        source_latest = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {}
        if live_query and (
            source_latest.get("execution_mode") == "fixture"
            or source_latest.get("environment") in {"fixture", "test"}
        ):
            source_latest = {}
        result = source_latest.get("result") or (latest.get("results") or {}).get(source) or {}
        hist = history.load_all(source)
        if live_query:
            hist = [
                h
                for h in hist
                if h.get("execution_mode") in {"live", "canary"}
                and h.get("environment") not in {"fixture", "test"}
            ]

        last_attempt = None
        last_transport_success = None
        last_complete_collection = None
        last_operational_success = None
        last_http_status = None
        content_max = None
        for row in hist:
            ts = _parse_ts(row.get("finished_at") or row.get("started_at"))
            if ts and (last_attempt is None or ts > last_attempt):
                last_attempt = ts
            if row.get("status") in {"success", "empty_confirmed", "partial"} and ts:
                if last_transport_success is None or ts > last_transport_success:
                    last_transport_success = ts
            if row.get("satisfactory") and row.get("status") in {"success", "empty_confirmed"} and ts:
                if last_complete_collection is None or ts > last_complete_collection:
                    last_complete_collection = ts
            if row.get("operational_satisfactory") and row.get("db_committed") and ts:
                if last_operational_success is None or ts > last_operational_success:
                    last_operational_success = ts
            if row.get("http_status") is not None:
                last_http_status = row.get("http_status")
            cts = _parse_ts(row.get("content_max_timestamp") or row.get("source_content_max_timestamp"))
            if cts and (content_max is None or cts > content_max):
                content_max = cts

        # Fall back to latest file timestamps when history empty (same env only).
        attempted_at = source_latest.get("started_at") or (latest.get("started_at") if result else None)
        if last_attempt is None:
            last_attempt = _parse_ts(attempted_at)
        if last_complete_collection is None and result.get("satisfactory") and result.get("status") in {
            "success",
            "empty_confirmed",
        }:
            last_complete_collection = _parse_ts(attempted_at)
        if last_operational_success is None and result.get("operational_satisfactory") and result.get("db_committed"):
            last_operational_success = _parse_ts(attempted_at)
        if content_max is None:
            content_max = _parse_ts(result.get("content_max_timestamp"))

        sla = _sla_hours(source)
        has_content = content_max is not None
        fresh = _freshness_triple(
            collection_at=last_complete_collection,
            content_max=content_max,
            operational_at=last_operational_success or last_complete_collection,
            sla_hours=sla,
            now=now,
            has_content_ts=has_content,
        )

        source_cps = [cp for cp in checkpoints.pending() if cp.source == source]
        breaker_path = cfg.breaker_path / cfg.environment / source / "default.json"
        breaker_state = "unknown"
        if breaker_path.is_file():
            try:
                breaker_state = json.loads(breaker_path.read_text(encoding="utf-8")).get("state", "unknown")
            except (OSError, json.JSONDecodeError):
                breaker_state = "unknown"

        budget_path = cfg.ops_path / "budgets" / f"{source}.json"
        budget_used = budget_limit = None
        if budget_path.is_file():
            try:
                b = json.loads(budget_path.read_text(encoding="utf-8"))
                budget_used = b.get("used")
                budget_limit = b.get("limit")
            except (OSError, json.JSONDecodeError):
                pass

        # Cross-checks
        wm_path = cfg.ops_path / "watermarks" / source
        last_wm = None
        if wm_path.is_dir():
            files = sorted(wm_path.glob("*.json"))
            if files:
                try:
                    last_wm = json.loads(files[-1].read_text(encoding="utf-8"))
                    ev_path = Path(str(last_wm.get("evidence_path") or ""))
                    if last_wm.get("evidence_path") and not ev_path.is_file():
                        inconsistencies.append(f"{source}:watermark_missing_evidence")
                    if live_query and not last_wm.get("db_committed"):
                        inconsistencies.append(f"{source}:watermark_without_db")
                except (OSError, json.JSONDecodeError):
                    inconsistencies.append(f"{source}:watermark_unreadable")

        try:
            lookup(source if source != "ciga_dom" else "ciga_ckan")
        except Exception:
            inconsistencies.append(f"{source}:not_in_registry")

        last_success_preserved = last_operational_success or last_complete_collection
        sources[source] = {
            "environment": cfg.environment,
            "execution_mode": source_latest.get("execution_mode") or latest.get("execution_mode") or cfg.execution_mode,
            "last_attempt": last_attempt.isoformat() if last_attempt else None,
            "last_transport_success": last_transport_success.isoformat() if last_transport_success else None,
            "last_complete_collection": last_complete_collection.isoformat() if last_complete_collection else None,
            "last_operational_success": last_operational_success.isoformat() if last_operational_success else None,
            "last_success": last_success_preserved.isoformat() if last_success_preserved else None,
            "collection_freshness": fresh["collection_freshness"],
            "content_freshness": fresh["content_freshness"],
            "operational_freshness": fresh["operational_freshness"],
            "freshness_basis": fresh["freshness_basis"],
            "freshness_sla_hours": sla,
            "source_content_max_timestamp": content_max.isoformat() if content_max else None,
            "canonical_content_max_timestamp": content_max.isoformat() if content_max else None,
            "last_status": result.get("status", "unknown"),
            "last_http_status": last_http_status or result.get("checkpoint", {}).get("last_http_status")
            if isinstance(result.get("checkpoint"), dict)
            else last_http_status,
            "http_429_count_window": 1 if result.get("status") == "rate_limited" else 0,
            "partial_count_window": 1 if result.get("status") == "partial" else 0,
            "error_count_window": len(result.get("errors") or []),
            "pending_checkpoints": len(source_cps),
            "pending_dlq": len(dlq.pending(source)),
            "circuit_breaker_state": breaker_state,
            "request_budget_used": budget_used,
            "request_budget_limit": budget_limit,
            "db_records_committed": result.get("db_records_committed", 0),
            "last_evidence_hash": result.get("evidence_hash"),
            "last_watermark": last_wm.get("evidence_hash") if last_wm else None,
            "status": result.get("status", "unknown"),
            # Compat field — never treat fixture as operational current.
            "freshness": fresh["operational_freshness"]
            if live_query
            else fresh["collection_freshness"],
        }

    pending_all = checkpoints.pending()
    pending_dlq = dlq.pending()

    if live_query:
        if not any(sources[s].get("last_operational_success") for s in PRIORITY_SOURCES):
            # Also allow last_complete only if db was committed in latest.
            if not any(sources[s].get("db_records_committed") for s in PRIORITY_SOURCES):
                return 2, {
                    "status": "no_live_evidence",
                    "exit_code": 2,
                    "checked_at": now.isoformat(),
                    "environment": target_env,
                    "execution_mode": "live",
                    "sources": sources,
                    "pending_checkpoints": len(pending_all),
                    "pending_dlq": len(pending_dlq),
                    "latest_run_id": latest.get("run_id"),
                    "inconsistencies": inconsistencies,
                    "claim": "no live operational evidence",
                }

        blocked = bool(inconsistencies) or any(
            row["last_status"] in {"error", "auth_blocked", "rate_limited", "unknown"}
            or row["operational_freshness"] in {"stale", "unknown"}
            for row in sources.values()
        )
        # unknown operational freshness with no success is blocked
        degraded = bool(pending_all or pending_dlq or any(row["last_status"] == "partial" for row in sources.values()))
        code = 2 if blocked else (1 if degraded else 0)
        status = "blocked_or_stale" if code == 2 else ("degraded" if code == 1 else "healthy")
    else:
        # Fixture/test health — never called "healthy" operationally.
        blocked = any(row["last_status"] in {"error", "auth_blocked", "rate_limited", "unknown"} for row in sources.values())
        degraded = bool(pending_all or pending_dlq or any(row["last_status"] == "partial" for row in sources.values()))
        all_ok = all(
            row["last_status"] in {"success", "empty_confirmed"} or row.get("last_complete_collection")
            for row in sources.values()
        ) and not blocked and not degraded
        # If latest fixture run was satisfactory:
        if latest.get("status") == "TEST_HEALTHY" or (
            latest.get("mode") == "controlled_fixture" and latest.get("exit_code") == 0
        ):
            code = 0 if not blocked and not degraded else (2 if blocked else 1)
            status = "TEST_HEALTHY" if code == 0 else ("blocked_or_stale" if code == 2 else "degraded")
        else:
            code = 2 if blocked or not all_ok else (1 if degraded else 0)
            status = "TEST_HEALTHY" if code == 0 else ("blocked_or_stale" if code == 2 else "degraded")

    return code, {
        "status": status,
        "exit_code": code,
        "checked_at": now.isoformat(),
        "environment": target_env,
        "execution_mode": "live" if live_query else cfg.execution_mode,
        "sources": sources,
        "pending_checkpoints": len(pending_all),
        "pending_dlq": len(pending_dlq),
        "latest_run_id": latest.get("run_id"),
        "inconsistencies": inconsistencies,
        "claim": "operational live" if live_query else "fixture/test mechanics only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Saúde consolidada da resiliência local")
    parser.add_argument("--json", action="store_true", help="Mantido por compatibilidade; saída sempre JSON")
    parser.add_argument(
        "--env",
        choices=["test", "fixture", "development", "staging", "production"],
        default=None,
        help="Consultar estado de um environment (default: live/development). Fixture requer --env fixture",
    )
    args = parser.parse_args(argv)
    # Default operational command: live development paths only.
    env = args.env or "development"
    code, report = collect_health(env=env)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
