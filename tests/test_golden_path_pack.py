"""Golden path commercial pack — real CSVs + non-empty PDF."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.reports.golden_path_pack import build_pack


def test_build_pack_writes_pdf_and_csvs(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    man = build_pack(dsn=dsn, output_dir=tmp_path, run_id="test-pack-1")
    assert "paths" in man
    pdf = Path(man["paths"]["pdf"])
    assert pdf.is_file()
    assert pdf.stat().st_size > 200  # not empty stub
    for kind in ("editais", "contratos", "concorrentes", "referencias_valores"):
        p = Path(man["paths"][kind])
        assert p.is_file()
    assert (tmp_path / "test-pack-1" / "manifest.json").is_file()
    assert man["claims"]["forbidden"]


def test_cli_json() -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.reports.golden_path_pack",
            "--dsn",
            dsn,
            "--json",
            "--run-id",
            "cli-pack",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    body = json.loads(r.stdout)
    assert Path(body["paths"]["pdf"]).is_file()
