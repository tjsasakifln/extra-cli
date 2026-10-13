"""AC4-AC14 and AC18 (secondary) — the lifecycle projection itself.

Story: contract-lifecycle-truth-v1.

Every row queried here is a synthetic INSERT: ``LOCAL_DATALAKE_DSN`` is empty of
production data, so no assertion in this module depends on real contracts. Each
test runs inside a transaction that is rolled back in teardown, which also
unwinds the ``trg_contract_role_link`` trigger writes into
``contract_role_links``.

Scenario A1 (terminal ``status_normalized``) is fixture-only by construction:
production currently has zero contracts in CANCELLED/TERMINATED/SUSPENDED
because no official-situation field is wired into the stamper yet.

Requires a real PostgreSQL connection: every test carries ``real_db`` via the
module-level ``pytestmark``. Under the default mocked-connection gate these
tests skip loudly instead of passing against a MagicMock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from scripts.confenge_activation.commercial_authority_v2 import window_floor
from scripts.confenge_activation.rebuild_commercial_qualification import (
    QUALIFICATION_SQL,
    TARGET_CONFIRMED,
)
from scripts.contracts_truth import (
    classify_contract_activity,
    classify_contract_quality,
)
from scripts.testing.real_db_guard import admit_ready_connection

pytestmark = pytest.mark.real_db

REQUIRED_TABLES = ("pncp_supplier_contracts",)
REQUIRED_VIEWS = ("v_contract_lifecycle_truth_v1", "v_contracts_canonical_v2")

LIFECYCLE_COLUMNS = (
    "lifecycle_state",
    "lifecycle_trust",
    "lifecycle_is_current_evidence",
    "lifecycle_reason_codes",
)

# The full 7 x 4 = 28 cell truth table from the story's "Lifecycle Derivation
# Rule", pinned literally rather than recomputed by the test. is_active is FALSE
# for all 28 rows, so LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED is never triggered here
# (that code is exercised by test_legacy_is_active_is_recorded_and_discarded).
#
# (status_normalized, quality_state, state, trust, is_current_evidence, reason_codes)
TRUTH_TABLE_CASES: list[tuple[str | None, str | None, str, str, bool, list[str]]] = [
    ("ACTIVE_PROVEN", "VALID", "ACTIVE_PROVEN", "TRUSTED", True, ["LIFECYCLE_TRUSTED"]),
    ("ACTIVE_PROVEN", "REVIEW", "ACTIVE_PROVEN", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("ACTIVE_PROVEN", "QUARANTINED", "ACTIVE_PROVEN", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("ACTIVE_PROVEN", None, "ACTIVE_PROVEN", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    ("COMPLETED", "VALID", "COMPLETED", "TRUSTED", False, ["LIFECYCLE_TRUSTED"]),
    ("COMPLETED", "REVIEW", "COMPLETED", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("COMPLETED", "QUARANTINED", "COMPLETED", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("COMPLETED", None, "COMPLETED", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    ("CANCELLED", "VALID", "CANCELLED", "TRUSTED", False, ["LIFECYCLE_TRUSTED"]),
    ("CANCELLED", "REVIEW", "CANCELLED", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("CANCELLED", "QUARANTINED", "CANCELLED", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("CANCELLED", None, "CANCELLED", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    ("TERMINATED", "VALID", "TERMINATED", "TRUSTED", False, ["LIFECYCLE_TRUSTED"]),
    ("TERMINATED", "REVIEW", "TERMINATED", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("TERMINATED", "QUARANTINED", "TERMINATED", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("TERMINATED", None, "TERMINATED", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    ("SUSPENDED", "VALID", "SUSPENDED", "TRUSTED", False, ["LIFECYCLE_TRUSTED"]),
    ("SUSPENDED", "REVIEW", "SUSPENDED", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("SUSPENDED", "QUARANTINED", "SUSPENDED", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("SUSPENDED", None, "SUSPENDED", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    ("UNKNOWN", "VALID", "UNKNOWN", "TRUSTED", False, ["LIFECYCLE_TRUSTED"]),
    ("UNKNOWN", "REVIEW", "UNKNOWN", "REVIEW", False, ["LIFECYCLE_REVIEW"]),
    ("UNKNOWN", "QUARANTINED", "UNKNOWN", "UNTRUSTED", False, ["LIFECYCLE_UNTRUSTED"]),
    ("UNKNOWN", None, "UNKNOWN", "UNSTAMPED", False, ["LIFECYCLE_QUALITY_UNSTAMPED"]),
    (None, "VALID", "UNKNOWN", "TRUSTED", False, ["LIFECYCLE_TRUSTED", "LIFECYCLE_UNSTAMPED"]),
    (None, "REVIEW", "UNKNOWN", "REVIEW", False, ["LIFECYCLE_REVIEW", "LIFECYCLE_UNSTAMPED"]),
    (
        None,
        "QUARANTINED",
        "UNKNOWN",
        "UNTRUSTED",
        False,
        ["LIFECYCLE_UNTRUSTED", "LIFECYCLE_UNSTAMPED"],
    ),
    (
        None,
        None,
        "UNKNOWN",
        "UNSTAMPED",
        False,
        ["LIFECYCLE_QUALITY_UNSTAMPED", "LIFECYCLE_UNSTAMPED"],
    ),
]

TRUTH_TABLE_IDS = [f"{status or 'NULL'}-{quality or 'NULL'}" for status, quality, *_ in TRUTH_TABLE_CASES]


@pytest.fixture(scope="module")
def pg_conn():
    """Real PostgreSQL connection admitted by the named preflight."""
    conn, _dsn = admit_ready_connection(
        required_tables=REQUIRED_TABLES,
        required_views=REQUIRED_VIEWS,
        context="contract_lifecycle_truth",
    )
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def conn(pg_conn):
    """Transaction-scoped connection: every fixture INSERT is rolled back."""
    try:
        yield pg_conn
    finally:
        pg_conn.rollback()


def _insert_contract(cur, contrato_id: str, **columns) -> None:
    """Insert one synthetic contract row. Unspecified columns keep defaults."""
    columns.setdefault("data_inicio", date(2024, 5, 1))
    columns.setdefault("is_active", False)
    names = ["contrato_id", *columns]
    placeholders = ", ".join(["%s"] * len(names))
    cur.execute(
        f"INSERT INTO public.pncp_supplier_contracts ({', '.join(names)}) VALUES ({placeholders})",
        (contrato_id, *columns.values()),
    )


def _lifecycle(cur, contrato_id: str) -> tuple:
    cur.execute(
        f"SELECT {', '.join(LIFECYCLE_COLUMNS)} FROM public.v_contract_lifecycle_truth_v1 WHERE contrato_id = %s",
        (contrato_id,),
    )
    rows = cur.fetchall()
    assert len(rows) == 1, f"expected exactly one view row for {contrato_id}, got {len(rows)}"
    return rows[0]


# --------------------------------------------------------------------------
# AC2 — the three sanctioned routines exist, IMMUTABLE and PARALLEL SAFE
# --------------------------------------------------------------------------
SANCTIONED_ROUTINES = {
    "contract_contracting_date_v1": "date",
    "contract_contracting_date_field_v1": "text",
    "contract_window_floor_v1": "date",
}


@pytest.mark.parametrize("routine_name", sorted(SANCTIONED_ROUTINES))
def test_sanctioned_routine_is_immutable_and_parallel_safe(conn, routine_name):
    """IMMUTABLE via information_schema; PARALLEL SAFE via pg_catalog.

    information_schema.routines exposes no parallel-safety column, so the two
    halves of this AC come from two different catalogs by necessity.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT data_type, is_deterministic FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = %s",
            (routine_name,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1, f"{routine_name} not found exactly once"
        data_type, is_deterministic = rows[0]

        cur.execute(
            "SELECT proparallel FROM pg_catalog.pg_proc WHERE pronamespace = 'public'::regnamespace AND proname = %s",
            (routine_name,),
        )
        (proparallel,) = cur.fetchone()

    assert data_type == SANCTIONED_ROUTINES[routine_name]
    assert is_deterministic == "YES", "routine is not IMMUTABLE"
    assert proparallel == "s", "routine is not PARALLEL SAFE"


def test_contracting_date_functions_take_the_four_precedence_dates(conn):
    """Signature order is the precedence order, and data_fim is never present."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT proname, pg_get_function_arguments(oid) FROM pg_catalog.pg_proc "
            "WHERE pronamespace = 'public'::regnamespace AND proname IN "
            "('contract_contracting_date_v1', 'contract_contracting_date_field_v1') "
            "ORDER BY proname"
        )
        signatures = dict(cur.fetchall())

    expected = "data_assinatura date, data_inicio date, data_publicacao date, data_publicacao_fonte date"
    assert signatures["contract_contracting_date_v1"] == expected
    assert signatures["contract_contracting_date_field_v1"] == expected
    assert "data_fim" not in expected


# --------------------------------------------------------------------------
# AC8 / scenario A10 — the exhaustive 28-cell derivation table
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status_normalized", "quality_state", "state", "trust", "is_current_evidence", "reason_codes"),
    TRUTH_TABLE_CASES,
    ids=TRUTH_TABLE_IDS,
)
def test_full_derivation_truth_table(
    conn,
    status_normalized,
    quality_state,
    state,
    trust,
    is_current_evidence,
    reason_codes,
):
    """Every one of the 28 cells, quadruple asserted, zero rows skipped."""
    contrato_id = f"lct-v1-grid-{status_normalized or 'NULL'}-{quality_state or 'NULL'}"
    with conn.cursor() as cur:
        _insert_contract(
            cur,
            contrato_id,
            status_normalized=status_normalized,
            quality_state=quality_state,
            is_active=False,
        )
        observed = _lifecycle(cur, contrato_id)

    assert observed == (state, trust, is_current_evidence, reason_codes)


def test_truth_table_has_exactly_twenty_eight_cases():
    """7 status values (6 stamped + NULL) x 4 quality values (3 stamped + NULL)."""
    assert len(TRUTH_TABLE_CASES) == 28
    assert len({(case[0], case[1]) for case in TRUTH_TABLE_CASES}) == 28


def test_exactly_one_cell_is_current_evidence():
    """The AND-gate is TRUE in exactly one of the 28 cells, by design."""
    positives = [case for case in TRUTH_TABLE_CASES if case[4]]
    assert [(case[0], case[1]) for case in positives] == [("ACTIVE_PROVEN", "VALID")]


# --------------------------------------------------------------------------
# AC6 / scenario A8 — the positive case
# --------------------------------------------------------------------------
def test_active_proven_and_valid_is_current_evidence(conn):
    """The only TRUE cell. A fixed-FALSE implementation fails here."""
    contrato_id = "lct-v1-a8-positive"
    with conn.cursor() as cur:
        # data_fim in the past and is_active TRUE must have zero influence.
        _insert_contract(
            cur,
            contrato_id,
            data_fim=date(2024, 6, 1),
            status_normalized="ACTIVE_PROVEN",
            quality_state="VALID",
            is_active=True,
        )
        state, trust, evidence, codes = _lifecycle(cur, contrato_id)

    assert state == "ACTIVE_PROVEN"
    assert trust == "TRUSTED"
    assert evidence is True
    assert "LIFECYCLE_TRUSTED" in codes
    for forbidden in (
        "LIFECYCLE_UNSTAMPED",
        "LIFECYCLE_UNTRUSTED",
        "LIFECYCLE_REVIEW",
        "LIFECYCLE_QUALITY_UNSTAMPED",
    ):
        assert forbidden not in codes


# --------------------------------------------------------------------------
# AC7 / scenario A9 — the REVIEW branch
# --------------------------------------------------------------------------
def test_active_proven_with_review_quality_is_not_current_evidence(conn):
    """Activity status and data-quality flag are orthogonal dimensions."""
    contrato_id = "lct-v1-a9-review"
    with conn.cursor() as cur:
        _insert_contract(
            cur,
            contrato_id,
            status_normalized="ACTIVE_PROVEN",
            quality_state="REVIEW",
        )
        state, trust, evidence, codes = _lifecycle(cur, contrato_id)

    assert state == "ACTIVE_PROVEN"
    assert trust == "REVIEW"
    assert evidence is False
    assert "LIFECYCLE_REVIEW" in codes


# --------------------------------------------------------------------------
# AC9 / scenario A1 — terminal status wins over a future data_fim
# --------------------------------------------------------------------------
def test_terminated_beats_future_data_fim_and_is_active(conn):
    """Fixture-only: production has zero terminal-status contracts today."""
    contrato_id = "lct-v1-a1-terminated"
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_fim, status_normalized, quality_state, is_active)
            VALUES (%s, DATE '2024-05-01', CURRENT_DATE + 365, 'TERMINATED', 'VALID', TRUE)
            """,
            (contrato_id,),
        )
        state, _trust, evidence, _codes = _lifecycle(cur, contrato_id)

    assert state == "TERMINATED"
    assert evidence is False


