"""DoD §12.1 — golden path can re-run without duplicating stable keys."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.real_db


def test_dual_seed_and_bid_table_no_duplicate_keys() -> None:
    from scripts.testing.connection_policy import IDEMPOTENCY_TABLES
    from scripts.testing.real_db_guard import admit_ready_connection

    conn, dsn = admit_ready_connection(
        required_tables=IDEMPOTENCY_TABLES,
        context="golden_path_idempotency",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), count(distinct cnpj_8) FROM sc_public_entities")
            n, d = cur.fetchone()
            assert n == d, "sc_public_entities must not have duplicate cnpj_8 keys"
            assert n >= 1000
            cur.execute("SELECT count(*), count(distinct pncp_id) FROM pncp_raw_bids")
            bn, bd = cur.fetchone()
            assert bn == bd, "pncp_raw_bids must not have duplicate pncp_id"
            # Dual seed: re-run seed should not inflate entity count beyond uniqueness
            from scripts.golden_path import apply_seeds

            ok1, _, s1 = apply_seeds(dsn)
            ok2, _, s2 = apply_seeds(dsn)
            assert ok1 and ok2
            cur.execute("SELECT count(*), count(distinct cnpj_8) FROM sc_public_entities")
            n2, d2 = cur.fetchone()
            assert n2 == d2
            # count should not explode (allow tiny variance only if seed inserts 0)
            assert n2 <= n + 5
    finally:
        conn.close()


def test_dual_snapshot_stable_ids_sha() -> None:
    import tempfile
    from pathlib import Path

    from scripts.golden_path import run_snapshot_reconciliation
    from scripts.testing.connection_policy import IDEMPOTENCY_TABLES
    from scripts.testing.real_db_guard import admit_ready_connection

    conn, dsn = admit_ready_connection(
        required_tables=IDEMPOTENCY_TABLES,
        context="golden_path_idempotency_snapshot",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pncp_raw_bids")
            if int(cur.fetchone()[0]) == 0:
                pytest.skip("no bids")
    finally:
        conn.close()

    with tempfile.TemporaryDirectory() as td:
        snap = Path(td)
        r1 = run_snapshot_reconciliation(dsn, snapshot_dir=snap)
        r2 = run_snapshot_reconciliation(dsn, snapshot_dir=snap)
        assert r1.status == "pass" and r2.status == "pass"
        assert r2.details.get("added") == 0
        assert r2.details.get("removed") == 0
        assert r1.details.get("ids_sha256") == r2.details.get("ids_sha256")
