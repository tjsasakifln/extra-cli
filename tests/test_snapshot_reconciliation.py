"""Tests for snapshot reconciliation algorithm (Story 1.4).

7 scenarios from Secao 8 of the master plan:
    1. Snapshot A (IDs 1,2,3) + Snapshot B complete (IDs 2,3) = ID 1 inativo
    2. Snapshot B parcial: ID 1 NAO inativado
    3. ID 1 reappears in C: reativado
    4. Execucao zero completa: todos os registros do escopo ficam inativos
    5. Execucao zero parcial: nenhum registro e alterado
    6. Concorrencia entre runs: apenas run finalizado reconcilia
    7. Idempotencia do mesmo run
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg2
import psycopg2.extras
import pytest

from scripts.opportunity_intel.reconciliation import SourceSnapshotReconciler

pytestmark = [
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database tests",
    ),
    pytest.mark.integration,
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dsn() -> str:
    """Test DSN from env or default local."""
    import os

    return os.getenv(
        "TEST_DATALAKE_DSN",
        "postgresql://postgres:@127.0.0.1:54399/postgres",
    )


@pytest.fixture
def conn(dsn: str) -> Any:
    """Create a test database connection."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture
def reconciler(dsn: str) -> SourceSnapshotReconciler:
    """Create reconciler instance."""
    return SourceSnapshotReconciler(dsn)


@pytest.fixture
def clean_test_data(conn: Any) -> None:
    """Remove test data before and after each test."""
    # Clean up before test
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM source_snapshot_membership WHERE source = 'test_pncp'")
        cursor.execute(
            "DELETE FROM opportunity_intel WHERE source = 'test_pncp' AND crawl_batch_id = 'test_reconciliation'"
        )
        cursor.execute(
            "DELETE FROM opportunity_runs WHERE source = 'test_pncp' AND metadata->>'test_reconciliation' = 'true'"
        )
    yield
    # Clean up after test
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM source_snapshot_membership WHERE source = 'test_pncp'")
        cursor.execute(
            "DELETE FROM opportunity_intel WHERE source = 'test_pncp' AND crawl_batch_id = 'test_reconciliation'"
        )
        cursor.execute(
            "DELETE FROM opportunity_runs WHERE source = 'test_pncp' AND metadata->>'test_reconciliation' = 'true'"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_run(
    conn: Any,
    status: str = "completed",
    scope_complete: bool = True,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Create a test run and return its ID."""
    payload = metadata or {}
    payload["test_reconciliation"] = "true"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO opportunity_runs (
                source, scope_key, status, scope_complete,
                started_at, finished_at, metadata
            ) VALUES (
                'test_pncp', 'uf=SC;modalidades=1-19', %s, %s,
                NOW(), NOW(), %s::jsonb
            ) RETURNING id
            """,
            (status, scope_complete, json.dumps(payload, default=str)),
        )
        return int(cursor.fetchone()[0])


def _create_opportunity(
    conn: Any,
    source_id: str,
    content_hash: str | None = None,
    source_active: bool = True,
) -> int:
    """Create a test opportunity and return its ID."""
    ch = content_hash or f"test_hash_{source_id}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO opportunity_intel (
                source, source_id, content_hash, numero_controle_pncp,
                objeto, uf, status_canonico, data_encerramento,
                is_active, source_active, crawl_batch_id
            ) VALUES (
                'test_pncp', %s, %s, %s,
                'Test object', 'SC', 'open', %s,
                TRUE, %s, 'test_reconciliation'
            )
            ON CONFLICT (content_hash) DO UPDATE SET
                source_active = EXCLUDED.source_active
            RETURNING id
            """,
            (
                source_id,
                ch,
                ch,
                datetime.now(UTC) + timedelta(days=30),
                source_active,
            ),
        )
        return int(cursor.fetchone()[0])


def _get_source_active(conn: Any, opportunity_id: int) -> bool:
    """Read source_active for an opportunity."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT source_active FROM opportunity_intel WHERE id = %s",
            (opportunity_id,),
        )
        return bool(cursor.fetchone()[0])


