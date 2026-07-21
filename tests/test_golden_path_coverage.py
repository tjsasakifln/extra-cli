"""DoD §12.1 — golden path calculates coverage with canonical denominator."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import run_coverage_calculation


def test_help_documents_execute_coverage_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-coverage-only" in (r.stdout + r.stderr)


def test_coverage_rejects_wrong_denominator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed when universe size != expected denominator."""
    import types

    class FakeU:
        included = list(range(50))
        seed_sha256 = "y" * 64

    fake_mod = types.ModuleType("scripts.lib.universe")
    fake_mod.CANONICAL_UNIVERSE = 1093
    fake_mod.load_canonical_universe = lambda **k: FakeU()
    fake_mod.resolve_default_seed_path = lambda root=None: Path("/tmp/fake-seed.xlsx")
    monkeypatch.setitem(sys.modules, "scripts.lib.universe", fake_mod)
    root = Path(__file__).resolve().parents[1]
    rec = run_coverage_calculation("postgresql://x", project_root=root, expected_denominator=1093)
    assert rec.status == "fail"
    assert "denominator mismatch" in (rec.error or "")


def test_coverage_live_clean_db() -> None:
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no local test-db")
    root = Path(__file__).resolve().parents[1]
    rec = run_coverage_calculation(dsn, project_root=root)
    assert rec.status == "pass", (rec.error, rec.details)
    d = rec.details or {}
    assert d.get("denominator") == 1093
    assert d.get("numerator") is not None
    assert d.get("coverage_pct") is not None
    assert "public_tables" not in d
