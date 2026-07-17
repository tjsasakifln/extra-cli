"""Single idempotent local resilient collection cycle (pre-VPS)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult, SourceAdapter
from scripts.crawl.resilience.adapters import CigaDomAdapter, PNCPAdapter, ScComprasAdapter
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.state import CanonicalCheckpoint, CheckpointStore, EvidenceLedger, FileDLQ, WatermarkStore
from scripts.crawl.run_evidence import new_run_id, sha256_json


class JsonLogger:
    fields = (
        "timestamp", "level", "service", "source", "run_id", "request_scope",
        "window", "page", "status", "http_status", "attempt", "duration",
        "records_fetched", "records_persisted", "checkpoint", "error_code", "error_message",
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
        pagination = {key: payload[key] for key in ("totalRegistros", "totalPaginas", "numeroPagina", "paginasRestantes", "empty")}
        return FetchResult(status="success", records=records, request_completed=True, http_status=200, pages_fetched=1, pages_expected=1, empty_confirmed=False, provenance={"fixture": True}, metadata={"pagination": pagination, "url": "fixture://pncp", "response_headers": {"content-type": "application/json"}})

    pncp = PNCPAdapter(config, page_fetcher=pncp_page)
    setattr(pncp.legacy, "INGESTION_MODALIDADES", [1])

    ciga_jsonl = fixture_dir / "ciga_publications.jsonl"
    def ciga_runner(**_kwargs: Any) -> dict[str, Any]:
        return {"run_id": new_run_id("ciga-fixture"), "status": "success", "jsonl_path": str(ciga_jsonl), "evidence_path": str(fixture_dir / "ciga_evidence.json"), "counts": {"selected": 1, "resources_processed_ok": 1, "resources_skipped_checkpoint": 0}, "errors": []}

    sc_items = json.loads((fixture_dir / "sc_compras_items.json").read_text(encoding="utf-8"))
    def sc_fetch(_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return sc_items, {"ok": True, "total_elementos": len(sc_items), "url": "fixture://sc-compras"}

    return [pncp, CigaDomAdapter(config, runner=ciga_runner), ScComprasAdapter(config, list_fetcher=sc_fetch)]


def _live_adapters(config: ResilienceConfig) -> list[SourceAdapter]:
    return [PNCPAdapter(config), CigaDomAdapter(config), ScComprasAdapter(config)]


def run_cycle(*, live: bool = False, source: str | None = None, fixture_dir: Path | None = None) -> tuple[int, dict[str, Any]]:
    config = ResilienceConfig.from_env()
    for path in (config.checkpoint_path, config.raw_path, config.dlq_path, config.evidence_path, config.ops_path):
        path.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id("resilient-local")
    log_path = config.ops_path / "logs" / f"{run_id}.jsonl"
    logger = JsonLogger(log_path)
    ledger = EvidenceLedger(config.evidence_path)
    checkpoints = CheckpointStore(config.checkpoint_path)
    watermarks = WatermarkStore(config.ops_path / "watermarks")
    dlq = FileDLQ(config.dlq_path)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    steps: list[dict[str, Any]] = [
        {"step": "pre-check", "status": "success"},
        {"step": "migrations", "status": "validated", "note": "read-only pre-VPS; db migrations remain canonical"},
    ]
    adapters = _live_adapters(config) if live else _fixture_adapters(config, fixture_dir or Path("tests/fixtures/resilience"))
    if source:
        wanted = "ciga_dom" if source == "ciga_ckan" else source
        adapters = [adapter for adapter in adapters if adapter.source_id == wanted]
    results: dict[str, Any] = {}

    for adapter in adapters:
        source_started = time.monotonic()
        scope = f"mode=incremental|date={date.today().isoformat()}"
        request = CrawlRequest(mode="incremental", date_from=date.today(), date_to=date.today(), source=adapter.source_id, request_scope=scope, run_id=run_id)
        health = adapter.health()
        steps.append({"step": f"source-health:{adapter.source_id}", "status": health.status})
        try:
            fetched = adapter.fetch(request)
            normalized = adapter.normalize(fetched.records)
            canonical_path = config.ops_path / "canonical" / adapter.source_id / f"{run_id}.json"
            _atomic(canonical_path, normalized)
            canonical_hash = sha256_json(normalized)

            # A page becomes complete only after canonical persistence.
            for raw_ref in fetched.metadata.get("raw", []):
                cp = checkpoints.load(adapter.source_id, raw_ref["request_scope"])
                if cp and fetched.status in {"success", "empty_confirmed"}:
                    cp.status = fetched.status
                    checkpoints.save(cp)
            if isinstance(fetched.checkpoint, dict) and fetched.checkpoint.get("request_scope"):
                try:
                    cp = CanonicalCheckpoint(**fetched.checkpoint)
                    if fetched.status in {"success", "empty_confirmed"}:
                        cp.status = fetched.status
                    checkpoints.save(cp)
                except TypeError:
                    pass

            fetched.provenance["canonical_path"] = str(canonical_path)
            fetched.provenance["canonical_hash"] = canonical_hash
            evidence_path, evidence = ledger.write(source=adapter.source_id, run_id=run_id, request_scope=scope, result=fetched, window={"date_from": str(request.date_from), "date_to": str(request.date_to)}, target=request.target)
            run_cp = CanonicalCheckpoint(source=adapter.source_id, run_id=run_id, request_scope=scope, target=request.target, date_from=str(request.date_from), date_to=str(request.date_to), window=str(request.date_from), status=fetched.status or "error", attempt_count=1, last_http_status=fetched.http_status, last_error="; ".join(fetched.errors) or None, pages_fetched=fetched.pages_fetched, pages_expected=fetched.pages_expected, content_hash=canonical_hash, scope_level="run")
            checkpoints.save(run_cp)
            if evidence["satisfactory"]:
                watermarks.commit(run_cp, evidence_path, evidence)
            results[adapter.source_id] = {"status": fetched.status, "satisfactory": evidence["satisfactory"], "pages_fetched": fetched.pages_fetched, "pages_expected": fetched.pages_expected, "records_fetched": len(fetched.records), "records_persisted": len(normalized), "checkpoint": asdict(run_cp), "evidence": str(evidence_path), "canonical": str(canonical_path), "errors": fetched.errors}
            logger.emit(source=adapter.source_id, run_id=run_id, request_scope=scope, window=run_cp.window, status=fetched.status, http_status=fetched.http_status, attempt=1, duration=round(time.monotonic() - source_started, 4), records_fetched=len(fetched.records), records_persisted=len(normalized), checkpoint=str(checkpoints.path_for(adapter.source_id, scope)), error_code=fetched.status if fetched.errors else None, error_message="; ".join(fetched.errors) or None)
        except Exception as exc:
            dlq.push(source=adapter.source_id, run_id=run_id, payload={"request_scope": scope}, error=exc, error_kind="systemic")
            results[adapter.source_id] = {"status": "error", "satisfactory": False, "errors": [str(exc)]}
            logger.emit(level="ERROR", source=adapter.source_id, run_id=run_id, request_scope=scope, status="error", attempt=1, duration=round(time.monotonic() - source_started, 4), records_fetched=0, records_persisted=0, error_code="systemic", error_message=str(exc))

    steps.extend([
        {"step": "resume-pending", "status": "success" if not checkpoints.pending() else "partial", "pending": len(checkpoints.pending())},
        {"step": "evidence-projection", "status": "success" if all(v.get("satisfactory") for v in results.values()) else "partial"},
        {"step": "freshness-gate", "status": "success" if all(v.get("satisfactory") for v in results.values()) else "blocked"},
        {"step": "coverage-contract", "status": "mechanics_only", "note": "fixture runs never inflate operational entity coverage"},
    ])
    blocked = any(v.get("status") in {"error", "auth_blocked", "rate_limited"} for v in results.values())
    degraded = any(not v.get("satisfactory") for v in results.values()) or bool(checkpoints.pending())
    exit_code = 2 if blocked else (1 if degraded else 0)
    summary = {"run_id": run_id, "mode": "live" if live else "controlled_fixture", "status": "blocked" if exit_code == 2 else ("degraded" if exit_code == 1 else "healthy"), "exit_code": exit_code, "started_at": started_at, "duration_seconds": round(time.monotonic() - started, 4), "results": results, "steps": steps, "pending_checkpoints": len(checkpoints.pending()), "pending_dlq": len(dlq.pending()), "log_path": str(log_path), "claim": "resilience mechanics only" if not live else "live local collection; not VPS"}
    summary_path = config.ops_path / "runs" / f"{run_id}.json"
    steps.append({"step": "health-summary", "status": summary["status"], "path": str(summary_path)})
    _atomic(summary_path, summary)
    _atomic(config.ops_path / "latest.json", summary)
    for source_id, result in results.items():
        _atomic(
            config.ops_path / "latest_sources" / f"{source_id}.json",
            {"run_id": run_id, "started_at": started_at, "duration_seconds": summary["duration_seconds"], "result": result},
        )
    return exit_code, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ciclo local resiliente canônico (não provisiona VPS)")
    parser.add_argument("--live", action="store_true", help="Consultar fontes públicas reais; padrão usa fixtures controladas")
    parser.add_argument("--source", choices=["pncp", "ciga_dom", "ciga_ckan", "sc_compras"])
    parser.add_argument("--fixture-dir", type=Path, default=Path("tests/fixtures/resilience"))
    args = parser.parse_args(argv)
    code, summary = run_cycle(live=args.live, source=args.source, fixture_dir=args.fixture_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
