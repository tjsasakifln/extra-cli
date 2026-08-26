"""DoD §12.1 — golden path reconciles editais snapshot (real delta, not connectivity)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import run_snapshot_reconciliation

pytestmark = pytest.mark.real_db


def _dsn_with_bid() -> str:
    from scripts.testing.real_db_guard import admit_ready_connection

    conn, dsn = admit_ready_connection(
        required_tables=("pncp_raw_bids",),
        context="golden_path_snapshot",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pncp_raw_bids (
                    pncp_id, objeto_compra, uf, source, content_hash,
                    is_active, synthetic_id
                ) VALUES (
                    'REALDB-SNAPSHOT-001', 'snapshot deterministic seed', 'SC',
                    'real_db_test', %s, TRUE, TRUE
                ) ON CONFLICT (pncp_id) DO UPDATE SET is_active = TRUE
                """,
                ("e" * 64,),
            )
        conn.commit()
    finally:
        conn.close()
    return dsn


def test_help_documents_execute_snapshot_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-snapshot-only" in (r.stdout + r.stderr)


def test_snapshot_baseline_then_stable(tmp_path: Path) -> None:
    dsn = _dsn_with_bid()

    snap_dir = tmp_path / "snapshots"
    r1 = run_snapshot_reconciliation(dsn, snapshot_dir=snap_dir)
    assert r1.status == "pass", (r1.error, r1.details)
    assert r1.details.get("baseline") is True
    assert int(r1.details.get("current_count") or 0) > 0
    assert r1.details.get("ids_sha256")

    r2 = run_snapshot_reconciliation(dsn, snapshot_dir=snap_dir)
    assert r2.status == "pass", (r2.error, r2.details)
    assert r2.details.get("baseline") is False
    assert r2.details.get("added") == 0
    assert r2.details.get("removed") == 0
    assert r2.details.get("changed") == 0
    assert r2.details.get("ids_sha256") == r1.details.get("ids_sha256")


def test_snapshot_detects_removed_id(tmp_path: Path) -> None:
    dsn = _dsn_with_bid()

    snap_dir = tmp_path / "snap2"
    r1 = run_snapshot_reconciliation(dsn, snapshot_dir=snap_dir)
    assert r1.status == "pass"
    # Corrupt prev by adding phantom id
    prev = snap_dir / "editais-snapshot-prev.json"
    doc = json.loads(prev.read_text(encoding="utf-8"))
    doc["records"]["__phantom_id__"] = {"content_hash": "x", "data_publicacao": ""}
    doc["count"] = len(doc["records"])
    prev.write_text(json.dumps(doc), encoding="utf-8")
    r2 = run_snapshot_reconciliation(dsn, snapshot_dir=snap_dir)
    assert r2.status == "pass"
    assert int(r2.details.get("removed") or 0) >= 1
