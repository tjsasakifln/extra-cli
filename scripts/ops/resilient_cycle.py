"""Single idempotent local resilient collection cycle (pre-VPS).

Canonical path:
  fetch → raw → normalize → persist_canonical (PostgreSQL when live)
  → evidence → checkpoint complete → watermark → health
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult, SourceAdapter
from scripts.crawl.resilience.adapters import CigaDomAdapter, PNCPAdapter, ScComprasAdapter
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.pipeline import OperationalPipeline
from scripts.crawl.resilience.state import CheckpointStore, FileDLQ
from scripts.crawl.run_evidence import new_run_id


class JsonLogger:
    fields = (
        "timestamp",
        "level",
        "service",
        "source",
        "run_id",
        "request_scope",
        "window",
        "page",
        "status",
        "http_status",
        "attempt",
        "duration",
        "records_fetched",
        "records_persisted",
        "checkpoint",
        "error_code",
        "error_message",
    )

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, **values: Any) -> None:
        event = {key: values.get(key) for key in self.fields}
        event["timestamp"] = values.get("timestamp") or datetime.now(UTC).isoformat()
        event["level"] = values.get("level") or "INFO"
        event["service"] = values.get("service") or "resilient-local-cycle"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _fixture_adapters(config: ResilienceConfig, fixture_dir: Path) -> list[SourceAdapter]:
    pncp_payload = json.loads((fixture_dir / "pncp_page.json").read_text(encoding="utf-8"))

    def pncp_page(_request: CrawlRequest, _modalidade: int, page: int) -> FetchResult:
        payload = dict(pncp_payload)
        payload["numeroPagina"] = page
        records = payload["data"] if page == 1 else []
        pagination = {
            key: payload[key] for key in ("totalRegistros", "totalPaginas", "numeroPagina", "paginasRestantes", "empty")
        }
        return FetchResult(
            status="success",
            records=records,
            request_completed=True,
            http_status=200,
            pages_fetched=1,
            pages_expected=1,
            empty_confirmed=False,
            provenance={"fixture": True},
            metadata={
                "pagination": pagination,
                "url": "fixture://pncp",
                "response_headers": {"content-type": "application/json"},
            },
        )

    pncp = PNCPAdapter(config, page_fetcher=pncp_page)
    setattr(pncp.legacy, "INGESTION_MODALIDADES", [1])

    ciga_jsonl = fixture_dir / "ciga_publications.jsonl"

    def ciga_runner(**_kwargs: Any) -> dict[str, Any]:
        return {
            "run_id": new_run_id("ciga-fixture"),
            "status": "success",
            "jsonl_path": str(ciga_jsonl),
            "evidence_path": str(fixture_dir / "ciga_evidence.json"),
            "counts": {"selected": 1, "resources_processed_ok": 1, "resources_skipped_checkpoint": 0},
            "errors": [],
        }

    sc_items = json.loads((fixture_dir / "sc_compras_items.json").read_text(encoding="utf-8"))

    def sc_fetch(_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return sc_items, {"ok": True, "total_elementos": len(sc_items), "url": "fixture://sc-compras"}

    return [pncp, CigaDomAdapter(config, runner=ciga_runner), ScComprasAdapter(config, list_fetcher=sc_fetch)]


def _live_adapters(config: ResilienceConfig) -> list[SourceAdapter]:
    return [PNCPAdapter(config), CigaDomAdapter(config), ScComprasAdapter(config)]


def _pncp_request_windows(adapter: SourceAdapter, *, current: date, limit: int = 14) -> list[tuple[date, date]]:
    """Bounded oldest-first replay windows plus the current UTC day."""
    windows: set[tuple[date, date]] = set()
    checkpoints = getattr(adapter, "checkpoints", None)
    if checkpoints is not None:
        for checkpoint in checkpoints.pending("pncp"):
            try:
                start = date.fromisoformat(str(checkpoint.date_from))
                end = date.fromisoformat(str(checkpoint.date_to or checkpoint.date_from))
            except (TypeError, ValueError):
                continue
            if start <= end <= current:
                windows.add((start, end))
    ordered = sorted(windows)[: max(0, limit - 1)]
    current_window = (current, current)
    if current_window not in ordered:
        ordered.append(current_window)
    return ordered


def _aggregate_source_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(runs) == 1:
        return runs[0]
    priority = {"error": 5, "auth_blocked": 4, "rate_limited": 3, "partial": 2, "success": 1, "empty_confirmed": 1}
    status = max((str(run.get("status") or "error") for run in runs), key=lambda item: priority.get(item, 4))
    return {
        "status": status,
        "terminal_status": "success" if all(run.get("satisfactory") for run in runs) else "partial",
        "satisfactory": all(bool(run.get("satisfactory")) for run in runs),
        "mechanics_satisfactory": all(bool(run.get("mechanics_satisfactory")) for run in runs),
        "operational_satisfactory": all(bool(run.get("operational_satisfactory")) for run in runs),
        "db_committed": all(bool(run.get("db_committed")) for run in runs),
        "request_completed": all(bool(run.get("request_completed")) for run in runs),
        "scope_complete": all(bool(run.get("scope_complete")) for run in runs),
        "records_fetched": sum(int(run.get("records_fetched") or 0) for run in runs),
        "records_persisted": sum(int(run.get("records_persisted") or 0) for run in runs),
        "db_records_committed": sum(int(run.get("db_records_committed") or 0) for run in runs),
        "errors": [error for run in runs for error in (run.get("errors") or [])],
        "warnings": [warning for run in runs for warning in (run.get("warnings") or [])],
        "pages_reused": sum(int(run.get("pages_reused") or 0) for run in runs),
        "pages_reprocessed": sum(int(run.get("pages_reprocessed") or 0) for run in runs),
        "local_corruption_count": sum(int(run.get("local_corruption_count") or 0) for run in runs),
        "windows": runs,
    }


def run_cycle(
    *,
    live: bool = False,
    source: str | None = None,
    target: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    run_id: str | None = None,
    fixture_dir: Path | None = None,
    config: ResilienceConfig | None = None,
    persistence: Any | None = None,
    crash_after: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if config is None:
        env = "fixture" if not live else None
        config = ResilienceConfig.from_env(environment=env, execution_mode="live" if live else "fixture")
        if live:
            config = config.with_execution_mode("live")
        else:
            config = config.with_execution_mode("fixture")

    for path in (
        config.checkpoint_path,
        config.raw_path,
        config.dlq_path,
        config.evidence_path,
        config.ops_path,
        config.breaker_path,
    ):
        path.mkdir(parents=True, exist_ok=True)

    run_id = run_id or new_run_id("resilient-local")
    log_path = config.ops_path / "logs" / f"{run_id}.jsonl"
    logger = JsonLogger(log_path)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    pipeline = OperationalPipeline(config, persistence=persistence, crash_after=crash_after)
    steps: list[dict[str, Any]] = [
        {
            "step": "pre-check",
            "status": "success",
            "environment": config.environment,
            "execution_mode": config.execution_mode,
        },
        {"step": "pipeline", "status": "canonical", "note": "single path including optional PostgreSQL persist"},
    ]
    adapters = (
        _live_adapters(config) if live else _fixture_adapters(config, fixture_dir or Path("tests/fixtures/resilience"))
    )
    if source:
        wanted = "ciga_dom" if source == "ciga_ckan" else source
        adapters = [adapter for adapter in adapters if adapter.source_id == wanted]
    results: dict[str, Any] = {}

    for adapter in adapters:
        source_started = time.monotonic()
        request_start = date_from or datetime.now(UTC).date()
        request_end = date_to or request_start
        health = adapter.health()
        steps.append({"step": f"source-health:{adapter.source_id}", "status": health.status})
        windows = [(request_start, request_end)]
        if live and adapter.source_id == "pncp" and date_from is None and date_to is None:
            windows = _pncp_request_windows(adapter, current=request_start)
        source_runs: list[dict[str, Any]] = []
        for index, (window_start, window_end) in enumerate(windows):
            scope = (
                f"mode=incremental|date={window_start.isoformat()}:{window_end.isoformat()}|target={target or 'all'}"
            )
            window_run_id = run_id if len(windows) == 1 else f"{run_id}-w{index + 1:02d}"
            request = CrawlRequest(
                mode="incremental",
                date_from=window_start,
                date_to=window_end,
                target=target,
                source=adapter.source_id,
                request_scope=scope,
                run_id=window_run_id,
            )
            out = pipeline.run_source(adapter, request, run_id=window_run_id)
            out["request_scope"] = scope
            source_runs.append(out)
            logger.emit(
                source=adapter.source_id,
                run_id=window_run_id,
                request_scope=scope,
                window=f"{window_start}:{window_end}",
                status=out.get("status"),
                attempt=1,
                duration=round(time.monotonic() - source_started, 4),
                records_fetched=out.get("records_fetched", 0),
                records_persisted=out.get("records_persisted", 0),
                error_code=out.get("status") if out.get("errors") else None,
                error_message="; ".join(out.get("errors") or []) or None,
            )
        results[adapter.source_id] = _aggregate_source_runs(source_runs)

    checkpoints = CheckpointStore(config.checkpoint_path)
    dlq = FileDLQ(config.dlq_path)
    pending = checkpoints.pending()
    steps.extend(
        [
            {
                "step": "resume-pending",
                "status": "success" if not pending else "partial",
                "pending": len(pending),
            },
            {
                "step": "evidence-projection",
                "status": "success" if all(v.get("satisfactory") for v in results.values()) else "partial",
            },
            {
                "step": "db-projection",
                "status": "success"
                if all(v.get("db_committed") or config.execution_mode == "fixture" for v in results.values())
                else "blocked",
            },
            {
                "step": "freshness-gate",
                "status": "success" if all(v.get("satisfactory") for v in results.values()) else "blocked",
            },
            {
                "step": "coverage-contract",
                "status": "mechanics_only" if not live else "operational",
                "note": "fixture runs never inflate operational live health",
            },
        ]
    )

    blocked = any(v.get("status") in {"error", "auth_blocked", "rate_limited"} for v in results.values())
    # Live operational path: missing DB commit is blocked.
    if live:
        blocked = blocked or any(
            not v.get("db_committed") and v.get("status") in {"success", "empty_confirmed"} for v in results.values()
        )
    degraded = any(not v.get("satisfactory") for v in results.values()) or bool(pending)
    exit_code = 2 if blocked else (1 if degraded else 0)

    if live:
        status_label = "blocked" if exit_code == 2 else ("degraded" if exit_code == 1 else "healthy")
        claim = "live local collection with PostgreSQL projection; not VPS"
    else:
        # Fixture cycle must never claim operational healthy.
        status_label = "blocked" if exit_code == 2 else ("degraded" if exit_code == 1 else "TEST_HEALTHY")
        claim = "resilience mechanics only — not operational live"

    summary = {
        "run_id": run_id,
        "mode": "live" if live else "controlled_fixture",
        "environment": config.environment,
        "execution_mode": config.execution_mode,
        "status": status_label,
        "exit_code": exit_code,
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 4),
        "results": results,
        "steps": steps,
        "pending_checkpoints": len(pending),
        "pending_dlq": len(dlq.pending()),
        "log_path": str(log_path),
        "claim": claim,
        "host": config.host,
        "aggregate": {
            "status": status_label,
            "exit_code": exit_code,
            "pending_checkpoints": len(pending),
            "pending_dlq": len(dlq.pending()),
        },
    }
    summary_path = config.ops_path / "runs" / f"{run_id}.json"
    steps.append({"step": "health-summary", "status": summary["status"], "path": str(summary_path)})
    summary["steps"] = steps
    _atomic(summary_path, summary)
    _atomic(config.ops_path / "latest.json", summary)
    for source_id, result in results.items():
        _atomic(
            config.ops_path / "latest_sources" / f"{source_id}.json",
            {
                "run_id": run_id,
                "started_at": started_at,
                "duration_seconds": summary["duration_seconds"],
                "environment": config.environment,
                "execution_mode": config.execution_mode,
                "result": result,
                "aggregate": summary["aggregate"],
            },
        )
    return exit_code, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ciclo local resiliente canônico (não provisiona VPS)")
    parser.add_argument(
        "--live", action="store_true", help="Consultar fontes públicas reais; padrão usa fixtures controladas"
    )
    parser.add_argument("--source", choices=["pncp", "ciga_dom", "ciga_ckan", "sc_compras"])
    parser.add_argument("--fixture-dir", type=Path, default=Path("tests/fixtures/resilience"))
    parser.add_argument(
        "--env",
        choices=["test", "fixture", "development", "staging", "production"],
        default=None,
        help="RESILIENCE_ENV override (fixture isolation vs live)",
    )
    args = parser.parse_args(argv)
    env = args.env or ("fixture" if not args.live else "development")
    config = ResilienceConfig.from_env(environment=env, execution_mode="live" if args.live else "fixture")
    code, summary = run_cycle(live=args.live, source=args.source, fixture_dir=args.fixture_dir, config=config)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