# --------------------------------------------------------------------------
# AC10 / scenario A2 — the legacy flag is recorded and discarded
# --------------------------------------------------------------------------
def test_legacy_is_active_is_recorded_and_discarded(conn):
    """is_active is read for the audit code only, and is never projected."""
    contrato_id = "lct-v1-a2-legacy"
    with conn.cursor() as cur:
        _insert_contract(
            cur,
            contrato_id,
            data_fim=date(2020, 1, 1),
            status_normalized=None,
            quality_state="VALID",
            is_active=True,
        )
        state, _trust, evidence, codes = _lifecycle(cur, contrato_id)

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'v_contract_lifecycle_truth_v1'"
        )
        view_columns = {row[0] for row in cur.fetchall()}

    assert state == "UNKNOWN"
    assert evidence is False
    assert "LIFECYCLE_UNSTAMPED" in codes
    assert "LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED" in codes
    assert "is_active" not in view_columns


# --------------------------------------------------------------------------
# AC11 / scenario A3 — absence of a stamp is never evidence
# --------------------------------------------------------------------------
def test_unstamped_status_projects_unknown(conn):
    contrato_id = "lct-v1-a3-unstamped"
    with conn.cursor() as cur:
        _insert_contract(cur, contrato_id, status_normalized=None, quality_state="VALID")
        state, _trust, evidence, codes = _lifecycle(cur, contrato_id)

    assert state == "UNKNOWN"
    assert evidence is False
    assert "LIFECYCLE_UNSTAMPED" in codes


