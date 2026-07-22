"""DoD §12.1 — golden path calculates dual capability coverage (canonical)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import run_coverage_calculation


def _require_real_db() -> str:
    """Opt-in real PostgreSQL (conftest mocks psycopg2 otherwise)."""
    if os.getenv("REQUIRE_REAL_DB", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("REQUIRE_REAL_DB=1 required for live dual coverage")
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        psycopg2.connect(dsn, connect_timeout=3).close()
    except Exception:
        pytest.skip("no local test-db")
    return dsn


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


@pytest.mark.real_db
def test_coverage_live_clean_db() -> None:
    dsn = _require_real_db()
    root = Path(__file__).resolve().parents[1]
    rec = run_coverage_calculation(dsn, project_root=root)
    d = rec.details or {}
    assert d.get("method") == "dual_capability_coverage"
    assert d.get("method") not in {"entity_coverage.any_row", "entity_coverage.is_covered"}
    # Identity unresolved (ambiguous CNPJ in seed) fails measurement closed.
    mm = d.get("mapping_metrics") or {}
    identity_bad = int(mm.get("identity_unresolved_count") or 0) > 0
    if identity_bad:
        assert rec.status == "fail", (rec.error, d)
        assert d.get("measurement_success") is False
        assert "identity_unresolved" in str(d.get("error") or rec.error or "").lower()
        assert mm.get("mapping_status") == "identity_unresolved"
        assert d.get("dual_gate_status") == "NOT_READY"
    else:
        assert rec.status == "pass", (rec.error, d)
        assert d.get("measurement_success") is True
        assert d.get("dual_gate_status") in {"FAIL", "PASS"}
    # Low coverage / incomplete identity is not gate pass
    assert d.get("coverage_gate_pass") is False
    assert d.get("scope_complete") is True
    assert d.get("pipeline_success") is False
    caps = d.get("capabilities") or {}
    assert "open_tenders" in caps
    assert "historical_contracts" in caps
    for name, block in caps.items():
        assert "applicable_denominator" in block
        assert "covered_numerator" in block
        assert "coverage_pct" in block
        assert "gate_status" in block
        assert "data_presence_pct" in block
        assert "never_checked_count" in block or "pending_count" in block
        assert block.get("method") == "dual_capability_coverage"
    # legacy single fields mirror open_tenders for transition
    assert d.get("denominator") == caps["open_tenders"]["applicable_denominator"]
    assert "public_tables" not in d
    # identity stamps present
    assert d.get("seed_sha256")
    assert d.get("canonical_ids_sha256")


def test_dual_coverage_only_exits_nonzero_when_gates_fail() -> None:
    """CLI dual mode must not claim overall success when gates FAIL.

    Subprocess is outside conftest psycopg2 mock — needs reachable DSN.
    """
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
    combined = r.stdout + r.stderr
    # With identity_unresolved on live seed, measurement fails (exit 1);
    # otherwise gate fails (exit 2). Never overall success for empty dual gates.
    assert r.returncode in {1, 2}, (r.returncode, combined[-800:])
    assert r.returncode != 0
    assert (
        "coverage_gate_failed" in combined
        or "coverage_gate_pass=False" in combined
        or "measurement" in combined.lower()
        or "identity_unresolved" in combined.lower()
        or "FALHOU" in combined
    )
