"""DoD §12.1 — golden path generates domain-specific referências de valores report."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.reports.valores_report import write_valores_report

pytestmark = pytest.mark.real_db
REPO = Path(__file__).resolve().parents[1]


def test_help_documents_execute_valores_report_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-valores-report-only" in (r.stdout + r.stderr)


def test_write_valores_report_domain_file(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    out = write_valores_report(dsn, out_dir=tmp_path)
    assert out.get("ok") is True
    path = Path(out["path"])
    assert path.is_file() and path.stat().st_size >= 50
    assert "relatorio-valores" in path.name
    assert "panorama" not in path.name.lower()
    with path.open(encoding="utf-8") as fh:
        fieldnames = (csv.DictReader(fh).fieldnames) or []
        for col in ("modalidade", "n", "valor_semantica"):
            assert col in fieldnames
    side = json.loads(Path(out["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "referencias_valores"
    assert side.get("limitations")
    assert side.get("git_sha")
    assert "LOCAL_READY" in str(side.get("claims_forbidden"))


def test_cli_execute_valores_report_only(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    ledger = tmp_path / "ledger-valores.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--execute-valores-report-only",
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
    step = next(s for s in last.get("steps") or [] if s.get("step") == "valores_report")
    assert step.get("status") == "pass"
    details = step.get("details") or {}
    assert "relatorio-valores" in str(details.get("path", ""))
    side = json.loads(Path(details["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "referencias_valores"