# --------------------------------------------------------------------------
# AC12 / scenario A4 — QUARANTINED never expels from the qualification window
# --------------------------------------------------------------------------
def test_quarantined_stays_inside_the_qualification_window(conn):
    contrato_id = "lct-v1-a4-quarantined"
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_assinatura, status_normalized,
                 quality_state, is_active)
            VALUES (%s, CURRENT_DATE - 200, CURRENT_DATE - 200, 'ACTIVE_PROVEN',
                    'QUARANTINED', FALSE)
            """,
            (contrato_id,),
        )
        cur.execute(
            "SELECT lifecycle_trust, lifecycle_is_current_evidence, "
            "contracting_date_in_qualification_window "
            "FROM public.v_contract_lifecycle_truth_v1 WHERE contrato_id = %s",
            (contrato_id,),
        )
        trust, evidence, in_window = cur.fetchone()

    assert trust == "UNTRUSTED"
    assert evidence is False
    assert in_window is True


# --------------------------------------------------------------------------
# AC13 / scenario A5 — historical qualification is preserved, not conflated
# --------------------------------------------------------------------------
def test_completed_in_window_is_historical_not_current(conn):
    contrato_id = "lct-v1-a5-completed"
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_assinatura, status_normalized,
                 quality_state, is_active)
            VALUES (%s, CURRENT_DATE - 600, CURRENT_DATE - 600, 'COMPLETED', 'VALID', FALSE)
            """,
            (contrato_id,),
        )
        cur.execute(
            "SELECT lifecycle_state, lifecycle_is_current_evidence, "
            "contracting_date_in_qualification_window "
            "FROM public.v_contract_lifecycle_truth_v1 WHERE contrato_id = %s",
            (contrato_id,),
        )
        state, evidence, in_window = cur.fetchone()

    assert state == "COMPLETED"
    assert evidence is False
    assert in_window is True


