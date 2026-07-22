"""Presence measurability fail-closed (null pct, never fake zero)."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.coverage.dual_capability_coverage import (
    CAP_OPEN_TENDERS,
    PresenceLoadResult,
    aggregate_capability,
    build_universe_identity,
)
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse


def _entity(eid: str = "e1") -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=1,
        razao_social="Ente",
        cnpj8="12345678",
        municipio="FLORIANOPOLIS",
        codigo_ibge="4205407",
        natureza_juridica="Município",
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="t",
        identity_key="k",
    )


def _id(u: CanonicalUniverse):
    return build_universe_identity(u, as_of=datetime.now(UTC).isoformat())


def test_table_absent_presence_null_not_zero() -> None:
    e = _entity()
    u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
    from scripts.coverage.dual_capability_coverage import EntityCapabilityResult

    results = [
        EntityCapabilityResult(
            entity_id="e1",
            entity_name="Ente",
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
            has_data_presence=False,
        )
    ]
    cap = aggregate_capability(
        CAP_OPEN_TENDERS,
        [e],
        results,
        _id(u),
        data_presence_status="table_absent",
        data_presence_numerator=0,
        presence_not_measurable=True,
    )
    assert cap.data_presence_pct is None
    assert cap.data_presence_status == "table_absent"
    assert cap.data_presence_complete is False
    assert cap.measurement_success is False


def test_fully_unmapped_not_measured_zero() -> None:
    e = _entity()
    u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
    from scripts.coverage.dual_capability_coverage import EntityCapabilityResult

    results = [
        EntityCapabilityResult(
            entity_id="e1",
            entity_name="Ente",
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
            has_data_presence=False,
        )
    ]
    cap = aggregate_capability(
        CAP_OPEN_TENDERS,
        [e],
        results,
        _id(u),
        data_presence_status="fully_unmapped",
        data_presence_numerator=0,
        presence_not_measurable=True,
    )
    assert cap.data_presence_pct is None
    assert cap.measurement_success is False


def test_measured_no_rows_can_be_zero() -> None:
    e = _entity()
    u = CanonicalUniverse(seed_path="x", seed_sha256="a" * 64, radius_km=200.0, entities=[e])
    from scripts.coverage.dual_capability_coverage import EntityCapabilityResult

    results = [
        EntityCapabilityResult(
            entity_id="e1",
            entity_name="Ente",
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
            has_data_presence=False,
        )
    ]
    cap = aggregate_capability(
        CAP_OPEN_TENDERS,
        [e],
        results,
        _id(u),
        data_presence_status="measured_no_rows",
        data_presence_numerator=0,
        presence_not_measurable=False,
    )
    assert cap.data_presence_pct == 0.0
    assert cap.data_presence_complete is True


def test_presence_load_result_dict() -> None:
    p = PresenceLoadResult(status="table_absent", table_name="pncp_raw_bids", error="table_absent")
    d = p.to_dict()
    assert d["status"] == "table_absent"
    assert d["entity_count"] == 0
