"""Minimal signed/published engineering-data candidate contract."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts.engineering_class import (
    attach_engineering_class,
    stamp_engineering_class_labels,
)
from scripts.crawl.pncp_contract_terms import map_pncp_term
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/engineering_data_release"
CONTRACT_PATH = ROOT / "docs/contracts/commercial-read/v1/commercial_read_v1.json"
SQL_115 = ROOT / "db/migrations/115_commercial_read_v1.sql"
SQL_116 = ROOT / "db/migrations/116_engineering_data_release_candidate_v2.sql"
PREFIX = "EDRC2-"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_candidate_is_signed_published_only_and_has_one_class_authority() -> None:
    sql = SQL_116.read_text(encoding="utf-8")
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert "contract_engineering_class" in sql
    assert "ILIKE" not in sql
    assert "objeto_contrato ~" not in sql
    assert "pncp_procurement_results" not in sql
    assert "RESULT_PUBLISHED" not in sql
    assert "ADJUDICATED" not in sql
    assert "HOMOLOGATED" not in sql
    assert set(contract["live_proven_event_types"]) == {
        "CONTRACT_SIGNED",
        "CONTRACT_PUBLISHED",
    }
    assert "THEN 'CONTRACT_SIGNED'" in sql
    assert "ELSE 'CONTRACT_PUBLISHED'" in sql
    for column in contract["columns"] + contract["candidate_additive_columns"]:
        assert column in sql


def test_migrations_are_unique_and_pre_signature_results_are_absent() -> None:
    files = sorted((ROOT / "db/migrations").glob("1*.sql"))
    versions = [
        path.name.split("_", 1)[0]
        for path in files
        if path.name[:3].isdigit() and int(path.name[:3]) >= 107
    ]
    assert versions == [f"{number:03d}" for number in range(107, 117)]
    assert not list((ROOT / "db/migrations").glob("*procurement_result*.sql"))
    assert not (ROOT / "scripts/crawl/pncp_procurement_results.py").exists()
    assert not (ROOT / "scripts/ops/ingest_pncp_procurement_results.py").exists()


def test_role_is_select_only_contact_is_cadastral_and_terminal_is_blocked() -> None:
    sql_115 = SQL_115.read_text(encoding="utf-8")
    sql_116 = SQL_116.read_text(encoding="utf-8")
    supplier_sql = (
        ROOT / "db/migrations/112_engineering_supplier_registry.sql"
    ).read_text(encoding="utf-8")

    assert "NOLOGIN" in sql_115
    assert "GRANT SELECT" in sql_115
    assert "GRANT SELECT" in sql_116
    for sql in (sql_115, sql_116):
        lowered = sql.lower()
        assert "password" not in lowered
        assert "grant insert" not in lowered
        assert "grant update" not in lowered
        assert "grant delete" not in lowered
    assert "Not decision-maker discovery" in supplier_sql
    assert "cadastral_email" in supplier_sql
    assert "NOT_ACTIONABLE" in sql_116
    assert "REVOGACAO" in sql_116


def _dsn() -> str:
    return os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()


def _connect():
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)


def _cleanup(cur) -> None:
    cur.execute("DELETE FROM public.contract_terms WHERE contrato_id LIKE %s", (PREFIX + "%",))
    cur.execute(
        "DELETE FROM public.contract_engineering_class WHERE contrato_id LIKE %s",
        (PREFIX + "%",),
    )
    cur.execute(
        "DELETE FROM public.pncp_supplier_contracts WHERE contrato_id LIKE %s",
        (PREFIX + "%",),
    )


def _upsert_and_stamp(conn, cur, record: dict) -> None:
    candidate = dict(record)
    attach_engineering_class(candidate)
    for _ in range(2):
        cur.execute(
            "SELECT * FROM public.upsert_pncp_supplier_contracts(%s::jsonb)",
            (json.dumps([candidate], default=str),),
        )
        cur.fetchall()
    assert stamp_engineering_class_labels(conn, [candidate]) == 1
    assert stamp_engineering_class_labels(conn, [candidate]) == 1


@pytest.mark.real_db
@pytest.mark.database
def test_signed_published_terminal_replay_and_query_contract() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    signed = _load("signed.json")
    published = _load("published.json")
    terminal_fixture = _load("terminal.json")
    terminal = terminal_fixture["contract"]
    term = map_pncp_term(terminal_fixture["term"])

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _cleanup(cur)
            for record in (signed, published, terminal):
                _upsert_and_stamp(conn, cur, record)

            for _ in range(2):
                cur.execute(
                    "SELECT action FROM public.apply_contract_terms(%s::jsonb)",
                    (json.dumps([term], default=str),),
                )
                cur.fetchall()

            cur.execute(
                """
                SELECT * FROM public.v_recent_engineering_wins
                WHERE contract_id LIKE %s
                ORDER BY contract_id
                """,
                (PREFIX + "%",),
            )
            rows = {row["contract_id"]: row for row in cur.fetchall()}

            assert set(rows) == {signed["contrato_id"], published["contrato_id"], terminal["contrato_id"]}
            assert rows[signed["contrato_id"]]["event_type"] == "CONTRACT_SIGNED"
            assert rows[published["contrato_id"]]["event_type"] == "CONTRACT_PUBLISHED"
            assert rows[terminal["contrato_id"]]["lifecycle_status"] == "REVOGACAO"
            assert rows[terminal["contrato_id"]]["commercial_actionability"] == "NOT_ACTIONABLE"
            assert {row["event_type"] for row in rows.values()} <= set(
                contract["live_proven_event_types"]
            )

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'v_recent_engineering_wins'
                ORDER BY ordinal_position
                """
            )
            columns = [row["column_name"] for row in cur.fetchall()]
            assert columns[: len(contract["columns"])] == contract["columns"]
            assert columns[len(contract["columns"]) :] == contract["candidate_additive_columns"]

            # Daily consumer query shape. The local disposable-DB gate verifies
            # plan execution under the issue's 10 s ceiling; production scale
            # remains explicitly pending until #468 permits a change window.
            cur.execute(
                """
                EXPLAIN (ANALYZE, FORMAT JSON)
                SELECT company_cnpj, contract_id, event_type, event_at,
                       engineering_class, lifecycle_status, commercial_actionability
                FROM public.v_recent_engineering_wins
                WHERE event_at >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY event_at DESC
                LIMIT 500
                """
            )
            plan = cur.fetchone()["QUERY PLAN"][0]
            assert float(plan["Execution Time"]) < 10_000.0

            cur.execute(
                """
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = 'confenge_commercial_read_v1'
                  AND table_name = 'v_recent_engineering_wins'
                """
            )
            assert {row["privilege_type"] for row in cur.fetchall()} == {"SELECT"}
        conn.commit()
    finally:
        try:
            with conn.cursor() as cur:
                _cleanup(cur)
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
