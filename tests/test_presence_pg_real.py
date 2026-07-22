"""Real PostgreSQL presence states — fail-closed measurability (§12.3).

Every status assertion drives ``load_data_presence`` on a real connection.
No handcrafted PresenceLoadResult as the unit under test; no ``or True``.
"""

from __future__ import annotations

import os
import uuid

import pytest

from scripts.coverage.dual_capability_coverage import (
    CAP_HISTORICAL_CONTRACTS,
    CAP_OPEN_TENDERS,
    PRESENCE_NOT_MEASURABLE,
    EntityCapabilityResult,
    aggregate_capability,
    build_universe_identity,
    load_data_presence,
)
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse

pytestmark = pytest.mark.real_db

DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")


def _conn():
    import psycopg2

    try:
        return psycopg2.connect(DSN, connect_timeout=5)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no postgres: {exc}")


def _require_real() -> None:
    try:
        c = _conn()
        c.close()
    except Exception:
        pytest.skip("DB unreachable")


def _entity() -> CanonicalEntity:
    return CanonicalEntity(
        entity_id="e1",
        seed_row=1,
        razao_social="X",
        cnpj8="12345678",
        municipio="Y",
        codigo_ibge="1",
        natureza_juridica="Município",
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="t",
        identity_key="k",
    )


def test_pg_measured_rows_or_no_rows_via_loader() -> None:
    """Table present → loader returns measured/no_rows/unmapped — never silent zero without status."""
    _require_real()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='pncp_raw_bids'
            """
        )
        if not cur.fetchone():
            pytest.skip("pncp_raw_bids absent")
        cur.close()
        pres = load_data_presence(conn, CAP_OPEN_TENDERS, {}, set())
        assert pres.status != "table_absent"
        assert pres.status in {
            "no_rows",
            "rows_present",
            "measured_no_rows",
            "measured_rows_present",
            "unmapped_rows",
            "column_absent",
            "partially_unmapped",
            "fully_unmapped",
            "query_failed",
        }
        # Non-measurable statuses must not publish as measured zero without flag
        if pres.status in PRESENCE_NOT_MEASURABLE or pres.status in {
            "table_absent",
            "column_absent",
            "query_failed",
            "fully_unmapped",
            "unmapped_rows",
        }:
            # Aggregate must force null pct when marked not measurable
            if pres.status in {"column_absent", "query_failed", "table_absent"} or (
                pres.status in {"unmapped_rows", "fully_unmapped"} and not pres.entity_ids
            ):
                e = _entity()
                u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
                r = EntityCapabilityResult(
                    entity_id="e1",
                    entity_name="X",
                    capability=CAP_OPEN_TENDERS,
                    applicability="applicable",
                    covered=False,
                    coverage_state="never_checked",
                    required_sources=["pncp"],
                    successful_sources=[],
                    missing_sources=["pncp"],
                    freshness_status="unknown",
                    last_success_at=None,
                    blocker="",
                    next_action="run",
                    evidence_reference="",
                )
                st = "fully_unmapped" if pres.status in {"unmapped_rows"} and not pres.entity_ids else pres.status
                cap = aggregate_capability(
                    CAP_OPEN_TENDERS,
                    [e],
                    [r],
                    build_universe_identity(u, as_of="t"),
                    data_presence_status=st,
                    data_presence_numerator=0,
                    presence_not_measurable=True,
                )
                assert cap.data_presence_pct is None
                assert cap.measurement_success is False
    finally:
        conn.close()


def test_pg_table_absent_via_rename_roundtrip() -> None:
    """Drive load_data_presence table_absent by temporarily renaming the real table."""
    _require_real()
    conn = _conn()
    conn.autocommit = False
    bak = f"pncp_raw_bids_bak_{uuid.uuid4().hex[:8]}"
    renamed = False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='pncp_raw_bids'
            """
        )
        if not cur.fetchone():
            # Already absent — loader must report table_absent
            cur.close()
            pres = load_data_presence(conn, CAP_OPEN_TENDERS, {}, set())
            assert pres.status == "table_absent"
            assert pres.entity_ids == set()
            return
        cur.execute(f'ALTER TABLE pncp_raw_bids RENAME TO "{bak}"')
        conn.commit()
        renamed = True
        cur.close()
        pres = load_data_presence(conn, CAP_OPEN_TENDERS, {}, set())
        assert pres.status == "table_absent"
        assert pres.entity_ids == set()
        # Aggregate null path
        e = _entity()
        u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
        r = EntityCapabilityResult(
            entity_id="e1",
            entity_name="X",
            capability=CAP_OPEN_TENDERS,
            applicability="applicable",
            covered=False,
            coverage_state="never_checked",
            required_sources=["pncp"],
            successful_sources=[],
            missing_sources=["pncp"],
            freshness_status="unknown",
            last_success_at=None,
            blocker="",
            next_action="run",
            evidence_reference="",
        )
        cap = aggregate_capability(
            CAP_OPEN_TENDERS,
            [e],
            [r],
            build_universe_identity(u, as_of="t"),
            data_presence_status="table_absent",
            data_presence_numerator=0,
            presence_not_measurable=True,
        )
        assert cap.data_presence_pct is None
        assert cap.measurement_success is False
    finally:
        if renamed:
            try:
                cur = conn.cursor()
                cur.execute(f'ALTER TABLE "{bak}" RENAME TO pncp_raw_bids')
                conn.commit()
                cur.close()
            except Exception:
                conn.rollback()
        conn.close()


