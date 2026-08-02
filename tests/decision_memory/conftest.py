"""Shared fixtures for Decision & Outcome Memory tests (real PostgreSQL)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
MIGRATION = ROOT / "db" / "migrations" / "068_decision_outcome_memory.sql"


def _pg_available() -> bool:
    try:
        import psycopg2

        conn = psycopg2.connect(DSN, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _ensure_migration() -> None:
    """Apply 068 if dm_decision_events is missing.

    Handles local DB that may have orphaned version 068 from unmerged predictive PR:
    if version 068 is recorded but dm tables missing, re-apply SQL content directly.
    """
    import psycopg2

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name='dm_decision_events'
                )
                """
            )
            exists = bool(cur.fetchone()[0])
            if exists:
                return
            # Apply migration file statements
            sql = MIGRATION.read_text(encoding="utf-8")
            cur.execute(sql)
            # Ensure ledger row
            cur.execute(
                """
                INSERT INTO public._migrations (version, name, checksum)
                VALUES ('068', %s, 'sha256=decision-memory-v1')
                ON CONFLICT (version) DO UPDATE
                SET name = EXCLUDED.name
                """,
                (MIGRATION.name,),
            )
    finally:
        conn.close()


@pytest.fixture(scope="session")
def dm_dsn() -> str:
    if not _pg_available():
        pytest.skip("PostgreSQL not available at LOCAL_DATALAKE_DSN")
    _ensure_migration()
    return DSN


@pytest.fixture
def dm_conn(dm_dsn: str):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dm_dsn, cursor_factory=RealDictCursor)
    yield conn
    try:
        conn.rollback()
    except Exception:
        pass
    conn.close()


@pytest.fixture
def client_id() -> str:
    """Unique client per test to avoid cross-test interference."""
    return f"test-client-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def repo(dm_conn, client_id: str):
    from scripts.decision_memory.repository import DecisionMemoryRepository

    return DecisionMemoryRepository(dm_conn)


@pytest.fixture
def two_cycle_fixture_dir(tmp_path: Path) -> Path:
    """Sanitized two-cycle fixture (no private Extra data)."""
    c1 = tmp_path / "cycle1"
    c2 = tmp_path / "cycle2"
    c1.mkdir()
    c2.mkdir()
    shortlist = {
        "schema": "test-actionable/1.0",
        "result": "SHORTLIST_READY",
        "shortlist_count": 1,
        "profile_stamp": {
            "profile_id": "fixture-client",
            "version": "1",
            "profile_hash": "a" * 64,
        },
        "shortlist": [
            {
                "opportunity_id": "00.000.000/0001-00-1-000001/2026",
                "numero_controle_pncp": "00.000.000/0001-00-1-000001/2026",
                "state": "REVIEW",
                "recommendation": "REVIEW",
                "orgao": "Orgao Fixture",
                "objeto": "servicos de engenharia fixture",
            }
        ],
    }
    import json

    (c1 / "actionable-summary.json").write_text(json.dumps(shortlist, indent=2) + "\n", encoding="utf-8")
    (c1 / "shortlist.json").write_text(json.dumps(shortlist, indent=2) + "\n", encoding="utf-8")
    # Cycle 1 human decision ledger
    line = {
        "schema": "extra-decision-review/1.0",
        "recorded_at": "2026-07-01T12:00:00Z",
        "actor": "fixture-actor",
        "opportunity_id": "00.000.000/0001-00-1-000001/2026",
        "decision": "ACCEPT",
        "reason": "Escopo alinhado ao perfil fixture",
        "next_action": "Montar proposta tecnica",
        "next_action_due": "2026-07-08T00:00:00Z",
        "profile_version": "1",
        "profile_hash": "a" * 64,
        "evidence_hash": "b" * 64,
        "run_dir": str(c1),
    }
    (c1 / "human-decisions.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    # Cycle 2 reappears
    (c2 / "actionable-summary.json").write_text(json.dumps(shortlist, indent=2) + "\n", encoding="utf-8")
    return tmp_path
