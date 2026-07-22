"""Canonical source policy authority + combination selection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.coverage.source_policy import (
    compute_policy_sha256,
    derive_esfera,
    entity_attributes_from_canonical,
    fallback_policy_stub,
    load_source_policy,
    select_required_combination,
)
from scripts.lib.universe import CanonicalEntity


def _ent(
    eid: str,
    *,
    name: str = "X",
    natureza: str = "Município",
    municipio: str = "FLORIANOPOLIS",
    cnpj8: str = "12345678",
) -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=1,
        razao_social=name,
        cnpj8=cnpj8,
        municipio=municipio,
        codigo_ibge="4205407",
        natureza_juridica=natureza,
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="test",
        identity_key=f"{cnpj8}|{municipio}|{name}",
    )


def test_active_policy_loads_with_verified_hash() -> None:
    pol = load_source_policy(require_active=True)
    assert pol.ready is True
    assert pol.status == "active"
    assert pol.policy_sha256
    assert compute_policy_sha256(Path(pol.path)) == pol.policy_sha256
    assert not pol.errors


def test_hash_mismatch_fails_active() -> None:
    pol = load_source_policy(require_active=True, expected_sha256="0" * 64)
    assert pol.ready is False
    assert any("expected_sha256_mismatch" in e for e in pol.errors)


def test_municipal_requires_pncp_plus_ciga() -> None:
    pol = load_source_policy(require_active=True)
    attrs = entity_attributes_from_canonical(
        _ent("m1", natureza="Município"), entity_type="prefeitura"
    )
    assert attrs.esfera == "municipal"
    sel = select_required_combination(pol, "open_tenders", attrs, validated_at="t")
    assert sel["selected_combination"] == ["pncp", "ciga_ckan"]
    assert sel["entity_capability_status"] == "applicable"


def test_federal_requires_pncp_only() -> None:
    pol = load_source_policy(require_active=True)
    attrs = entity_attributes_from_canonical(
        _ent("f1", natureza="Órgão Público do Poder Executivo Federal"),
        entity_type="orgao_federal",
    )
    assert attrs.esfera == "federal"
    sel = select_required_combination(pol, "open_tenders", attrs, validated_at="t")
    assert sel["selected_combination"] == ["pncp"]


def test_estadual_and_autarquia_and_camara() -> None:
    pol = load_source_policy(require_active=True)
    for natureza, et, esfera in [
        ("Órgão Público do Poder Executivo Estadual", "orgao_estadual", "estadual"),
        ("Autarquia Municipal", "autarquia_municipal", "municipal"),
        ("Câmara Municipal", "camara_municipal", "municipal"),
    ]:
        attrs = entity_attributes_from_canonical(_ent("x", natureza=natureza), entity_type=et)
        assert attrs.esfera == esfera, (natureza, attrs.esfera, attrs.source_of_esfera)
        sel = select_required_combination(pol, "open_tenders", attrs, validated_at="t")
        assert sel["entity_capability_status"] == "applicable"
        assert sel["selected_combination"]


def test_esfera_absent_unknown() -> None:
    esfera, src = derive_esfera(natureza_juridica=None, entity_type=None)
    assert esfera is None
    assert "absent" in src or src == "attribute_absent"
    pol = load_source_policy(require_active=True)
    # natureza/entity_type insufficient to derive esfera → unknown
    attrs2 = entity_attributes_from_canonical(
        _ent("u2", natureza="Entidade Sem Esfera Clara"), entity_type="unknown_type"
    )
    sel = select_required_combination(pol, "open_tenders", attrs2, validated_at="t")
    if attrs2.esfera is None:
        assert sel["entity_capability_status"] in {"unknown", "NOT_READY"}


def test_override_requires_justification() -> None:
    esfera, src = derive_esfera(override="federal", override_justification="")
    assert esfera is None
    assert src == "override_missing_justification"
    esfera2, src2 = derive_esfera(override="federal", override_justification="manual audit")
    assert esfera2 == "federal"
    assert src2 == "override"


def test_fallback_non_canonical() -> None:
    stub = fallback_policy_stub()
    assert stub.canonical is False
    assert stub.fallback_used is True
    attrs = entity_attributes_from_canonical(_ent("m"), entity_type="prefeitura")
    sel = select_required_combination(stub, "open_tenders", attrs, validated_at="t")
    assert sel["entity_capability_status"] == "NOT_READY"
    assert sel["fallback_used"] is True


def test_pncp_alone_does_not_satisfy_municipal_policy() -> None:
    pol = load_source_policy(require_active=True)
    attrs = entity_attributes_from_canonical(
        _ent("m", natureza="Município"), entity_type="prefeitura"
    )
    sel = select_required_combination(pol, "open_tenders", attrs, validated_at="t")
    assert sel["selected_combination"] != ["pncp"]
    assert "ciga_ckan" in (sel["selected_combination"] or [])


def test_historical_requires_pncp_contracts() -> None:
    pol = load_source_policy(require_active=True)
    attrs = entity_attributes_from_canonical(
        _ent("m", natureza="Município"), entity_type="prefeitura"
    )
    sel = select_required_combination(pol, "historical_contracts", attrs, validated_at="t")
    assert sel["selected_combination"] == ["pncp", "contracts"]


def test_min_source_matches_policy() -> None:
    from scripts.coverage.applicability_matrix import MANDATORY_SOURCES, MIN_SOURCE_COMBINATION
    from scripts.coverage.dual_capability_coverage import (
        DEFAULT_REQUIRED_SOURCES,
        resolve_required_sources,
    )

    assert MIN_SOURCE_COMBINATION["open_tenders"] == ["pncp", "ciga_ckan"]
    # Full combination — never first-source-only reduction
    assert MANDATORY_SOURCES["open_tenders"] == ["pncp", "ciga_ckan"]
    assert MANDATORY_SOURCES["historical_contracts"] == ["pncp", "contracts"]
    # Default stub remains non-canonical and must diverge intentionally
    assert DEFAULT_REQUIRED_SOURCES["open_tenders"] == ("pncp",)
    assert list(DEFAULT_REQUIRED_SOURCES["open_tenders"]) != MIN_SOURCE_COMBINATION["open_tenders"]
    # allow_fallback=False without policy → empty (never silent pncp)
    assert resolve_required_sources("open_tenders", allow_fallback=False) == []
    # allow_fallback=True is explicit non-canonical only
    assert resolve_required_sources("open_tenders", allow_fallback=True) == ["pncp"]


def test_compute_dual_rejects_missing_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.coverage.dual_capability_coverage import CAP_OPEN_TENDERS, compute_dual_coverage
    from scripts.lib.universe import CanonicalUniverse

    u = CanonicalUniverse(
        seed_path="x",
        seed_sha256="a" * 64,
        radius_km=200.0,
        entities=[_ent("e1")],
    )
    missing = tmp_path / "no-policy.yaml"
    monkeypatch.setattr(
        "scripts.coverage.source_policy.DEFAULT_POLICY_PATH",
        missing,
    )
    # force load from project path that does not exist via require
    report = compute_dual_coverage(
        universe=u,
        observations_by_cap={CAP_OPEN_TENDERS: {}},
        presence_by_cap={CAP_OPEN_TENDERS: set()},
        capabilities=[CAP_OPEN_TENDERS],
        use_config_matrix=True,
        require_canonical_policy=True,
        source_policy=load_source_policy(missing, require_active=True),
    )
    assert report.measurement_success is False
    assert report.dual_gate_status == "NOT_READY"
    assert "SOURCE_POLICY_NOT_READY" in (report.error or "")
