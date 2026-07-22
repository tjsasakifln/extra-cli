"""DoD §12.1 — golden path generates domain-specific contratos report (not panorama)."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.reports.contratos_report import write_contratos_report

pytestmark = pytest.mark.real_db
REPO = Path(__file__).resolve().parents[1]


def test_help_documents_execute_contratos_report_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-contratos-report-only" in (r.stdout + r.stderr)


def test_write_contratos_report_domain_file(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    # Ensure table exists; seed one synthetic contract if empty
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
                )
                """
            )
            if not cur.fetchone()[0]:
                pytest.skip("pncp_supplier_contracts missing")
            cur.execute("SELECT count(*) FROM pncp_supplier_contracts WHERE COALESCE(is_active,true)")
            n = int(cur.fetchone()[0])
            if n == 0:
                # Best-effort seed; if columns differ, report still writes header-only honestly
                try:
                    cur.execute(
                        """
                        INSERT INTO pncp_supplier_contracts (
                          orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
                          valor_total, is_active
                        ) VALUES (
                          '00000000000191', 'Orgao Teste', '11111111000191', 'Fornecedor Teste',
                          1000.0, true
                        )
                        """
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
        conn.close()
    except Exception as exc:
        pytest.skip(f"cannot inspect contracts table: {exc}")

    out = write_contratos_report(dsn, out_dir=tmp_path)
    assert out.get("ok") is True
    path = Path(out["path"])
    assert path.is_file()
    assert path.stat().st_size >= 50
    assert "relatorio-contratos" in path.name
    assert "panorama" not in path.name.lower()
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for col in ("ente_id", "n_contratos", "valor_total"):
            assert col in fieldnames
    assert out.get("json_path")
    side = json.loads(Path(out["json_path"]).read_text(encoding="utf-8"))
    assert side.get("report_type") == "contratos"
    assert "limitations" in side and side["limitations"]
    assert side.get("git_sha")
    assert "LOCAL_READY" in str(side.get("claims_forbidden"))


def test_cli_execute_contratos_report_only(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no test-db")

    ledger = tmp_path / "ledger-contratos.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--execute-contratos-report-only",
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
    assert "contratos_report" in names
    edit = next(s for s in steps if s.get("step") == "contratos_report")
    assert edit.get("status") == "pass"
    details = edit.get("details") or {}
    assert "relatorio-contratos" in str(details.get("path", ""))
    assert details.get("ok") is True
    assert Path(details["path"]).is_file()
    assert Path(details["path"]).stat().st_size >= 50
    jpath = details.get("json_path")
    assert jpath and Path(jpath).is_file()
    side = json.loads(Path(jpath).read_text(encoding="utf-8"))
    assert side.get("report_type") == "contratos"
    assert "limitations" in side
