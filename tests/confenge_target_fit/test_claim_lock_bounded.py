"""Regression: the dirty-queue claim must never take locks proportional to the backlog.

Incident: ``claim_batch`` evaluated ``pg_try_advisory_xact_lock`` as a row-level
WHERE qual under a blocking Sort, so every backlog row took a transaction-scoped
advisory lock before LIMIT saw a tuple. ~423k of them exhausted the
cluster-global shared lock table ("out of shared memory"), which also denied
locks to every other DataLake session and crash-looped the worker under systemd.
"""

from __future__ import annotations

import os
import uuid

import pytest

from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.store import (
    CLAIM_CANDIDATES_SQL,
    claim_batch,
    ensure_control_defaults,
)

DSN = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("CONFENGE_TARGET_FIT_STATE_DSN")

pytestmark = [
    pytest.mark.real_db,
    pytest.mark.skipif(not DSN, reason="LOCAL_DATALAKE_DSN not set"),
]

# Backlog large enough that the pre-fix plan would blow the default shared lock
# table (max_locks_per_transaction=64 * max_connections=100 = 6400 slots).
BACKLOG_ROWS = 8000
# cnpj_raiz is CHAR(8); this range is disjoint from every other test's roots.
RAIZ_START = 30000000


def _apply_migration() -> None:
    import subprocess
    import sys
    from pathlib import Path

    subprocess.check_call(
        [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", DSN],
        cwd=str(Path(__file__).resolve().parents[2]),
    )


@pytest.fixture(scope="module")
def dsn():
    _apply_migration()
    return DSN


@pytest.fixture
def seeded_backlog(dsn):
    """Seed BACKLOG_ROWS pending rows across distinct company_keys; drop them after."""
    tag = f"bounded-claim-{uuid.uuid4().hex[:8]}"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO confenge_target_fit_dirty (
                    company_key, cnpj_raiz, reason, source_entity, source_id,
                    source_updated_at, source_watermark, priority, status,
                    idempotency_key
                )
                SELECT 'cnpj_root:' || lpad(g::text, 8, '0'),
                       lpad(g::text, 8, '0'),
                       %s, 'test', g::text,
                       now(), 'wm-bounded', 100, 'pending',
                       %s || '-' || g
                FROM generate_series(%s, %s) AS g
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (tag, tag, RAIZ_START, RAIZ_START + BACKLOG_ROWS - 1),
            )
            assert cur.rowcount == BACKLOG_ROWS
        conn.commit()
        with conn.cursor() as cur:
            # Autovacuum keeps production stats representative; a freshly bulk
            # loaded test table has none, and on stale stats the planner falls
            # back to bitmap-scan + Sort inside the CTE. That costs latency but
            # NOT the lock budget — the CTE boundary, not the index, is what
            # bounds the advisory locks. ANALYZE so the plan assertions below
            # test the shipped production plan.
            cur.execute("ANALYZE confenge_target_fit_dirty")
        conn.commit()
        yield tag
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM confenge_target_fit_dirty WHERE reason = %s", (tag,))
            conn.commit()
        finally:
            conn.close()


