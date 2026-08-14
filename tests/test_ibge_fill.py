"""Tests for #301 IBGE fill of the 19 included Florianópolis rows."""

from __future__ import annotations

import pytest

from scripts.lib.universe import normalize_codigo_ibge
from scripts.universe.ibge_fill import (
    FLORIANOPOLIS_IBGE,
    IbgeFillError,
    UniverseIbgeRow,
    apply_ibge_fill,
    catalog_hash,
    list_missing_included,
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
    rows = rows_from_canonical_universe()
    included = [r for r in rows if r.included]
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
    # State-level rows with UF-only "42" stay untouched (not among the 19).
    state_missing = [r for r in missing if r.municipio.upper() == "SANTA CATARINA"]
    assert state_missing
    state_keys = {r.canonical_entity_key for r in state_missing}
    after_by_key = {r.canonical_entity_key: r for r in enriched}
    for key in list(state_keys)[:3]:
        assert after_by_key[key].codigo_ibge == next(r.codigo_ibge for r in included if r.canonical_entity_key == key)
