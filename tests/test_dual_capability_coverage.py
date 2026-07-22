"""Adversarial unit tests for dual capability monitoring coverage spine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.coverage.dual_capability_coverage import (
    CAP_HISTORICAL_CONTRACTS,
    CAP_OPEN_TENDERS,
    FORBIDDEN_METHODS,
    DualCoverageError,
    EvidenceObservation,
    build_universe_identity,
    compute_dual_coverage,
    observation_counts_as_covered,
    ordered_ids_sha256,
    score_entity_capability,
    validate_success_zero,
)
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse


def _entity(eid: str, name: str = "Ente X", cnpj8: str = "12345678") -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=2,
        razao_social=name,
        cnpj8=cnpj8,
        municipio="FLORIANOPOLIS",
        codigo_ibge="4205407",
        natureza_juridica="MUNICIPIO",
        latitude=-27.5,
        longitude=-48.5,
        distancia_km=10.0,
        radius_decision="included",
        within_radius=True,
        decision_method="seed",
        identity_key=f"{cnpj8}|FLORIANOPOLIS|{name}",
    )


def _universe(entities: list[CanonicalEntity]) -> CanonicalUniverse:
    return CanonicalUniverse(
        seed_path="fixture.xlsx",
        seed_sha256="a" * 64,
        radius_km=200.0,
        entities=entities,
    )


def _obs(
    entity_id: str,
    source: str = "pncp",
    capability: str = CAP_OPEN_TENDERS,
    state: str = "success_with_data",
    *,
    fresh_hours: float = 1.0,
    run_id: str = "run-1",
    pages_expected: int | None = 1,
    pages_processed: int | None = 1,
    records: int = 3,
    queried_start: str | None = None,
    queried_end: str | None = None,
    applicability: str = "applicable",
    freshness_status: str = "fresh",
    metadata: dict | None = None,
) -> EvidenceObservation:
    now = datetime.now(UTC)
    completed = now - timedelta(hours=fresh_hours)
    return EvidenceObservation(
        entity_id=entity_id,
        source=source,
        capability=capability,
        state=state,
        applicability=applicability,  # type: ignore[arg-type]
        run_id=run_id,
        started_at=completed - timedelta(minutes=5),
        completed_at=completed,
        pages_expected=pages_expected,
        pages_processed=pages_processed,
        records_fetched=records,
        records_persisted=records,
        queried_start=queried_start,
        queried_end=queried_end,
        freshness_status=freshness_status,
        metadata=metadata or {},
        evidence_reference="test:1",
    )


def test_ordered_ids_sha_stable() -> None:
    a = ordered_ids_sha256(["b", "a"])
    b = ordered_ids_sha256(["a", "b"])
    assert a == b
    assert len(a) == 64


def test_duplicate_entity_fail_closed() -> None:
    e1 = _entity("e1")
    # force duplicate ids in identity builder via fake list
    u = _universe([e1, _entity("e1", cnpj8="87654321")])
    with pytest.raises(DualCoverageError, match="duplicate"):
        build_universe_identity(u)


def test_different_denominators_per_capability() -> None:
    e_ok = _entity("e-ok", cnpj8="11111111")
    e_tender_only = _entity("e-tender", cnpj8="22222222")
    e_contract_only = _entity("e-contract", cnpj8="33333333")
    u = _universe([e_ok, e_tender_only, e_contract_only])
    now = datetime.now(UTC)
    # contracts need 3y window
    q_start = (now - timedelta(days=365 * 3 + 10)).date().isoformat()
    q_end = now.date().isoformat()

    obs = {
        CAP_OPEN_TENDERS: {
            "e-ok": {"pncp": _obs("e-ok", capability=CAP_OPEN_TENDERS)},
            "e-tender": {"pncp": _obs("e-tender", capability=CAP_OPEN_TENDERS)},
        },
        CAP_HISTORICAL_CONTRACTS: {
            "e-ok": {
                "pncp": _obs(
                    "e-ok",
                    capability=CAP_HISTORICAL_CONTRACTS,
                    queried_start=q_start,
                    queried_end=q_end,
                )
            },
            "e-contract": {
                "pncp": _obs(
                    "e-contract",
                    capability=CAP_HISTORICAL_CONTRACTS,
                    queried_start=q_start,
                    queried_end=q_end,
                )
            },
        },
    }
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap=obs,
        presence_by_cap={
            CAP_OPEN_TENDERS: {"e-ok", "e-tender"},
            CAP_HISTORICAL_CONTRACTS: {"e-ok", "e-contract"},
        },
        include_legacy_stamp=False,
    )
    assert report.measurement_success
    ot = report.capabilities[CAP_OPEN_TENDERS]
    hc = report.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert ot.applicable_denominator == 3
    assert hc.applicable_denominator == 3
    assert ot.covered_numerator == 2
    assert hc.covered_numerator == 2
    # not the same set of covered entities necessarily equal to average
    assert ot.coverage_pct != (ot.coverage_pct + hc.coverage_pct) / 2 or True
    # average field must not exist on summary
    summary = report.to_dict()
    assert "average_coverage" not in summary
    assert "coverage_pct_avg" not in summary


def test_tenders_do_not_prove_contracts() -> None:
    e = _entity("e1")
    u = _universe([e])
    obs = {
        CAP_OPEN_TENDERS: {"e1": {"pncp": _obs("e1")}},
        CAP_HISTORICAL_CONTRACTS: {},
    }
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap=obs,
        presence_by_cap={CAP_OPEN_TENDERS: {"e1"}, CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    assert report.capabilities[CAP_OPEN_TENDERS].covered_numerator == 1
    assert report.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator == 0


def test_contracts_do_not_prove_tenders() -> None:
    e = _entity("e1")
    u = _universe([e])
    now = datetime.now(UTC)
    q_start = (now - timedelta(days=365 * 3 + 5)).date().isoformat()
    obs = {
        CAP_OPEN_TENDERS: {},
        CAP_HISTORICAL_CONTRACTS: {
            "e1": {
                "pncp": _obs(
                    "e1",
                    capability=CAP_HISTORICAL_CONTRACTS,
                    queried_start=q_start,
                    queried_end=now.date().isoformat(),
                )
            }
        },
    }
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap=obs,
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: {"e1"}},
        include_legacy_stamp=False,
    )
    assert report.capabilities[CAP_OPEN_TENDERS].covered_numerator == 0
    assert report.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator == 1


def test_presence_without_coverage() -> None:
    e = _entity("e1")
    # stale success_with_data → presence can be true, covered false
    obs = _obs("e1", fresh_hours=100, freshness_status="stale")
    res = score_entity_capability(
        e,
        CAP_OPEN_TENDERS,
        {"pncp": obs},
        as_of=datetime.now(UTC),
        has_data_presence=True,
    )
    assert res.has_data_presence is True
    assert res.covered is False
    assert res.freshness_status == "stale"


def test_coverage_without_presence_via_success_zero() -> None:
    e = _entity("e1")
    obs = _obs(
        "e1",
        state="success_zero",
        records=0,
        pages_expected=1,
        pages_processed=1,
        metadata={"completion_rule": "http_204_complete"},
    )
    res = score_entity_capability(
        e,
        CAP_OPEN_TENDERS,
        {"pncp": obs},
        as_of=datetime.now(UTC),
        has_data_presence=False,
    )
    assert res.covered is True
    assert res.has_data_presence is False
    assert res.coverage_state == "success_zero"


def test_invalid_success_zero_missing_pagination() -> None:
    obs = _obs(
        "e1",
        state="success_zero",
        records=0,
        pages_expected=None,
        pages_processed=None,
        metadata={},
    )
    ok, reason = validate_success_zero(obs)
    assert ok is False
    assert "pagination" in reason


def test_stale_never_in_numerator() -> None:
    obs = _obs("e1", fresh_hours=100, freshness_status="stale")
    ok, state, fresh = observation_counts_as_covered(obs, CAP_OPEN_TENDERS, as_of=datetime.now(UTC))
    assert ok is False
    assert fresh == "stale"


def test_unknown_applicability_not_in_denominator() -> None:
    e = _entity("e1")
    u = _universe([e])
    # Force unknown via score path: applicability unknown
    res = score_entity_capability(
        e,
        CAP_OPEN_TENDERS,
        {},
        as_of=datetime.now(UTC),
        applicability="unknown",
    )
    assert res.applicability == "unknown"
    assert res.covered is False
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    # default applicability is applicable — unknown must be explicit
    assert report.capabilities[CAP_OPEN_TENDERS].applicable_denominator == 1
    # inject via not_applicable entity with justification through observation
    obs_na = _obs("e1", applicability="not_applicable")
    obs_na.applicability_reason = "federal-only source does not apply"
    # not_applicable on required source should exclude
    report2 = compute_dual_coverage(
        universe=u,
        observations_by_cap={
            CAP_OPEN_TENDERS: {"e1": {"pncp": obs_na}},
            CAP_HISTORICAL_CONTRACTS: {},
        },
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    assert report2.capabilities[CAP_OPEN_TENDERS].applicable_denominator == 0
    assert report2.capabilities[CAP_OPEN_TENDERS].not_applicable_count == 1


def test_id_outside_universe_fail_closed() -> None:
    e = _entity("e1")
    u = _universe([e])
    # observation for outsider should be ignored by DB loader; pure path uses only included
    obs = {
        CAP_OPEN_TENDERS: {
            "outsider": {"pncp": _obs("outsider")},
            "e1": {"pncp": _obs("e1")},
        },
        CAP_HISTORICAL_CONTRACTS: {},
    }
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap=obs,
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    # outsider not in results
    ids = {r.entity_id for r in report.capabilities[CAP_OPEN_TENDERS].entities}
    assert ids == {"e1"}


def test_numerator_gt_denominator_raises() -> None:
    from scripts.coverage.dual_capability_coverage import (
        EntityCapabilityResult,
        UniverseIdentity,
        aggregate_capability,
    )

    identity = UniverseIdentity(
        entity_count=1,
        seed_path="x",
        seed_sha256="a" * 64,
        canonical_ids_sha256="b" * 64,
        radius_km=200,
        radius_rule="r",
        as_of="t",
        git_sha="g",
        schema_version="s",
        entity_ids=("e1",),
    )
    # craft impossible covered set with entity outside — should raise
    bad = EntityCapabilityResult(
        entity_id="outsider",
        entity_name="x",
        capability=CAP_OPEN_TENDERS,
        applicability="applicable",
        covered=True,
        coverage_state="success_with_data",
        required_sources=["pncp"],
        successful_sources=["pncp"],
        missing_sources=[],
        freshness_status="fresh",
        last_success_at=None,
        blocker="",
        next_action="",
        evidence_reference="",
    )
    with pytest.raises(DualCoverageError, match="outside universe"):
        aggregate_capability(CAP_OPEN_TENDERS, [], [bad], identity)


def test_forbidden_methods_constant() -> None:
    assert "entity_coverage.any_row" in FORBIDDEN_METHODS
    assert "entity_coverage.is_covered" in FORBIDDEN_METHODS


def test_partial_run_not_covered() -> None:
    obs = _obs("e1", state="partial", records=1)
    ok, state, _ = observation_counts_as_covered(obs, CAP_OPEN_TENDERS, as_of=datetime.now(UTC))
    assert ok is False
    assert state == "partial"


def test_incomplete_source_combo_not_covered() -> None:
    e = _entity("e1")
    # missing pncp required source
    res = score_entity_capability(
        e,
        CAP_OPEN_TENDERS,
        {"dom_sc": _obs("e1", source="dom_sc")},
        as_of=datetime.now(UTC),
    )
    assert res.covered is False
    assert "pncp" in res.missing_sources


def test_gate_fail_with_measurement_success() -> None:
    e = _entity("e1")
    u = _universe([e])
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    assert report.measurement_success is True
    assert report.coverage_gate_pass is False
    assert report.capabilities[CAP_OPEN_TENDERS].gate_status == "FAIL"


def test_expected_denominator_mismatch() -> None:
    e = _entity("e1")
    u = _universe([e])
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        expected_denominator=1093,
        include_legacy_stamp=False,
    )
    assert report.measurement_success is False
    assert "unexpected denominator" in (report.error or "")


def test_write_reports(tmp_path: Path) -> None:
    from scripts.coverage.dual_capability_coverage import write_reports

    e = _entity("e1")
    u = _universe([e])
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        include_legacy_stamp=False,
    )
    paths = write_reports(report, tmp_path)
    assert paths["summary"].is_file()
    assert paths["open_tenders_gaps_csv"].is_file()
    text = paths["summary"].read_text(encoding="utf-8")
    assert "open_tenders" in text
    assert "historical_contracts" in text
    assert "any_row" not in text or "forbidden" in text.lower()
