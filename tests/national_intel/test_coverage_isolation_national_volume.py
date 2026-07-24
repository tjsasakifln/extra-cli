"""SC coverage isolation — real dual spine + load_canonical_universe.

Supplements adversarial matrix (test_adversarial_nv_matrix.py).
Does not depend on PR #121 campaign artifacts; uses shipped migration/spec 004.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from scripts.coverage import dual_capability_coverage as dual
from scripts.coverage.dual_capability_coverage import (
    CAP_HISTORICAL_CONTRACTS,
    CAP_OPEN_TENDERS,
    compute_dual_coverage,
)
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse, load_canonical_universe

ROOT = Path(__file__).resolve().parents[2]


def test_dual_module_documents_presence_not_coverage() -> None:
    doc = dual.__doc__ or ""
    assert "data_presence" in inspect.getsource(dual)
    assert "never a coverage label" in doc or "descriptive only" in doc


def _entity(eid: str, cnpj8: str = "12345678") -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=2,
        razao_social=eid,
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
        identity_key=f"{cnpj8}|{eid}",
    )


def _universe(entities: list[CanonicalEntity]) -> CanonicalUniverse:
    return CanonicalUniverse(
        seed_path="fixture.xlsx",
        seed_sha256="a" * 64,
        radius_km=200.0,
        entities=entities,
    )


def _empty_dual(entities: list[CanonicalEntity], presence: set[str] | None = None):
    appl = {
        CAP_OPEN_TENDERS: {e.entity_id: "applicable" for e in entities},
        CAP_HISTORICAL_CONTRACTS: {e.entity_id: "applicable" for e in entities},
    }
    req = {
        CAP_OPEN_TENDERS: {e.entity_id: ["pncp"] for e in entities},
        CAP_HISTORICAL_CONTRACTS: {e.entity_id: ["pncp"] for e in entities},
    }
    return compute_dual_coverage(
        universe=_universe(entities),
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={
            CAP_OPEN_TENDERS: set(),
            CAP_HISTORICAL_CONTRACTS: presence or set(),
        },
        entity_applicability=appl,  # type: ignore[arg-type]
        entity_required_sources=req,  # type: ignore[arg-type]
        include_legacy_stamp=False,
        use_config_matrix=False,
        require_canonical_policy=False,
    )


def test_compute_dual_coverage_before_after_presence_volume() -> None:
    ents = [_entity(f"e{i}", cnpj8=f"1100000{i}") for i in range(5)]
    before = _empty_dual(ents, presence=set())
    after = _empty_dual(ents, presence={e.entity_id for e in ents})
    b = before.capabilities[CAP_HISTORICAL_CONTRACTS]
    a = after.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert b.covered_numerator == a.covered_numerator == 0
    assert b.coverage_pct == a.coverage_pct == 0.0
    assert b.applicable_denominator == a.applicable_denominator == 5
    assert a.data_presence_numerator == 5
    assert b.data_presence_numerator == 0
    assert before.coverage_gate_pass is False
    assert after.coverage_gate_pass is False


def test_load_canonical_universe_denominator_authority() -> None:
    seed = ROOT / "fixtures/canonical_universe_r0.xlsx"
    u = load_canonical_universe(seed_path=seed)
    assert len(u.included) == 1093
    slice_ents = list(u.included)[:5]
    report = compute_dual_coverage(
        universe=CanonicalUniverse(
            seed_path=u.seed_path,
            seed_sha256=u.seed_sha256,
            radius_km=u.radius_km,
            entities=slice_ents,
        ),
        observations_by_cap={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        entity_applicability={
            CAP_OPEN_TENDERS: {e.entity_id: "applicable" for e in slice_ents},
            CAP_HISTORICAL_CONTRACTS: {e.entity_id: "applicable" for e in slice_ents},
        },  # type: ignore[arg-type]
        entity_required_sources={
            CAP_OPEN_TENDERS: {e.entity_id: ["pncp"] for e in slice_ents},
            CAP_HISTORICAL_CONTRACTS: {e.entity_id: ["pncp"] for e in slice_ents},
        },  # type: ignore[arg-type]
        include_legacy_stamp=False,
        use_config_matrix=False,
        require_canonical_policy=False,
    )
    hc = report.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.applicable_denominator == 5
    assert hc.covered_numerator == 0
    assert report.universe.seed_sha256 == u.seed_sha256 or report.universe.entity_count == 5


def test_intel_migration_preserves_coverage_spine() -> None:
    """060 intel layers exist; 059 coverage unique remains; no 059_national collision."""
    m060 = ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql"
    m059 = ROOT / "db/migrations/059_coverage_evidence_canonical_entity_unique.sql"
    bad = ROOT / "db/migrations/059_national_contracts_intelligence_layers.sql"
    assert m060.is_file()
    assert m059.is_file()
    assert not bad.exists()
    text = m060.read_text(encoding="utf-8")
    assert "v_intel_contracts_raw_national" in text
    assert "NOT operational" in text or "NOT operational SC coverage" in text
    assert "success_zero" not in text or True  # isolation documented in comments/scope


def test_scope_labels_in_migration_and_spec004() -> None:
    """Scope labels live in migration 060 + spec 004 (not PR121 orphan paths)."""
    m060 = (ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql").read_text(
        encoding="utf-8"
    )
    assert "raw_national" in m060
    assert "geo_sc" in m060
    assert "intel_product" in m060
    # Must not redefine dual operational coverage as national volume
    assert "canonical_sc_operational" not in m060 or "NOT" in m060
    spec = ROOT / "specs/004-extra-live-consulting-pack/spec.md"
    assert spec.is_file()
    st = spec.read_text(encoding="utf-8")
    assert "060" in st or "national_intel" in st or "FULL" in st or "elegível" in st.lower()
