"""AC3 — SQL-vs-Python parity for the contracting-act date precedence.

Story: contract-lifecycle-truth-v1.

``public.contract_contracting_date_v1`` / ``public.contract_contracting_date_field_v1``
(migration 103) and ``commercial_authority_v2.contracting_date()`` must return
the identical ``(date, field_name)`` pair for every precedence permutation and
for the all-NULL case. That parity is what makes the future consolidation of
``rebuild_commercial_qualification.py``'s inline ``CASE`` (story 3) safe.

All rows here are literal date arguments passed to the SQL functions; no
fixture rows are inserted, so this module never touches table state.

Requires a real PostgreSQL connection: every test carries ``real_db`` via the
module-level ``pytestmark``. Under the default mocked-connection gate these
tests skip loudly instead of passing against a MagicMock.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.confenge_activation.commercial_authority_v2 import contracting_date
from scripts.testing.real_db_guard import admit_ready_connection

pytestmark = pytest.mark.real_db

REQUIRED_TABLES = ("pncp_supplier_contracts",)
REQUIRED_VIEWS = ("v_contract_lifecycle_truth_v1",)

# (case id, data_assinatura, data_inicio, data_publicacao, data_publicacao_fonte)
PRECEDENCE_CASES = [
    (
        "assinatura_wins_over_all",
        date(2024, 1, 5),
        date(2024, 2, 1),
        date(2024, 3, 1),
        date(2024, 4, 1),
    ),
    (
        "assinatura_wins_over_inicio",  # AC3's explicit two-field fixture
        date(2023, 7, 11),
        date(2023, 8, 22),
        None,
        None,
    ),
    (
        "inicio_wins_when_assinatura_null",
        None,
        date(2024, 2, 1),
        date(2024, 3, 1),
        date(2024, 4, 1),
    ),
    (
        "publicacao_wins_when_first_two_null",
        None,
        None,
        date(2024, 3, 1),
        date(2024, 4, 1),
    ),
    (
        "publicacao_fonte_wins_when_rest_null",
        None,
        None,
        None,
        date(2024, 4, 1),
    ),
    (
        "all_null",
        None,
        None,
        None,
        None,
    ),
]


@pytest.fixture(scope="module")
def pg_conn():
    """Real PostgreSQL connection admitted by the named preflight."""
    conn, _dsn = admit_ready_connection(
        required_tables=REQUIRED_TABLES,
        required_views=REQUIRED_VIEWS,
        context="contract_lifecycle_truth_precedence",
    )
    try:
        yield conn
    finally:
        conn.close()


def _sql_pair(conn, assinatura, inicio, publicacao, fonte):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT public.contract_contracting_date_v1(%s, %s, %s, %s), "
            "public.contract_contracting_date_field_v1(%s, %s, %s, %s)",
            (assinatura, inicio, publicacao, fonte, assinatura, inicio, publicacao, fonte),
        )
        row = cur.fetchone()
    conn.rollback()
    return row[0], row[1]


@pytest.mark.parametrize(
    ("case_id", "assinatura", "inicio", "publicacao", "fonte"),
    PRECEDENCE_CASES,
    ids=[case[0] for case in PRECEDENCE_CASES],
)
def test_sql_matches_python_precedence(pg_conn, case_id, assinatura, inicio, publicacao, fonte):
    """The SQL pair equals the Python pair for every precedence permutation."""
    python_date, python_field = contracting_date(
        {
            "data_assinatura": assinatura,
            "data_inicio": inicio,
            "data_publicacao": publicacao,
            "data_publicacao_fonte": fonte,
        }
    )
    sql_date, sql_field = _sql_pair(pg_conn, assinatura, inicio, publicacao, fonte)

    assert sql_date == python_date, f"{case_id}: date diverged"
    assert sql_field == python_field, f"{case_id}: field name diverged"


def test_assinatura_and_inicio_both_populated_resolves_to_assinatura(pg_conn):
    """AC3 literal fixture: both populated, assinatura wins, field is named."""
    sql_date, sql_field = _sql_pair(pg_conn, date(2023, 7, 11), date(2023, 8, 22), None, None)

    assert sql_date == date(2023, 7, 11)
    assert sql_field == "data_assinatura"


def test_all_null_field_is_empty_string_never_sql_null(pg_conn):
    """The field function mirrors ``return None, ""`` byte for byte.

    Asserted with ``= ''`` on the SQL side as well, never ``IS NULL``: psycopg2
    maps SQL NULL to Python None and ``None != ''``, so a NULL return would
    silently break the parity guarantee this module exists to protect.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT public.contract_contracting_date_field_v1(NULL, NULL, NULL, NULL) = '', "
            "public.contract_contracting_date_field_v1(NULL, NULL, NULL, NULL) IS NULL, "
            "public.contract_contracting_date_v1(NULL, NULL, NULL, NULL) IS NULL"
        )
        is_empty, is_null, date_is_null = cur.fetchone()
    pg_conn.rollback()

    assert is_empty is True
    assert is_null is False
    assert date_is_null is True

    python_date, python_field = contracting_date({})
    assert python_date is None
    assert python_field == ""