# --------------------------------------------------------------------------
# AC14 / scenario A6 — inverted vigência comes from the upstream classifiers
# --------------------------------------------------------------------------
def test_inverted_vigencia_projects_upstream_classifier_output(conn):
    """The view projects, never re-derives.

    The stamps are produced here by the existing Python classifiers, exactly as
    ``stamp_contract_truth_labels`` would produce them; the view must not
    contain any SQL-side inversion detection of its own.
    """
    start, end = date(2024, 9, 1), date(2024, 3, 1)
    activity = classify_contract_activity(vigencia_inicio=start, vigencia_fim=end)
    quality = classify_contract_quality(data_inicio=start, data_fim=end)

    assert activity.state == "UNKNOWN"
    assert quality.state == "QUARANTINED"
    assert "inverted_vigencia" in activity.reasons

    contrato_id = "lct-v1-a6-inverted"
    with conn.cursor() as cur:
        _insert_contract(
            cur,
            contrato_id,
            data_inicio=start,
            data_fim=end,
            status_normalized=activity.state,
            quality_state=quality.state,
        )
        state, trust, evidence, _codes = _lifecycle(cur, contrato_id)

    assert state == "UNKNOWN"
    assert trust == "UNTRUSTED"
    assert evidence is False


# --------------------------------------------------------------------------
# AC4 / scenario A7 — one row per dedup key, deterministic tiebreak
# --------------------------------------------------------------------------
def test_dedup_key_yields_one_row_per_logical_contract(conn):
    """Two rows share a canonical id; one has none and falls back to contrato_id."""
    shared = "lct-v1-canonical-shared"
    with conn.cursor() as cur:
        _insert_contract(
            cur,
            "lct-v1-a7-older",
            canonical_contract_id=shared,
            last_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
            status_normalized="COMPLETED",
        )
        _insert_contract(
            cur,
            "lct-v1-a7-newer",
            canonical_contract_id=shared,
            last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
            status_normalized="ACTIVE_PROVEN",
        )
        _insert_contract(
            cur,
            "lct-v1-a7-orphan",
            canonical_contract_id=None,
            status_normalized="SUSPENDED",
        )

        cur.execute(
            "SELECT dedup_key, contrato_id, lifecycle_state "
            "FROM public.v_contract_lifecycle_truth_v1 "
            "WHERE dedup_key IN (%s, %s) ORDER BY dedup_key",
            (shared, "lct-v1-a7-orphan"),
        )
        rows = cur.fetchall()

    assert len(rows) == 2
    by_key = {row[0]: row for row in rows}
    assert by_key[shared][1] == "lct-v1-a7-newer"
    assert by_key[shared][2] == "ACTIVE_PROVEN"
    assert by_key["lct-v1-a7-orphan"][1] == "lct-v1-a7-orphan"


