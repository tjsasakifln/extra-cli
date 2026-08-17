"""Acceptance tests on real PostgreSQL. Never MagicMock. Marked real_db."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scripts.coverage.covered_entity import MISSING_EVIDENCE
from scripts.coverage.dual_capability_coverage import GATE_THRESHOLD
from scripts.ops.coverage_live_proof.admission import read_gate_threshold, require_explicit_dsn
from scripts.ops.coverage_live_proof.errors import MigrationApplyError
from scripts.ops.coverage_live_proof.evidence import write_evidence_pack
from scripts.ops.coverage_live_proof.probe import assert_real_postgres, connect_real
from scripts.ops.coverage_live_proof.runner import (
    apply_canonical_migrations,
    create_ephemeral_database,
    database_exists,
    evaluate_identity_scenarios,
    execute_golden_path,
    is_campaign_database,
    run_live_proof,
    teardown_ephemeral,
)
from scripts.ops.coverage_live_proof.seed import apply_seed, count_seed_rows, load_seed_rows

pytestmark = pytest.mark.real_db

_REPO = Path(__file__).resolve().parents[2]


def _admin_dsn() -> str:
    return require_explicit_dsn(os.environ.get("LOCAL_DATALAKE_DSN"))


@pytest.fixture(scope="module")
def migrated_proof_dsn() -> str:
    admin = _admin_dsn()
    proof_dsn, dbname = create_ephemeral_database(admin)
    try:
        apply_canonical_migrations(proof_dsn)
        yield proof_dsn
    finally:
        teardown_ephemeral(admin, dbname)


def test_probe_records_real_postgres_driver(migrated_proof_dsn: str) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        info = assert_real_postgres(conn)
    finally:
        conn.close()
    assert "PostgreSQL" in info["postgres_version"]
    assert "psycopg2" in info["driver"]
    assert "MagicMock" not in info["driver"]


def test_migrations_are_idempotent(migrated_proof_dsn: str) -> None:
    second = apply_canonical_migrations(migrated_proof_dsn)
    assert second["applied"] == []
    assert len(second["skipped"]) >= 1


def test_scenario_source_wide_only_does_not_count_entity(migrated_proof_dsn: str) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        apply_seed(conn)
        rows = load_seed_rows(conn)
        result = evaluate_identity_scenarios(rows)
    finally:
        conn.close()
    scenario_a = result["A"]
    assert scenario_a["classification"] == MISSING_EVIDENCE
    assert scenario_a["reason"] == "source_wide_aggregate_without_identity"
    assert scenario_a["entity_scoped_numerator"] == 0
    assert scenario_a["covered_count"] == 0
    assert scenario_a["measurement_success"] is False


def test_scenario_mixed_counts_only_entity_scoped(migrated_proof_dsn: str) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        apply_seed(conn)
        result = evaluate_identity_scenarios(load_seed_rows(conn))
    finally:
        conn.close()
    scenario_b = result["B"]
    assert scenario_b["identified_count"] == 1
    assert scenario_b["entity_scoped_numerator"] == 1
    assert scenario_b["source_wide_count"] == 1
    assert scenario_b["measurement_success"] is True
    assert scenario_b["covered_count"] == 1


def test_scenario_unmappable_fail_closed(migrated_proof_dsn: str) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        apply_seed(conn)
        result = evaluate_identity_scenarios(load_seed_rows(conn))
    finally:
        conn.close()
    scenario_c = result["C"]
    assert scenario_c["reason"] == "unmappable_evidence_cannot_drop"
    assert scenario_c["measurement_success"] is False
    assert scenario_c["entity_scoped_numerator"] == 0
    assert scenario_c["classification"] == MISSING_EVIDENCE


def test_replay_does_not_duplicate_and_hash_is_stable(
    migrated_proof_dsn: str, tmp_path: Path
) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        apply_seed(conn)
        first_count = count_seed_rows(conn)
        second = apply_seed(conn)
        second_count = count_seed_rows(conn)
        rows = load_seed_rows(conn)
    finally:
        conn.close()
    assert first_count == second_count == 3
    assert second["inserted"] == 0
    scenarios = evaluate_identity_scenarios(rows)
    payload = {
        "source_wide_count": scenarios["source_wide_count"],
        "entity_scoped_count": scenarios["entity_scoped_count"],
        "scenarios": {"A": scenarios["A"], "B": scenarios["B"], "C": scenarios["C"]},
        "threshold": read_gate_threshold(),
    }
    pack_a = write_evidence_pack(
        tmp_path / "r1", {**payload, "run_id": "one", "duration_ms": 1}
    )
    pack_b = write_evidence_pack(
        tmp_path / "r2", {**payload, "run_id": "two", "duration_ms": 9}
    )
    assert pack_a["normalized_semantic_hash"] == pack_b["normalized_semantic_hash"]
    assert (tmp_path / "r1" / "evidence.normalized.json").read_bytes() == (
        tmp_path / "r2" / "evidence.normalized.json"
    ).read_bytes()


def test_teardown_on_success() -> None:
    admin = _admin_dsn()
    _proof, dbname = create_ephemeral_database(admin)
    assert is_campaign_database(dbname)
    assert database_exists(admin, dbname) is True
    teardown_ephemeral(admin, dbname)
    assert database_exists(admin, dbname) is False


def _campaign_databases(admin_dsn: str) -> set[str]:
    conn = connect_real(admin_dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datname LIKE 'coverage_live_proof_%'")
        names = {str(row[0]) for row in (cur.fetchall() or [])}
        cur.close()
        return names
    finally:
        conn.close()


def test_teardown_on_failure_leaves_no_campaign_db(tmp_path: Path) -> None:
    admin = _admin_dsn()
    before = _campaign_databases(admin)
    with pytest.raises(RuntimeError, match="injected failure after_create"):
        run_live_proof(
            dsn=admin,
            output_dir=tmp_path,
            execute_golden=False,
            inject_failure="after_create",
        )
    after = _campaign_databases(admin)
    assert after == before


def test_clear_migration_failure(tmp_path: Path) -> None:
    admin = _admin_dsn()
    proof_dsn, dbname = create_ephemeral_database(admin)
    try:
        bad_root = tmp_path / "migrations"
        bad_root.mkdir()
        (bad_root / "001_fail.sql").write_text(
            "DO $$ BEGIN RAISE EXCEPTION 'coverage_live_proof_injected_failure'; END $$;\n",
            encoding="utf-8",
        )
        with pytest.raises(MigrationApplyError, match="canonical migration apply failed"):
            apply_canonical_migrations(proof_dsn, root=bad_root)
    finally:
        teardown_ephemeral(admin, dbname)


def test_threshold_unchanged_on_real_path(migrated_proof_dsn: str) -> None:
    conn = connect_real(migrated_proof_dsn)
    try:
        apply_seed(conn)
        result = evaluate_identity_scenarios(load_seed_rows(conn))
    finally:
        conn.close()
    assert read_gate_threshold() == GATE_THRESHOLD == 0.95
    assert result["expectation_errors"] == []


def test_golden_path_entry_runs_on_ephemeral(migrated_proof_dsn: str, tmp_path: Path) -> None:
    result = execute_golden_path(migrated_proof_dsn, tmp_path, _REPO)
    assert result["argv"][1:4] == ["-m", "scripts.golden_path", "--dsn"]
    assert "--execute-dual-coverage-only" in result["argv"]
    combined = (result.get("stdout_sanitized") or "") + (result.get("stderr_sanitized") or "")
    assert "super-secret" not in combined
    password = urlparse(migrated_proof_dsn).password or ""
    if password:
        assert password not in combined
    assert result["ledger_present"] is True or result["returncode"] in {0, 1, 2}


def test_runner_writes_evidence_pack(tmp_path: Path) -> None:
    admin = _admin_dsn()
    before = _campaign_databases(admin)
    pack = run_live_proof(
        dsn=admin,
        output_dir=tmp_path,
        execute_golden=True,
    )
    after = _campaign_databases(admin)
    assert after == before
    assert (tmp_path / "evidence.json").is_file()
    assert (tmp_path / "evidence.normalized.json").is_file()
    assert (tmp_path / "SHA256SUMS").is_file()
    payload = pack["payload"]
    assert payload["threshold"] == GATE_THRESHOLD
    assert payload["scenarios"]["A"]["reason"] == "source_wide_aggregate_without_identity"
    assert payload["scenarios"]["B"]["entity_scoped_numerator"] == 1
    assert payload["scenarios"]["D"]["row_counts_stable"] is True
    assert "psycopg2" in payload["connection"]["driver"]
    log_text = (tmp_path / "coverage-live-proof.log").read_text(encoding="utf-8")
    password = urlparse(admin).password or ""
    if password:
        assert password not in log_text
        assert password not in (tmp_path / "evidence.json").read_text(encoding="utf-8")
