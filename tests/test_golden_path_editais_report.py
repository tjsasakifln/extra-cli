"""DoD §12.1 — golden path generates domain-specific editais report (not panorama)."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.reports.editais_report import write_editais_report

pytestmark = pytest.mark.real_db
REPO = Path(__file__).resolve().parents[1]


def test_help_documents_execute_editais_report_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-editais-report-only" in (r.stdout + r.stderr)


def test_write_editais_report_domain_file(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    # Ensure at least one active bid for strong path (synthetic OK)
    try:
        import hashlib

        import psycopg2

        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema='public' AND table_name='pncp_raw_bids'
                )
                """
            )
            if not cur.fetchone()[0]:
                pytest.skip("pncp_raw_bids missing")
            cur.execute("SELECT count(*) FROM pncp_raw_bids WHERE COALESCE(is_active,true)")
            n = int(cur.fetchone()[0])
            if n == 0:
                pid = "SYNTH-EDITAIS-REPORT-0001"
                ch = hashlib.sha256(pid.encode()).hexdigest()
                cur.execute(
                    """
                    INSERT INTO pncp_raw_bids (pncp_id, objeto_compra, uf, source, content_hash, is_active, synthetic_id)
                    VALUES (%s, %s, 'SC', 'pncp', %s, true, true)
                    ON CONFLICT (pncp_id) DO NOTHING
                    """,
                    (pid, "Objeto edital teste relatório", ch),
                )
                conn.commit()
        conn.close()
    except Exception as exc:
        pytest.skip(f"cannot seed bid: {exc}")

    out = write_editais_report(dsn, out_dir=tmp_path)
    assert out.get("ok") is True
    path = Path(out["path"])
    assert path.is_file()
    assert path.stat().st_size >= 50
    assert "relatorio-editais" in path.name
    # not panorama
    assert "panorama" not in path.name.lower()
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for col in ("pncp_id", "objeto_compra", "uf"):
            assert col in fieldnames
        rows = list(reader)
    assert out.get("row_count", 0) >= 1
    assert rows, "expected at least one editais row"
    assert out.get("json_path")
    side = json.loads(Path(out["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "editais"
    assert "limitations" in side and side["limitations"]
    assert side.get("git_sha")
    assert "LOCAL_READY" in str(side.get("claims_forbidden"))


def test_cli_execute_editais_report_only(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    ledger = tmp_path / "ledger-editais.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--execute-editais-report-only",
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
    assert ledger.is_file()
    data = json.loads(ledger.read_text(encoding="utf-8"))
    last = (data.get("runs") or [])[-1]
    steps = last.get("steps") or []
    names = [s.get("step") for s in steps]
    assert "editais_report" in names
    edit = next(s for s in steps if s.get("step") == "editais_report")
    assert edit.get("status") == "pass"
    details = edit.get("details") or {}
    assert details.get("row_count", 0) >= 0
    assert "relatorio-editais" in str(details.get("path", ""))
