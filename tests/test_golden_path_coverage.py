"""DoD §12.1 — golden path calculates dual capability coverage (canonical)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import run_coverage_calculation


def test_help_documents_coverage_modes() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    help_text = r.stdout + r.stderr
    assert "execute-coverage-only" in help_text
    assert "execute-dual-coverage-only" in help_text
    assert "capability" in help_text


def test_coverage_rejects_wrong_denominator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed when universe size != expected denominator."""

    from scripts.coverage import dual_capability_coverage as dcc
    from scripts.lib.universe import CanonicalEntity, CanonicalUniverse

    ent = CanonicalEntity(
        entity_id="only-one",
        seed_row=2,
        razao_social="X",
        cnpj8="12345678",
        municipio="Y",
        codigo_ibge="4205407",
        natureza_juridica="M",
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="seed",
        identity_key="k",
    )
    fake_u = CanonicalUniverse(
        seed_path="fake.xlsx",
        seed_sha256="b" * 64,
        radius_km=200.0,
        entities=[ent],
    )

    monkeypatch.setattr(dcc, "load_canonical_universe", lambda **k: fake_u)
    monkeypatch.setattr(dcc, "resolve_default_seed_path", lambda root=None: Path("/tmp/fake-seed.xlsx"))

    root = Path(__file__).resolve().parents[1]
    rec = run_coverage_calculation(
        "postgresql://x",
        project_root=root,
        expected_denominator=1093,
        capabilities=["open_tenders"],
    )
    assert rec.status == "fail"
    assert "denominator" in (rec.error or "").lower() or "unexpected" in (rec.error or "").lower()


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
    assert d.get("method") == "dual_capability_coverage"
    assert d.get("method") not in {"entity_coverage.any_row", "entity_coverage.is_covered"}
    assert d.get("measurement_success") is True
    # Low coverage is measurement success, not gate pass
    assert d.get("coverage_gate_pass") is False
    caps = d.get("capabilities") or {}
    assert "open_tenders" in caps
    assert "historical_contracts" in caps
    for name, block in caps.items():
        assert "applicable_denominator" in block
        assert "covered_numerator" in block
        assert "coverage_pct" in block
        assert "gate_status" in block
        assert "data_presence_pct" in block
        assert block.get("method") == "dual_capability_coverage"
    # legacy single fields mirror open_tenders for transition
    assert d.get("denominator") == caps["open_tenders"]["applicable_denominator"]
    assert "public_tables" not in d


def test_dual_coverage_only_exits_nonzero_when_gates_fail() -> None:
    """CLI dual mode must not claim overall success when gates FAIL."""
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no local test-db")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--execute-dual-coverage-only",
            "--capability",
            "both",
            "--dsn",
            dsn,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 2, (r.returncode, r.stdout[-500:], r.stderr[-500:])
    combined = r.stdout + r.stderr
    assert "coverage_gate_failed" in combined or "coverage_gate_pass=False" in combined
