"""DoD §23 crawler metrics — duration, success, volume, HTTP, timeouts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.crawl.resilience.state import RunHistory
from scripts.ops.crawler_monitor import (
    aggregate,
    build_report,
    seed_demo_records,
)


def test_seed_demo_aggregates_http_classes() -> None:
    metrics = aggregate(seed_demo_records())
    assert "pncp" in metrics
    assert "ciga_dom" in metrics
    pncp = metrics["pncp"]
    assert pncp.runs == 2
    assert pncp.http_429 == 1
    assert pncp.records_total == 40
    assert pncp.duration_seconds_total > 0
    assert pncp.success_rate == 0.5
    ciga = metrics["ciga_dom"]
    assert ciga.http_403 == 1
    assert ciga.http_5xx == 1
    assert ciga.timeouts >= 1


def test_build_report_with_samples() -> None:
    rep = build_report(history_roots=[], sample_records=seed_demo_records())
    assert rep["overall"] == "ok"
    assert rep["totals"]["runs"] == 4
    assert rep["monitored"]["duration"] is True
    assert rep["monitored"]["http_429"] is True
    assert rep["totals"]["http_403"] >= 1
    assert rep["totals"]["timeouts"] >= 1


def test_empty_history_is_unknown_not_green() -> None:
    rep = build_report(history_roots=[], sample_records=[])
    assert rep["overall"] == "unknown"
    assert rep["totals"]["runs"] == 0
    assert rep["limitations"]


def test_run_history_jsonl_roundtrip(tmp_path: Path) -> None:
    hist = RunHistory(tmp_path)
    for rec in seed_demo_records():
        hist.append(rec)
    rep = build_report(history_roots=[tmp_path])
    assert rep["totals"]["runs"] == 4
    assert rep["totals"]["records_total"] == 40


def test_cli_seed_demo_json() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.crawler_monitor",
            "--json",
            "--seed-demo",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["overall"] == "ok"
    assert body["totals"]["http_429"] >= 1
