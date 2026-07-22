"""DoD §12.1 — golden path generates domain-specific concorrentes report."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.reports.concorrentes_report import write_concorrentes_report

pytestmark = pytest.mark.real_db
REPO = Path(__file__).resolve().parents[1]


def test_help_documents_execute_concorrentes_report_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-concorrentes-report-only" in (r.stdout + r.stderr)


def test_write_concorrentes_report_domain_file(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    out = write_concorrentes_report(dsn, out_dir=tmp_path)
    assert out.get("ok") is True
    path = Path(out["path"])
    assert path.is_file()
    assert path.stat().st_size >= 50
    assert "relatorio-concorrentes" in path.name
    assert "panorama" not in path.name.lower()
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for col in ("concorrente_id", "n_contratos"):
            assert col in fieldnames
    side = json.loads(Path(out["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "concorrentes"
    assert side.get("limitations")
    assert side.get("git_sha")
    assert "LOCAL_READY" in str(side.get("claims_forbidden"))


def test_cli_execute_concorrentes_report_only(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    ledger = tmp_path / "ledger-concorrentes.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--execute-concorrentes-report-only",
            "--dsn",
            dsn,
            "--ledger-output",
            str(ledger),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(ledger.read_text(encoding="utf-8"))
    last = (data.get("runs") or [])[-1]
    step = next(s for s in last.get("steps") or [] if s.get("step") == "concorrentes_report")
    assert step.get("status") == "pass"
    details = step.get("details") or {}
    assert "relatorio-concorrentes" in str(details.get("path", ""))
    assert details.get("ok") is True
    side = json.loads(Path(details["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "concorrentes"
