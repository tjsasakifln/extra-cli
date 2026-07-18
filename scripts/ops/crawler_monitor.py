"""Crawler operational metrics (DoD §23).

Aggregates duration, success rate, collected volume, and HTTP 403/429/5xx/timeouts
from RunHistory JSONL files (and optional inline samples).

Never invents green health when history is empty — status=unknown with limitations.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.crawl.resilience.state import RunHistory

REPO = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY_ROOTS = (
    REPO / "output" / "resilience" / "fixture" / "ops" / "run_history",
    REPO / "output" / "resilience" / "live" / "ops" / "run_history",
    REPO / "output" / "ops" / "run_history",
    REPO / "data" / "ops" / "run_history",
)


@dataclass
class SourceMetrics:
    source: str
    runs: int = 0
    successes: int = 0
    failures: int = 0
    duration_seconds_total: float = 0.0
    duration_seconds_max: float = 0.0
    records_total: int = 0
    http_403: int = 0
    http_429: int = 0
    http_5xx: int = 0
    timeouts: int = 0
    last_run_at: str | None = None

    @property
    def success_rate(self) -> float | None:
        if self.runs <= 0:
            return None
        return self.successes / self.runs

    @property
    def avg_duration_seconds(self) -> float | None:
        if self.runs <= 0:
            return None
        return self.duration_seconds_total / self.runs

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["avg_duration_seconds"] = self.avg_duration_seconds
        return d


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _classify_http(status: Any) -> str | None:
    try:
        code = int(status)
    except (TypeError, ValueError):
        return None
    if code == 403:
        return "403"
    if code == 429:
        return "429"
    if 500 <= code <= 599:
        return "5xx"
    return None


def _is_timeout(record: dict[str, Any]) -> bool:
    err = str(record.get("error") or record.get("error_type") or record.get("error_message") or "").lower()
    if "timeout" in err or "timed out" in err:
        return True
    if record.get("timeout") is True:
        return True
    return False


def _is_success(record: dict[str, Any]) -> bool:
    if "success" in record:
        return bool(record["success"])
    status = str(record.get("status") or record.get("outcome") or "").lower()
    if status in {"ok", "success", "done", "completed", "pass"}:
        return True
    if status in {"error", "failed", "fail", "aborted"}:
        return False
    # Infer from http
    code = record.get("http_status") or record.get("status_code")
    try:
        return 200 <= int(code) < 400
    except (TypeError, ValueError):
        return False


def ingest_record(metrics: dict[str, SourceMetrics], record: dict[str, Any]) -> None:
    source = str(record.get("source") or "unknown")
    m = metrics.setdefault(source, SourceMetrics(source=source))
    m.runs += 1
    if _is_success(record):
        m.successes += 1
    else:
        m.failures += 1
    dur = _as_float(
        record.get("duration_seconds")
        or record.get("duration")
        or record.get("elapsed_seconds")
    )
    m.duration_seconds_total += dur
    if dur > m.duration_seconds_max:
        m.duration_seconds_max = dur
    m.records_total += _as_int(
        record.get("records")
        or record.get("records_total")
        or record.get("volume")
        or record.get("items")
    )
    # HTTP class counters (may appear on success or failure records)
    for key in ("http_status", "status_code", "http_statuses"):
        val = record.get(key)
        if isinstance(val, list):
            for item in val:
                cls = _classify_http(item)
                if cls == "403":
                    m.http_403 += 1
                elif cls == "429":
                    m.http_429 += 1
                elif cls == "5xx":
                    m.http_5xx += 1
        else:
            cls = _classify_http(val)
            if cls == "403":
                m.http_403 += 1
            elif cls == "429":
                m.http_429 += 1
            elif cls == "5xx":
                m.http_5xx += 1
    # Explicit counters on record
    m.http_403 += _as_int(record.get("http_403_count"))
    m.http_429 += _as_int(record.get("http_429_count"))
    m.http_5xx += _as_int(record.get("http_5xx_count"))
    m.timeouts += _as_int(record.get("timeout_count"))
    if _is_timeout(record):
        m.timeouts += 1
    ts = record.get("finished_at") or record.get("ended_at") or record.get("at") or record.get("timestamp")
    if ts:
        m.last_run_at = str(ts)


def load_histories(roots: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        hist = RunHistory(root)
        rows.extend(hist.load_all())
    return rows


def aggregate(
    records: list[dict[str, Any]],
) -> dict[str, SourceMetrics]:
    metrics: dict[str, SourceMetrics] = {}
    for rec in records:
        ingest_record(metrics, rec)
    return metrics


def build_report(
    *,
    history_roots: list[Path] | None = None,
    sample_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Explicit empty list means "no roots" (tests); None means project defaults.
    roots = list(DEFAULT_HISTORY_ROOTS) if history_roots is None else list(history_roots)
    records = load_histories(roots)
    if sample_records:
        records = list(records) + list(sample_records)
    by_source = aggregate(records)
    sources = [m.to_dict() for m in sorted(by_source.values(), key=lambda x: x.source)]
    totals = {
        "runs": sum(m.runs for m in by_source.values()),
        "successes": sum(m.successes for m in by_source.values()),
        "failures": sum(m.failures for m in by_source.values()),
        "records_total": sum(m.records_total for m in by_source.values()),
        "duration_seconds_total": sum(m.duration_seconds_total for m in by_source.values()),
        "http_403": sum(m.http_403 for m in by_source.values()),
        "http_429": sum(m.http_429 for m in by_source.values()),
        "http_5xx": sum(m.http_5xx for m in by_source.values()),
        "timeouts": sum(m.timeouts for m in by_source.values()),
    }
    if totals["runs"] > 0:
        totals["success_rate"] = totals["successes"] / totals["runs"]
        overall = "ok"
        limitations: list[str] = []
    else:
        totals["success_rate"] = None
        overall = "unknown"
        limitations = [
            "Nenhum run_history encontrado — métricas de crawler não inventadas.",
            "Execute crawlers com RunHistory.append ou passe --seed-demo para demo local.",
        ]
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "overall": overall,
        "history_roots": [str(p) for p in roots],
        "sources": sources,
        "totals": totals,
        "monitored": {
            "duration": True,
            "success_rate": True,
            "volume": True,
            "http_403": True,
            "http_429": True,
            "http_5xx": True,
            "timeouts": True,
        },
        "limitations": limitations if totals["runs"] == 0 else [
            "Métricas derivadas de RunHistory JSONL; ausência de histórico ≠ crawler saudável.",
        ],
        "claims": {
            "allowed": [
                "Reportar duração/taxa/volume/HTTP a partir de histórico real",
                "overall=unknown quando N=0 runs",
            ],
            "forbidden": [
                "Cobertura operacional 95% a partir de crawler_monitor",
                "Crawler saudável sem runs registrados",
            ],
        },
    }


def seed_demo_records() -> list[dict[str, Any]]:
    """Deterministic sample for self-check / unit tests (not live ops)."""
    return [
        {
            "source": "pncp",
            "success": True,
            "duration_seconds": 12.5,
            "records": 40,
            "http_status": 200,
            "finished_at": "2026-07-18T12:00:00Z",
        },
        {
            "source": "pncp",
            "success": False,
            "duration_seconds": 30.0,
            "records": 0,
            "http_status": 429,
            "error": "rate limited",
            "finished_at": "2026-07-18T12:05:00Z",
        },
        {
            "source": "ciga_dom",
            "success": False,
            "duration_seconds": 5.0,
            "records": 0,
            "http_status": 403,
            "finished_at": "2026-07-18T12:06:00Z",
        },
        {
            "source": "ciga_dom",
            "success": False,
            "duration_seconds": 60.0,
            "records": 0,
            "http_status": 503,
            "error": "timeout waiting for response",
            "finished_at": "2026-07-18T12:07:00Z",
        },
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Crawler metrics monitor (DoD §23)")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--history-root",
        action="append",
        default=[],
        help="Extra RunHistory root (repeatable)",
    )
    p.add_argument(
        "--seed-demo",
        action="store_true",
        help="Include deterministic demo records (for self-check, not live claims)",
    )
    args = p.parse_args(argv)
    roots = [Path(x) for x in args.history_root] if args.history_root else None
    if roots is None:
        roots = list(DEFAULT_HISTORY_ROOTS)
    else:
        roots = roots + list(DEFAULT_HISTORY_ROOTS)
    samples = seed_demo_records() if args.seed_demo else None
    report = build_report(history_roots=roots, sample_records=samples)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"overall={report['overall']} runs={report['totals']['runs']}")
        t = report["totals"]
        print(
            f"  success_rate={t.get('success_rate')} "
            f"volume={t['records_total']} "
            f"dur_s={t['duration_seconds_total']:.1f} "
            f"403={t['http_403']} 429={t['http_429']} 5xx={t['http_5xx']} "
            f"timeouts={t['timeouts']}"
        )
        for s in report["sources"]:
            print(
                f"  [{s['source']}] runs={s['runs']} "
                f"ok_rate={s['success_rate']} vol={s['records_total']}"
            )
        for lim in report.get("limitations") or []:
            print(f"  limitation: {lim}")
    if report["overall"] == "unknown" and not args.seed_demo:
        return 0  # honest empty is not a crash
    return 0


if __name__ == "__main__":
    sys.exit(main())
