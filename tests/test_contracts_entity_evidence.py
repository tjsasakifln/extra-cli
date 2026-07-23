"""Adapter: contracts crawl lineage → per-entity coverage_evidence."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.coverage.contracts_entity_evidence import (
    CheckpointWindowProof,
    assert_success_zero_proof,
    default_backfill_window,
    load_checkpoint_window_proof,
    project_historical_contracts_evidence,
)
from scripts.coverage.dual_capability_coverage import (
    contracts_backfill_ok,
    EvidenceObservation,
)
from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path


def _valid_multi_window_proof(
    tmp_path: Path,
    *,
    planned: int = 3,
    completed: int | None = None,
    pages: int = 50,
) -> Path:
    n = planned if completed is None else completed
    windows = [f"20230101_20230130_w{i}" for i in range(n)]
    payload = {
        "planned_windows": planned,
        "completed_windows": windows,
        "total_windows_failed": 0,
        "total_pages": pages,
        "pages_processed": pages,
        "meta": {"run_ids": ["run-proof-1"], "planned_windows": planned},
    }
    path = tmp_path / "contracts_full_proof.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_backfill_window_meets_three_year_math() -> None:
    start, end = default_backfill_window()
    years = (end - start).days / 365.25
    assert years + 1e-9 >= 3.0
    obs = EvidenceObservation(
        entity_id="e",
        source="pncp",
        capability="historical_contracts",
        state="success_zero",
        applicability="applicable",
        run_id="r",
        queried_start=start.isoformat(),
        queried_end=end.isoformat(),
    )
    from datetime import UTC, datetime

    assert contracts_backfill_ok(obs, as_of=datetime.now(UTC)) is True


def test_manual_flags_alone_cannot_attest_success_zero() -> None:
    """Adversarial: --window-complete --pages 1/1 without proof is rejected."""
    errs = assert_success_zero_proof(
        window_complete=True,
        proof=None,
        pages_processed=1,
        pages_expected=1,
    )
    assert errs
    assert any("checkpoint" in e.lower() or "proof" in e.lower() for e in errs)


def test_incomplete_checkpoint_cannot_attest_success_zero(tmp_path: Path) -> None:
    path = _valid_multi_window_proof(tmp_path, planned=37, completed=28, pages=100)
    proof = load_checkpoint_window_proof(path, require_all_planned=True)
    assert proof.valid is False
    errs = assert_success_zero_proof(
        window_complete=True,
        proof=proof,
        pages_processed=proof.pages_processed,
        pages_expected=proof.pages_expected,
    )
    assert errs


def test_complete_checkpoint_allows_success_zero(tmp_path: Path) -> None:
    path = _valid_multi_window_proof(tmp_path, planned=3, completed=3, pages=40)
    proof = load_checkpoint_window_proof(path)
    assert proof.valid is True
    assert assert_success_zero_proof(
        window_complete=True,
        proof=proof,
        pages_processed=proof.pages_processed,
        pages_expected=proof.pages_expected,
    ) == []


def test_project_refuses_success_zero_without_proof() -> None:
    """Dry projection with window_complete flags but no proof writes zero success_zero."""

    class _FakeConn:
        def cursor(self):
            return self

        def execute(self, *a, **k):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

        def commit(self):
            return None

    start, end = default_backfill_window()
    report = project_historical_contracts_evidence(
        _FakeConn(),
        run_id="fabricate-1",
        period_start=start,
        period_end=end,
        window_complete=True,
        pages_processed=1,
        pages_expected=1,
        dry_run=True,
        only_with_data=False,
        seed_path=resolve_default_seed_path(),
        checkpoint_proof=None,
    )
    assert report.success_zero == 0
    assert any("success_zero blocked" in x or "proof" in x.lower() for x in report.limitations)


def test_project_dry_run_without_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run must not require live crawl; counts applicable universe."""

    class _FakeConn:
        def cursor(self):
            return self

        def execute(self, *a, **k):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

        def commit(self):
            return None

    start, end = default_backfill_window()
    report = project_historical_contracts_evidence(
        _FakeConn(),
        run_id="dry-1",
        period_start=start,
        period_end=end,
        window_complete=False,
        dry_run=True,
        only_with_data=True,
        seed_path=resolve_default_seed_path(),
    )
    assert report.dry_run is True
    assert report.applicable_count == len(
        load_canonical_universe(seed_path=resolve_default_seed_path()).included
    )
    assert report.success_zero == 0  # only_with_data + incomplete window
    assert report.written_rows == 0 or report.dry_run


@pytest.mark.real_db
def test_project_success_with_data_and_dual_mapping() -> None:
    """With window complete + empty lake, success_zero projects and dual maps via canonical key.

    Requires: REQUIRE_REAL_DB=1 and LOCAL_DATALAKE_DSN (conftest mocks psycopg2 otherwise).
    """
    import os

    if os.getenv("REQUIRE_REAL_DB", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("REQUIRE_REAL_DB=1 required for real PostgreSQL evidence projection")
    pytest.importorskip("psycopg2")
    import psycopg2

    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("TEST_DSN")
    if not dsn:
        pytest.skip("LOCAL_DATALAKE_DSN not set")
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres unavailable: {exc}")

    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE coverage_evidence RESTART IDENTITY")
        conn.commit()
        start, end = default_backfill_window()
        # Synthetic multi-window proof is allowed only for mapping tests (real_db),
        # not as operational campaign attestation (see campaign STATUS non-claims).
        proof = CheckpointWindowProof(
            path="pytest-synthetic-proof",
            completed_windows=tuple(f"w{i}" for i in range(3)),
            planned_windows=3,
            total_windows_failed=0,
            pages_processed=30,
            pages_expected=3,
            run_ids=("pytest-hc-evidence-1",),
            valid=True,
            errors=(),
        )
        report = project_historical_contracts_evidence(
            conn,
            run_id="pytest-hc-evidence-1",
            period_start=start,
            period_end=end,
            window_complete=True,
            completion_rule="national_window_complete",
            pages_processed=30,
            pages_expected=3,
            dry_run=False,
            seed_path=resolve_default_seed_path(),
            checkpoint_proof=proof,
        )
        assert report.applicable_count >= 1000
        assert report.written_rows == report.applicable_count * 2
        assert report.success_zero + report.success_with_data == report.applicable_count

        from scripts.coverage.dual_capability_coverage import compute_dual_coverage

        u = load_canonical_universe(seed_path=resolve_default_seed_path())
        dual = compute_dual_coverage(
            conn=conn,
            universe=u,
            seed_path=resolve_default_seed_path(),
            project_root=Path(__file__).resolve().parents[1],
            capabilities=("historical_contracts",),
        )
        assert "historical_contracts" in dual.capabilities
        hc = dual.capabilities["historical_contracts"]
        assert hc.applicability_unknown_count == 0
        assert hc.applicable_denominator == hc.universe_count
        assert hc.covered_numerator == hc.applicable_denominator
        assert hc.coverage_gate_pass is True
        # Cleanup so local ops DB is not left claiming operational PASS without live crawl
        cur.execute("TRUNCATE coverage_evidence RESTART IDENTITY")
        conn.commit()
    finally:
        conn.close()
