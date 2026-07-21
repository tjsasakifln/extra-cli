"""DoD §12.1 — golden path can run in a clean environment."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_help_documents_skip_sources() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "skip-sources" in (r.stdout + r.stderr)


def test_clean_env_dry_run() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.ops.golden_clean_env", "--dry-run"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "would_drop_create" in (r.stdout + r.stderr)


def test_clean_env_refuses_without_confirm() -> None:
    env = os.environ.copy()
    env["LOCAL_DATALAKE_DSN"] = env.get(
        "LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    r = subprocess.run(
        [sys.executable, "-m", "scripts.ops.golden_clean_env", "--db-name", "extra_clean_refuse"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 3
    assert "confirm-drop" in (r.stdout + r.stderr).lower() or "REFUSING" in (r.stdout + r.stderr)


@pytest.mark.real_db
def test_clean_env_confirm_drop_runs(tmp_path: Path) -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no admin DB")
    report = tmp_path / "clean-env-report.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.golden_clean_env",
            "--confirm-drop",
            "--db-name",
            "extra_clean_pytest",
            "--admin-dsn",
            dsn,
            "--report",
            str(report),
        ],
        cwd=REPO,
        env={**os.environ, "LOCAL_DATALAKE_DSN": dsn},
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert report.is_file(), (r.stdout, r.stderr)
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data.get("steps", {}).get("recreate_db", {}).get("ok") is True
    assert data.get("steps", {}).get("migrations", {}).get("ok") is True
    assert int(data.get("steps", {}).get("public_tables") or 0) >= 5
    assert data.get("ok") is True, data
    assert r.returncode == 0
