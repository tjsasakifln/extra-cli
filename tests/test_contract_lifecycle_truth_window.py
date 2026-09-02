"""AC15 — SQL-vs-Python parity for the rolling qualification-window floor.

Story: contract-lifecycle-truth-v1.

``public.contract_window_floor_v1(anchor DATE)`` (migration 103) must reproduce
``commercial_authority_v2.add_years_go(anchor, -QUALIFICATION_WINDOW_YEARS)``
exactly, including Go's day-overflow-forward normalization. Parity is asserted
against ``add_years_go``, the shared parameterized primitive that
``window_floor(now)`` delegates to: ``window_floor`` takes a ``datetime``, not a
``date``, so it cannot be called with an arbitrary anchor. Case (c) below pins
the ``window_floor`` specialization itself.

Both sides receive the identical explicit anchor. The floor expression is never
copied into this module: the view and this test call the same function, so a
divergence cannot hide behind two independently-green implementations.

All fixture rows are synthetic INSERTs rolled back in teardown; the local
DataLake is empty of production data.

Requires a real PostgreSQL connection: every test carries ``real_db`` via the
module-level ``pytestmark``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from scripts.confenge_activation.commercial_authority_v2 import (
    QUALIFICATION_WINDOW_YEARS,
    add_years_go,
    window_floor,
)
from scripts.testing.real_db_guard import admit_ready_connection

pytestmark = pytest.mark.real_db

REQUIRED_TABLES = ("pncp_supplier_contracts",)
REQUIRED_VIEWS = ("v_contract_lifecycle_truth_v1",)

# (case id, anchor, pinned expected floor)
ANCHOR_CASES = [
    ("leap_day_overflows_forward", date(2024, 2, 29), date(2021, 3, 1)),
    ("arbitrary_non_leap_anchor", date(2026, 9, 1), date(2023, 9, 1)),
]


@pytest.fixture(scope="module")
def pg_conn():
    """Real PostgreSQL connection admitted by the named preflight."""
    conn, _dsn = admit_ready_connection(
        required_tables=REQUIRED_TABLES,
        required_views=REQUIRED_VIEWS,
        context="contract_lifecycle_truth_window",
    )
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def rollback_conn(pg_conn):
    """Every fixture INSERT is unwound, including trigger side effects."""
    try:
        yield pg_conn
    finally:
        pg_conn.rollback()


@pytest.mark.parametrize(
    ("case_id", "anchor", "expected_floor"),
    ANCHOR_CASES,
    ids=[case[0] for case in ANCHOR_CASES],
)
def test_sql_window_floor_matches_add_years_go(pg_conn, case_id, anchor, expected_floor):
    """Cases (a) and (b): explicit anchor, pinned value, no clock read."""
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.contract_window_floor_v1(%s)", (anchor,))
        sql_floor = cur.fetchone()[0]
    pg_conn.rollback()

    python_floor = add_years_go(anchor, -QUALIFICATION_WINDOW_YEARS)

    assert python_floor == expected_floor, f"{case_id}: pinned Python value drifted"
    assert sql_floor == expected_floor, f"{case_id}: pinned SQL value drifted"
    assert sql_floor == python_floor, f"{case_id}: SQL and Python floors diverged"


def test_sql_current_date_floor_matches_window_floor_specialization(pg_conn):
    """Case (c): pins ``window_floor(now)`` itself.

    The session timezone is pinned to UTC before evaluating ``CURRENT_DATE``:
    ``window_floor`` computes ``now.astimezone(UTC).date()`` explicitly, while
    ``CURRENT_DATE`` resolves in whatever session ``TimeZone`` is active. Without
    pinning, the two sides can legitimately disagree for a multi-hour window
    around local midnight on any non-UTC session.
    """
    with pg_conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute("SELECT public.contract_window_floor_v1(CURRENT_DATE), CURRENT_DATE")
        sql_floor, sql_today = cur.fetchone()
    pg_conn.rollback()

    now = datetime.now(UTC)
    python_floor = window_floor(now)

    assert sql_today == now.date(), "session clock drifted mid-test; rerun"
    assert sql_floor == python_floor


def test_future_contracting_date_is_outside_the_window(rollback_conn):
    """A tomorrow-dated contracting act is never inside the window.

    Mirrors ``qualify_root``'s ``resolved > today`` exclusion: the upper bound
    of the window is CURRENT_DATE, not open-ended.
    """
    with rollback_conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_assinatura, status_normalized,
                 quality_state, is_active)
            VALUES (%s, CURRENT_DATE + 1, CURRENT_DATE + 1, 'ACTIVE_PROVEN', 'VALID', FALSE)
            """,
            ("lct-v1-window-tomorrow",),
        )
        cur.execute(
            """
            SELECT contracting_date, contracting_date_field,
                   contracting_date_in_qualification_window, CURRENT_DATE
            FROM public.v_contract_lifecycle_truth_v1
            WHERE contrato_id = %s
            """,
            ("lct-v1-window-tomorrow",),
        )
        contracting, field, in_window, today = cur.fetchone()

    assert field == "data_assinatura"
    assert contracting == today + timedelta(days=1)
    assert in_window is False


def test_contracting_date_on_the_floor_is_inside_the_window(rollback_conn):
    """The floor date itself is inside the window (BETWEEN is inclusive)."""
    with rollback_conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_assinatura, status_normalized,
                 quality_state, is_active)
            VALUES (%s,
                    public.contract_window_floor_v1(CURRENT_DATE),
                    public.contract_window_floor_v1(CURRENT_DATE),
                    'COMPLETED', 'VALID', FALSE)
            """,
            ("lct-v1-window-floor-edge",),
        )
        cur.execute(
            """
            SELECT contracting_date_in_qualification_window
            FROM public.v_contract_lifecycle_truth_v1
            WHERE contrato_id = %s
            """,
            ("lct-v1-window-floor-edge",),
        )
        (in_window,) = cur.fetchone()

    assert in_window is True
