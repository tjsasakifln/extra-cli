"""Adversarial tests: national inventory volume must not become SC coverage."""

from __future__ import annotations

import inspect

from scripts.coverage import dual_capability_coverage as dual
from scripts.coverage.dual_capability_coverage import (
    CanonicalEntity,
    EntityCapabilityResult,
    UniverseIdentity,
    aggregate_capability,
)


def test_dual_module_documents_presence_not_coverage() -> None:
    assert "data_presence" in inspect.getsource(dual)
    doc = dual.__doc__ or ""
    assert "never a coverage label" in doc or "descriptive only" in doc


def _canon(eid: str) -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=0,
        razao_social=eid,
        cnpj8=eid[:8].ljust(8, "0")[:8],
        municipio="X",
        codigo_ibge="4200000",
        natureza_juridica="autarquia",
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="fixture",
        identity_key=eid,
    )


def _entity_result(
    eid: str,
    *,
    covered: bool = False,
    has_data_presence: bool = False,
) -> EntityCapabilityResult:
    return EntityCapabilityResult(
        entity_id=eid,
        entity_name=eid,
        capability="historical_contracts",
        applicability="applicable",
        covered=covered,
        coverage_state="success_with_data" if covered else "never_checked",
        required_sources=["pncp", "contracts"],
        successful_sources=["pncp", "contracts"] if covered else [],
        missing_sources=[] if covered else ["pncp", "contracts"],
        freshness_status="fresh" if covered else "unknown",
        last_success_at=None,
        blocker="" if covered else "never_checked",
        next_action="none" if covered else "run_required_sources",
        evidence_reference="fixture",
        has_data_presence=has_data_presence,
    )


def _identity(ids: list[str]) -> UniverseIdentity:
    return UniverseIdentity(
        entity_count=len(ids),
        seed_path="fixture",
        seed_sha256="a" * 64,
        canonical_ids_sha256="b" * 64,
        radius_km=200.0,
        radius_rule="fixture",
        as_of="2026-07-22T00:00:00Z",
        git_sha="test",
        schema_version="test",
        entity_ids=tuple(ids),
        universe_version="fixture-test",
    )


def test_coverage_pct_independent_of_national_presence_signal() -> None:
    """High data_presence must not raise coverage_pct when entities are not covered."""
    ids = [f"e{i}" for i in range(5)]
    entities = [_canon(i) for i in ids]
    results = [_entity_result(i, covered=False, has_data_presence=True) for i in ids]
    agg = aggregate_capability(
        "historical_contracts",
        entities,
        results,
        _identity(ids),
        data_presence_numerator=5,
    )
    assert agg.covered_numerator == 0
    assert agg.coverage_pct == 0.0
    assert agg.data_presence_numerator == 5
    assert agg.data_presence_pct == 100.0
    assert agg.gate_status in {"FAIL", "NOT_READY"}
    assert agg.coverage_gate_pass is False


def test_inserting_more_presence_does_not_change_zero_coverage() -> None:
    """Simulates national volume growth: presence rises, coverage stays 0."""
    ids = ["a", "b", "c"]
    entities = [_canon(i) for i in ids]
    r0 = aggregate_capability(
        "historical_contracts",
        entities,
        [_entity_result(i, has_data_presence=False) for i in ids],
        _identity(ids),
        data_presence_numerator=0,
    )
    r1 = aggregate_capability(
        "historical_contracts",
        entities,
        [_entity_result(i, has_data_presence=True) for i in ids],
        _identity(ids),
        data_presence_numerator=3,
    )
    assert r0.coverage_pct == r1.coverage_pct == 0.0
    assert r0.covered_numerator == r1.covered_numerator == 0
    assert r0.applicable_denominator == r1.applicable_denominator == 3
    assert r0.data_presence_numerator == 0
    assert r1.data_presence_numerator == 3


def test_invariants_doc_exists() -> None:
    from pathlib import Path

    p = Path(
        "artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/"
        "coverage-isolation/invariants.md"
    )
    assert p.is_file()
    assert "success_zero" in p.read_text(encoding="utf-8")


def test_scope_labels_forbid_coverage_alias() -> None:
    from pathlib import Path

    p = Path(
        "specs/003-national-contracts-intelligence-architecture/contracts/scope-classification.md"
    )
    text = p.read_text(encoding="utf-8")
    assert "raw_national" in text and "geo_sc" in text and "canonical_sc_operational" in text