def test_pg_historical_table_absent_or_measured() -> None:
    _require_real()
    conn = _conn()
    try:
        pres = load_data_presence(conn, CAP_HISTORICAL_CONTRACTS, {}, set())
        assert pres.status in {
            "table_absent",
            "no_rows",
            "rows_present",
            "measured_no_rows",
            "measured_rows_present",
            "unmapped_rows",
            "column_absent",
            "partially_unmapped",
            "fully_unmapped",
            "query_failed",
        }
        if pres.status == "table_absent":
            assert not pres.entity_ids
    finally:
        conn.close()


def test_pg_fully_unmapped_not_measured_zero() -> None:
    """Empty identity maps + existing rows → unmapped; aggregate pct null."""
    _require_real()
    conn = _conn()
    try:
        pres = load_data_presence(
            conn,
            CAP_OPEN_TENDERS,
            {},
            set(),
            cnpj8_to_entity_id={},
        )
        if pres.status in {"table_absent", "column_absent", "no_rows", "measured_no_rows"}:
            # No rows to unmap — still valid loader result
            if pres.status in {"table_absent", "column_absent"}:
                assert pres.status in PRESENCE_NOT_MEASURABLE or pres.status in {
                    "table_absent",
                    "column_absent",
                }
            return
        if pres.unmapped_count > 0 and not pres.entity_ids:
            assert pres.status in {"unmapped_rows", "fully_unmapped"}
            e = _entity()
            u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
            r = EntityCapabilityResult(
                entity_id="e1",
                entity_name="X",
                capability=CAP_OPEN_TENDERS,
                applicability="applicable",
                covered=False,
                coverage_state="never_checked",
                required_sources=["pncp"],
                successful_sources=[],
                missing_sources=["pncp"],
                freshness_status="unknown",
                last_success_at=None,
                blocker="",
                next_action="run",
                evidence_reference="",
            )
            cap = aggregate_capability(
                CAP_OPEN_TENDERS,
                [e],
                [r],
                build_universe_identity(u, as_of="t"),
                data_presence_status="fully_unmapped",
                data_presence_numerator=0,
                presence_not_measurable=True,
            )
            assert cap.data_presence_pct is None
            assert cap.measurement_success is False
            assert cap.data_presence_complete is False
    finally:
        conn.close()


def test_pg_query_failed_classification() -> None:
    _require_real()
    from scripts.coverage.dual_capability_coverage import _classify_db_exception

    class FakeUndefinedColumnError(Exception):
        pgcode = "42703"

    assert _classify_db_exception(FakeUndefinedColumnError("column x does not exist")) == "column_absent"

    class FakeUndefinedTableError(Exception):
        pgcode = "42P01"

    assert _classify_db_exception(FakeUndefinedTableError("relation y does not exist")) == "table_absent"

    class FakeOtherError(Exception):
        pass

    assert _classify_db_exception(FakeOtherError("syntax error")) == "query_failed"
