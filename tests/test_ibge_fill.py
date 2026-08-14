"""Tests for #301 IBGE fill of the 19 included Florianópolis rows."""

from __future__ import annotations

import pytest

from scripts.lib.universe import load_canonical_universe, normalize_codigo_ibge, resolve_default_seed_path
from scripts.universe.ibge_fill import (
    FLORIANOPOLIS_IBGE,
    IbgeFillError,
    UniverseIbgeRow,
    apply_ibge_fill,
    catalog_hash,
    list_missing_included,
    load_overlay,
    lookup_official_ibge,
    rows_from_canonical_universe,
)


def _row(**overrides: object) -> UniverseIbgeRow:
    base: dict[str, object] = {
        "canonical_entity_key": "k1",
        "cnpj": "82892282",
        "municipio": "FLORIANOPOLIS",
        "uf": "SC",
        "codigo_ibge": "",
        "distancia_km": 0.0,
        "radius_decision": "included",
        "included": True,
    }
    base.update(overrides)
    return UniverseIbgeRow(**base)  # type: ignore[arg-type]


def test_accents_normalize_to_official_florianopolis_code() -> None:
    assert lookup_official_ibge("Florianópolis", "SC") == FLORIANOPOLIS_IBGE
    assert lookup_official_ibge("FLORIANOPOLIS", "sc") == FLORIANOPOLIS_IBGE
    assert normalize_codigo_ibge(FLORIANOPOLIS_IBGE) == "4205407"


def test_homonym_without_uf_is_not_guessed() -> None:
    with pytest.raises(IbgeFillError, match="ambiguous_municipio"):
        lookup_official_ibge("São José", "")
    assert lookup_official_ibge("São José", "SC") == "4216602"
    assert lookup_official_ibge("Sao Jose", "SP") == "3549904"


def test_invalid_code_rejected() -> None:
    assert normalize_codigo_ibge("42") == ""
    assert normalize_codigo_ibge("420540") == ""
    assert normalize_codigo_ibge("42054070") == ""


def test_fill_writes_only_ibge_and_preserves_1093_identity() -> None:
    included = [_row(canonical_entity_key=f"k{i}", cnpj=f"{i:08d}") for i in range(19)]
    already = [
        _row(
            canonical_entity_key="kept",
            cnpj="11111111",
            municipio="BLUMENAU",
            codigo_ibge="4202404",
            distancia_km=12.5,
        )
    ]
    padding = [
        _row(
            canonical_entity_key=f"p{i}",
            cnpj=f"{i+100:08d}",
            municipio="JOINVILLE",
            codigo_ibge="4209102",
            distancia_km=float(i),
        )
        for i in range(1073)
    ]
    rows = tuple(included + already + padding)
    assert sum(1 for r in rows if r.included) == 1093
    enriched, report = apply_ibge_fill(rows)
    assert report.included_before == report.included_after == 1093
    assert len(report.filled) == 19
    assert {f.codigo_ibge for f in report.filled} == {FLORIANOPOLIS_IBGE}
    assert all(f.source == "IBGE-DTB-municipios" for f in report.filled)
    assert report.catalog_hash == catalog_hash()
    before = {r.identity_tuple() for r in rows}
    after = {r.identity_tuple() for r in enriched}
    assert before == after
    filled_keys = {f.canonical_entity_key for f in report.filled}
    for row in enriched:
        if row.canonical_entity_key in filled_keys:
            assert row.codigo_ibge == FLORIANOPOLIS_IBGE


def test_seed_has_exactly_19_included_missing_and_fills_florianopolis() -> None:
    raw = rows_from_canonical_universe(apply_overlay=False)
    included = [r for r in raw if r.included]
    assert len(included) == 1093
    missing = list_missing_included(tuple(included))
    municipal = [r for r in missing if r.municipio.upper() != "SANTA CATARINA"]
    assert len(municipal) == 19
    assert {r.municipio.upper() for r in municipal} == {"FLORIANOPOLIS"}
    enriched, report = apply_ibge_fill(tuple(included), only_municipio="FLORIANOPOLIS")
    assert len(report.filled) == 19
    assert report.included_before == 1093
    assert {f.codigo_ibge for f in report.filled} == {FLORIANOPOLIS_IBGE}
    assert {r.identity_tuple() for r in included} == {r.identity_tuple() for r in enriched}


def test_product_load_persists_19_florianopolis_codes() -> None:
    """The universe the product loads must show the 19 fills, not the raw seed gap."""
    seed = resolve_default_seed_path()
    before = load_canonical_universe(seed_path=seed, apply_ibge_overlay=False)
    after = load_canonical_universe(seed_path=seed)
    assert len(before.included) == len(after.included) == 1093
    overlay = load_overlay()
    assert len(overlay["fills"]) == 19
    assert {row["codigo_ibge"] for row in overlay["fills"]} == {FLORIANOPOLIS_IBGE}
    filled_cnpj = {row["cnpj8"] for row in overlay["fills"]}
    before_ids = {(e.entity_id, e.cnpj8, e.distancia_km, e.radius_decision, e.within_radius) for e in before.included}
    after_ids = {(e.entity_id, e.cnpj8, e.distancia_km, e.radius_decision, e.within_radius) for e in after.included}
    assert before_ids == after_ids
    loaded = [e for e in after.included if e.cnpj8 in filled_cnpj]
    assert len(loaded) == 19
    assert {e.codigo_ibge for e in loaded} == {FLORIANOPOLIS_IBGE}
    assert {e.municipio.upper() for e in loaded} == {"FLORIANOPOLIS"}
    raw_missing = [
        e
        for e in before.included
        if not normalize_codigo_ibge(e.codigo_ibge) and e.municipio.upper() != "SANTA CATARINA"
    ]
    assert len(raw_missing) == 19
    still_missing_municipal = [
        e
        for e in after.included
        if not normalize_codigo_ibge(e.codigo_ibge) and e.municipio.upper() != "SANTA CATARINA"
    ]
    assert still_missing_municipal == []