def _advisory_locks_held(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n
            FROM pg_locks
            WHERE locktype = 'advisory' AND pid = pg_backend_pid()
            """
        )
        row = cur.fetchone()
        return int(row["n"] if isinstance(row, dict) else row[0])


def test_claim_advisory_locks_bounded_by_batch(dsn, seeded_backlog):  # noqa: ARG001
    """Advisory locks held mid-claim scale with the batch limit, not the backlog."""
    batch_size = 50
    # claim_batch over-fetches to allow the one-per-company post-filter.
    candidate_limit = max(batch_size * 4, batch_size)

    conn = connect(dsn, readonly=False)
    try:
        items = claim_batch(conn, worker_id="w-bounded", batch_size=batch_size, lock_ttl_seconds=60)
        # Still inside the claim transaction: xact-scoped advisory locks are only
        # released at COMMIT, so this is the peak the shared lock table must hold.
        held = _advisory_locks_held(conn)
        conn.commit()

        assert held <= candidate_limit, (
            f"claim took {held} advisory locks for a {BACKLOG_ROWS}-row backlog; "
            f"must stay within the candidate limit {candidate_limit}"
        )
        assert held < BACKLOG_ROWS
        assert len(items) == batch_size
    finally:
        conn.close()


def test_claim_plan_does_not_scan_whole_backlog(dsn, seeded_backlog):
    """The advisory lock is evaluated post-LIMIT, on the bounded candidate set."""
    batch_size = 50
    candidate_limit = max(batch_size * 4, batch_size)

    conn = connect(dsn, readonly=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN (ANALYZE, FORMAT JSON) " + CLAIM_CANDIDATES_SQL,
                (candidate_limit,),
            )
            row = cur.fetchone()
        plan = row["QUERY PLAN"] if isinstance(row, dict) else row[0]
        if isinstance(plan, str):
            import json as _json

            plan = _json.loads(plan)
        root = plan[0]["Plan"]

        def walk(node):
            yield node
            for child in node.get("Plans", []) or []:
                yield from walk(child)

        nodes = list(walk(root))

        def subtree(name: str) -> list[dict]:
            for node in nodes:
                if node.get("Subplan Name") == f"CTE {name}":
                    return list(walk(node))
            raise AssertionError(f"CTE {name} not found in plan")

        # --- Hard invariant: the advisory lock is evaluated post-LIMIT. ---
        # This holds regardless of which plan the CTE body gets, and it is what
        # keeps the shared lock table safe.
        lock_nodes = [n for n in nodes if "pg_try_advisory_xact_lock" in str(n.get("Filter", ""))]
        assert lock_nodes, "advisory lock qual not found in plan"
        for n in lock_nodes:
            assert n["Node Type"] == "CTE Scan", (
                f"advisory lock evaluated in {n['Node Type']}, must be post-LIMIT CTE Scan"
            )
            assert int(n["Actual Rows"]) <= candidate_limit, (
                f"advisory lock evaluated on {n['Actual Rows']} rows for a "
                f"{BACKLOG_ROWS}-row backlog; limit is {candidate_limit}"
            )

        candidate_nodes = subtree("candidates")
        assert int(candidate_nodes[0]["Actual Rows"]) <= candidate_limit

        # --- Plan quality: LIMIT terminates the ordered index walk. ---
        # Needs the representative stats the fixture ANALYZEs in.
        assert not any(n["Node Type"] == "Sort" for n in candidate_nodes), (
            "blocking Sort inside the candidate CTE — LIMIT cannot terminate early"
        )
        index_names = {n.get("Index Name") for n in candidate_nodes if n.get("Index Name")}
        assert "confenge_tf_dirty_claim2_idx" in index_names, (
            f"candidate walk did not use the 099 claim index: {index_names}"
        )
        scanned = max(int(n["Actual Rows"]) for n in candidate_nodes)
        assert scanned <= candidate_limit, f"candidate CTE emitted {scanned} rows; must stop at {candidate_limit}"
    finally:
        conn.rollback()
        conn.close()


def test_claim_advisory_locks_bounded_without_index_plan(dsn, seeded_backlog):  # noqa: ARG001
    """The lock bound comes from the CTE boundary, not from the index.

    With enable_indexscan/enable_bitmapscan off the planner is forced back into
    exactly the seq-scan + blocking-Sort shape that caused the incident. The
    pre-fix statement evaluated pg_try_advisory_xact_lock inside that scan filter
    and died with "out of shared memory"; the shipped statement must still take
    at most `candidate_limit` advisory locks.
    """
    batch_size = 50
    candidate_limit = max(batch_size * 4, batch_size)

    conn = connect(dsn, readonly=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET enable_indexscan = off")
            cur.execute("SET enable_bitmapscan = off")
            cur.execute("SET enable_indexonlyscan = off")
        conn.commit()

        items = claim_batch(conn, worker_id="w-noindex", batch_size=batch_size, lock_ttl_seconds=60)
        held = _advisory_locks_held(conn)
        conn.commit()

        assert held <= candidate_limit, (
            f"claim took {held} advisory locks under a seq-scan plan over a "
            f"{BACKLOG_ROWS}-row backlog; limit is {candidate_limit}"
        )
        assert len(items) == batch_size
    finally:
        conn.close()


def test_reclaim_drains_more_than_one_batch(dsn, seeded_backlog):
    """Bounding reclaim per statement must not stop it from draining the backlog.

    The reclaim UPDATE now runs in committed batches so its row locks never ride
    inside the claim transaction. Semantics are unchanged: every expired lock is
    still reclaimed, even when there are far more of them than one batch holds.
    """
    from scripts.confenge_target_fit.store import RECLAIM_BATCH_SIZE, reclaim_expired_locks

    expired = RECLAIM_BATCH_SIZE * 2 + 7
    assert expired < BACKLOG_ROWS

    conn = connect(dsn, readonly=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE confenge_target_fit_dirty
                SET status = 'processing',
                    locked_by = 'dead-worker',
                    locked_until = now() - interval '1 hour'
                WHERE id IN (
                    SELECT id FROM confenge_target_fit_dirty
                    WHERE reason = %s ORDER BY id LIMIT %s
                )
                """,
                (seeded_backlog, expired),
            )
            assert cur.rowcount == expired
        conn.commit()

        assert reclaim_expired_locks(conn) == expired

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n FROM confenge_target_fit_dirty
                WHERE reason = %s AND status = 'processing'
                """,
                (seeded_backlog,),
            )
            row = cur.fetchone()
        assert int(row["n"] if isinstance(row, dict) else row[0]) == 0
    finally:
        conn.close()