def test_empty_canonical_contract_id_falls_back_to_contrato_id(conn):
    """NULLIF('' , '') keeps an empty canonical id from collapsing rows."""
    with conn.cursor() as cur:
        _insert_contract(cur, "lct-v1-a7-empty-a", canonical_contract_id="")
        _insert_contract(cur, "lct-v1-a7-empty-b", canonical_contract_id="")
        cur.execute(
            "SELECT dedup_key FROM public.v_contract_lifecycle_truth_v1 "
            "WHERE contrato_id IN (%s, %s) ORDER BY dedup_key",
            ("lct-v1-a7-empty-a", "lct-v1-a7-empty-b"),
        )
        keys = [row[0] for row in cur.fetchall()]

    assert keys == ["lct-v1-a7-empty-a", "lct-v1-a7-empty-b"]


# --------------------------------------------------------------------------
# AC5 — population parity with v_contracts_canonical_v2
# --------------------------------------------------------------------------
def test_population_filter_matches_canonical_v2(conn):
    """Same WHERE predicate: a row invisible to v2 is invisible here too."""
    visible = "lct-v1-pop-visible"
    invisible = "lct-v1-pop-invisible"
    with conn.cursor() as cur:
        _insert_contract(cur, visible, data_inicio=date(2024, 5, 1))
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_publicacao, data_assinatura)
            VALUES (%s, NULL, NULL, DATE '2024-05-01')
            """,
            (invisible,),
        )

        for view in ("v_contracts_canonical_v2", "v_contract_lifecycle_truth_v1"):
            cur.execute(
                f"SELECT contrato_id FROM public.{view} WHERE contrato_id IN (%s, %s)",
                (visible, invisible),
            )
            found = {row[0] for row in cur.fetchall()}
            assert found == {visible}, f"{view} population diverged"


# --------------------------------------------------------------------------
# AC18 (secondary) — qualified-root counts are untouched by this migration
# --------------------------------------------------------------------------
def test_qualified_roots_unchanged_by_the_new_view(conn):
    """Secondary evidence only. The structural proof carries AC18.

    The local DB is empty, so a 0 == 0 result would prove nothing. Synthetic
    fixture data is inserted so the qualification query returns a non-empty
    set, and that set is then shown to be identical before and after the new
    view is read. ``v_contracts_canonical_v2``'s definition is also asserted
    free of any reference to the objects added by migration 103.
    """
    # Check-digit-valid CNPJ: ck_contract_supplier_identity_consistent enforces
    # fn_contract_valid_cnpj(supplier_identifier) and fornecedor_cnpj equality.
    cnpj14 = "99887766000105"
    root8 = cnpj14[:8]
    company_key = "lct-v1-ac18-company"
    now = datetime.now(UTC)

    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(
            """
            INSERT INTO public.confenge_company_sector_current
                (company_key, cnpj_raiz, sector_class, sector_version,
                 sector_classifier_sha256, input_fingerprint, computed_at)
            VALUES (%s, %s, 'CONSTRUCTION_CONFIRMED', 'test', 'test', 'test', now())
            """,
            (company_key, root8),
        )
        cur.execute(
            """
            INSERT INTO public.confenge_target_fit_shadow
                (company_key, cnpj_raiz, shadow_class, target_fit_version,
                 input_fingerprint, computed_at)
            VALUES (%s, %s, %s, 'test', 'test', now())
            """,
            (company_key, root8, TARGET_CONFIRMED),
        )
        cur.execute(
            """
            INSERT INTO public.pncp_supplier_contracts
                (contrato_id, data_inicio, data_assinatura, fornecedor_cnpj,
                 supplier_id_type, supplier_identifier, orgao_cnpj,
                 status_normalized, quality_state, is_active)
            VALUES (%s, CURRENT_DATE - 30, CURRENT_DATE - 30, %s,
                    'CNPJ', %s, '11222333000181', 'COMPLETED', 'VALID', FALSE)
            """,
            ("lct-v1-ac18-contract", cnpj14, cnpj14),
        )

        params = {
            "target_confirmed": TARGET_CONFIRMED,
            "window_floor": window_floor(now),
            "today": now.date(),
        }
        cur.execute(QUALIFICATION_SQL, params)
        before = sorted(row[0] for row in cur.fetchall())

        cur.execute("SELECT count(*) FROM public.v_contract_lifecycle_truth_v1")
        cur.fetchone()

        cur.execute(QUALIFICATION_SQL, params)
        after = sorted(row[0] for row in cur.fetchall())

        cur.execute("SELECT pg_get_viewdef('public.v_contracts_canonical_v2'::regclass, TRUE)")
        (canonical_v2_definition,) = cur.fetchone()

    assert before, "fixture did not qualify any root; the comparison would be vacuous"
    assert before == after
    assert root8 in before
    for new_object in (
        "v_contract_lifecycle_truth_v1",
        "contract_contracting_date_v1",
        "contract_contracting_date_field_v1",
        "contract_window_floor_v1",
    ):
        assert new_object not in canonical_v2_definition