def _get_source_inactive_reason(conn: Any, opportunity_id: int) -> str | None:
    """Read source_inactive_reason for an opportunity."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT source_inactive_reason FROM opportunity_intel WHERE id = %s",
            (opportunity_id,),
        )
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] else None


# ===========================================================================
# Scenario 1: Snapshot A (IDs 1,2,3) + Snapshot B complete (IDs 2,3) = ID 1 inativo
# ===========================================================================


def test_scenario_1_complete_snapshot_inactivates_absent(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """After a complete snapshot, records not seen should be inactivated."""
    # Arrange: create 3 opportunities
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")
    id3 = _create_opportunity(conn, "SRC-003")

    # Complete run B that only sees IDs 2 and 3
    run_b = _create_run(conn, status="completed", scope_complete=True)
    records = [
        {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        {"source_id": "SRC-003", "numero_controle_pncp": "SRC-003"},
    ]
    reconciler.record_memberships(run_b, "test_pncp", records)

    # Act
    result = reconciler.reconcile(run_b, "test_pncp")

    # Assert
    assert result.skipped is False, f"Reconciliation should not be skipped: {result.skip_reason}"
    assert result.inactivated == 1, f"Expected 1 inactivated, got {result.inactivated}"
    assert result.reactivated == 0, f"Expected 0 reactivated, got {result.reactivated}"
    assert _get_source_active(conn, id1) is False, "ID 1 should be inactive"
    assert _get_source_active(conn, id2) is True, "ID 2 should remain active"
    assert _get_source_active(conn, id3) is True, "ID 3 should remain active"
    assert _get_source_inactive_reason(conn, id1) == "absent_from_complete_open_snapshot"


# ===========================================================================
# Scenario 2: Snapshot B parcial — ID 1 NAO inativado
# ===========================================================================


def test_scenario_2_partial_snapshot_never_inactivates(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """A partial run should NEVER inactivate records (fail-closed)."""
    # Arrange: create 3 opportunities all active
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")

    # Partial run (scope_complete = FALSE)
    run_partial = _create_run(conn, status="partial", scope_complete=False)
    records = [{"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"}]
    reconciler.record_memberships(run_partial, "test_pncp", records)

    # Act
    result = reconciler.reconcile(run_partial, "test_pncp")

    # Assert
    assert result.skipped is True, "Partial run should be skipped"
    assert result.inactivated == 0, "No records should be inactivated by partial run"
    assert _get_source_active(conn, id1) is True, "ID 1 should remain active"
    assert _get_source_active(conn, id2) is True, "ID 2 should remain active"

    # Also test with failed status
    run_failed = _create_run(conn, status="failed", scope_complete=False)
    result2 = reconciler.reconcile(run_failed, "test_pncp")
    assert result2.skipped is True, "Failed run should be skipped"
    assert result2.inactivated == 0, "No records should be inactivated by failed run"

    # Also test with running status
    run_running = _create_run(conn, status="running", scope_complete=False)
    result3 = reconciler.reconcile(run_running, "test_pncp")
    assert result3.skipped is True, "Running run should be skipped"


# ===========================================================================
# Scenario 3: ID 1 reaparece em C — reativado
# ===========================================================================


def test_scenario_3_reappearing_record_reactivates(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """A record that reappears in a later complete snapshot should be reactivated."""
    # Arrange: ID 1 is seen in run A, not in run B (gets inactivated)
    id1 = _create_opportunity(conn, "SRC-001")

    run_a = _create_run(conn, status="completed", scope_complete=True)
    reconciler.record_memberships(
        run_a,
        "test_pncp",
        [
            {"source_id": "SRC-001", "numero_controle_pncp": "SRC-001"},
        ],
    )

    run_b = _create_run(conn, status="completed", scope_complete=True)
    # Run B does NOT see ID 1
    reconciler.record_memberships(
        run_b,
        "test_pncp",
        [
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )

    # Inactivate ID 1 via run B
    reconciler.reconcile(run_b, "test_pncp")
    assert _get_source_active(conn, id1) is False, "ID 1 should be inactive after run B"

    # Act: Run C sees ID 1 again
    run_c = _create_run(conn, status="completed", scope_complete=True)
    reconciler.record_memberships(
        run_c,
        "test_pncp",
        [
            {"source_id": "SRC-001", "numero_controle_pncp": "SRC-001"},
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )
    result = reconciler.reconcile(run_c, "test_pncp")

    # Assert
    assert result.skipped is False
    assert result.reactivated > 0, f"Expected reactivation, got reactivated={result.reactivated}"
    assert _get_source_active(conn, id1) is True, "ID 1 should be reactivated"
    assert _get_source_inactive_reason(conn, id1) is None, "Inactive reason should be cleared"


# ===========================================================================
# Scenario 4: Execucao zero completa — todos os registros do escopo ficam inativos
# ===========================================================================


def test_scenario_4_complete_zero_run_inactivates_all(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """A completed_zero run should inactivate all previously active records."""
    # Arrange: create 3 active opportunities
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")
    id3 = _create_opportunity(conn, "SRC-003")

    # Completed_zero run (no records fetched but scope complete)
    run_zero = _create_run(conn, status="completed_zero", scope_complete=True)
    reconciler.record_memberships(run_zero, "test_pncp", [])

    # Act
    result = reconciler.reconcile(run_zero, "test_pncp")

    # Assert
    assert result.skipped is False
    assert result.inactivated == 3, f"Expected 3 inactivated, got {result.inactivated}"
    assert _get_source_active(conn, id1) is False
    assert _get_source_active(conn, id2) is False
    assert _get_source_active(conn, id3) is False


# ===========================================================================
# Scenario 5: Execucao zero parcial — nenhum registro e alterado
# ===========================================================================


def test_scenario_5_partial_zero_run_does_nothing(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """A partial zero-result run should NOT inactivate any records."""
    # Arrange: create active opportunities
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")

    # Partial run (scope_complete = FALSE)
    run_partial = _create_run(conn, status="partial", scope_complete=False)
    reconciler.record_memberships(run_partial, "test_pncp", [])

    # Act
    result = reconciler.reconcile(run_partial, "test_pncp")

    # Assert
    assert result.skipped is True, "Partial run should be skipped"
    assert result.inactivated == 0
    assert _get_source_active(conn, id1) is True
    assert _get_source_active(conn, id2) is True


# ===========================================================================
# Scenario 6: Concorrencia entre runs — apenas run finalizado reconcilia
# ===========================================================================


def test_scenario_6_only_completed_run_reconciles(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """Only a completed run should trigger reconciliation; concurrent incomplete runs should not."""
    # Arrange: create an active record
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")
    id3 = _create_opportunity(conn, "SRC-003")

    # Running run A (concurrent, not finished)
    run_running = _create_run(conn, status="running", scope_complete=False)
    reconciler.record_memberships(
        run_running,
        "test_pncp",
        [
            {"source_id": "SRC-001", "numero_controle_pncp": "SRC-001"},
        ],
    )

    # Running run B (concurrent, not finished)
    run_running2 = _create_run(conn, status="running", scope_complete=False)
    reconciler.record_memberships(
        run_running2,
        "test_pncp",
        [
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )

    # Act: try to reconcile both running runs
    result_a = reconciler.reconcile(run_running, "test_pncp")
    result_b = reconciler.reconcile(run_running2, "test_pncp")

    # Assert: neither should inactivate
    assert result_a.skipped is True, "Running run A should be skipped"
    assert result_b.skipped is True, "Running run B should be skipped"
    assert _get_source_active(conn, id1) is True, "ID 1 should remain active"
    assert _get_source_active(conn, id2) is True, "ID 2 should remain active"

    # Now complete a run C that only sees ID 1 and 2
    run_c = _create_run(conn, status="completed", scope_complete=True)
    reconciler.record_memberships(
        run_c,
        "test_pncp",
        [
            {"source_id": "SRC-001", "numero_controle_pncp": "SRC-001"},
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )
    result_c = reconciler.reconcile(run_c, "test_pncp")

    # Assert: only run C's reconciliation takes effect
    assert result_c.skipped is False
    assert result_c.inactivated == 1, "ID 3 should be inactivated"
    assert _get_source_active(conn, id1) is True
    assert _get_source_active(conn, id2) is True
    assert _get_source_active(conn, id3) is False


# ===========================================================================
# Scenario 7: Idempotencia do mesmo run
# ===========================================================================


def test_scenario_7_reconciliation_is_idempotent(
    conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None
) -> None:
    """Re-running the same reconciliation should produce the same result."""
    # Arrange: 3 opportunities, run sees only 2
    id1 = _create_opportunity(conn, "SRC-001")
    id2 = _create_opportunity(conn, "SRC-002")
    id3 = _create_opportunity(conn, "SRC-003")

    run_a = _create_run(conn, status="completed", scope_complete=True)
    reconciler.record_memberships(
        run_a,
        "test_pncp",
        [
            {"source_id": "SRC-001", "numero_controle_pncp": "SRC-001"},
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )

    # Act: First reconciliation
    result1 = reconciler.reconcile(run_a, "test_pncp")

    # Act: Second reconciliation (same run!)
    result2 = reconciler.reconcile(run_a, "test_pncp")

    # Assert: idempotent — first run inactivates, subsequent runs do nothing
    assert result1.inactivated == 1, "First run should inactivate 1 (ID 3)"
    assert result2.inactivated == 0, "Idempotent: second run should inactivate 0 (already done)"
    assert result1.reactivated == result2.reactivated
    assert _get_source_active(conn, id1) is True
    assert _get_source_active(conn, id2) is True
    assert _get_source_active(conn, id3) is False

    # Run third reconciliation — still idempotent
    result3 = reconciler.reconcile(run_a, "test_pncp")
    assert result3.inactivated == 0
    assert _get_source_active(conn, id1) is True
    assert _get_source_active(conn, id2) is True
    assert _get_source_active(conn, id3) is False


# ===========================================================================
# Additional: Limited run protection
# ===========================================================================


def test_scenario_limited_run_blocked(conn: Any, reconciler: SourceSnapshotReconciler, clean_test_data: None) -> None:
    """A run stopped by record/page limit should never inactivate."""
    id1 = _create_opportunity(conn, "SRC-001")

    # Run with stopped_by_record_limit
    run_limited = _create_run(
        conn,
        status="completed",
        scope_complete=True,
        metadata={"stopped_by_record_limit": True},
    )
    reconciler.record_memberships(
        run_limited,
        "test_pncp",
        [
            {"source_id": "SRC-002", "numero_controle_pncp": "SRC-002"},
        ],
    )

    # Act
    result = reconciler.reconcile(run_limited, "test_pncp")

    # Assert
    assert result.skipped is True, "Limited run should be skipped"
    assert result.inactivated == 0, "Limited run should not inactivate"
    assert _get_source_active(conn, id1) is True

    # Also test stopped_by_max_pages
    run_pagelimited = _create_run(
        conn,
        status="completed",
        scope_complete=True,
        metadata={"stopped_by_max_pages": True},
    )
    result2 = reconciler.reconcile(run_pagelimited, "test_pncp")
    assert result2.skipped is True, "Page-limited run should be skipped"
