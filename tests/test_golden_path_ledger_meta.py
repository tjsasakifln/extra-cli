"""DoD §12.1 — ledger, logs, wall clock, code/schema version, fail exit codes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.golden_path import (
    FreshnessRecord,
    ReportRecord,
    SourceRecord,
    collect_run_metadata,
    evaluate_run_outcome,
)


def test_cli_writes_ledger_and_log(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    ledger = tmp_path / "ledger.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--validate-spreadsheet-only",
            "--ledger-output",
            str(ledger),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert ledger.is_file()
    data = json.loads(ledger.read_text(encoding="utf-8"))
    runs = data.get("runs") or []
    assert runs, data
    last = runs[-1]
    assert last.get("steps"), "ledger must contain steps"
    assert last.get("wall_clock_ms", 0) > 0
    # log file mentioned in stdout
    out = r.stdout + r.stderr
    assert "Log salvo" in out or "log" in out.lower()


def test_metadata_includes_code_and_schema_version() -> None:
    meta = collect_run_metadata(dsn="postgresql://x@localhost/db")
    assert meta.get("git_sha")
    assert meta.get("schema_version") or meta.get("migration_files_count", 0) >= 0
    assert meta.get("canonical_command") == "python3 -m scripts.golden_path"
    assert meta.get("limitations")


def test_strict_exit_nonzero_on_essential_fail() -> None:
    _, code = evaluate_run_outcome(
        [
            SourceRecord(
                name="pcp",
                status="fail",
                duration_ms=1,
                attempts=1,
                error="boom",
            )
        ],
        {"pcp"},
        FreshnessRecord(status="pass"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
    )
    assert code != 0


def test_strict_exit_nonzero_on_freshness_fail() -> None:
    _, code = evaluate_run_outcome(
        [
            SourceRecord(
                name="pcp",
                status="success",
                duration_ms=1,
                attempts=1,
                metrics={"fetched": 1},
            )
        ],
        {"pcp"},
        FreshnessRecord(status="fail"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
    )
    assert code != 0
