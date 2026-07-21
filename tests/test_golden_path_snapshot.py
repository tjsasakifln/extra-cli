"""DoD §12.1 — golden path reconciles editais snapshot (real delta, not connectivity)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import run_snapshot_reconciliation


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
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pncp_raw_bids")
            n = int(cur.fetchone()[0])
        conn.close()
        if n == 0:
            pytest.skip("pncp_raw_bids empty — run crawl first")
    except Exception:
        pytest.skip("no local test-db")

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
    dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pncp_raw_bids")
            n = int(cur.fetchone()[0])
        conn.close()
        if n == 0:
            pytest.skip("pncp_raw_bids empty — run crawl first")
    except Exception:
        pytest.skip("no local test-db")

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
