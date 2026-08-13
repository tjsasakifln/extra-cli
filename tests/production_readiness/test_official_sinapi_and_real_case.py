"""Official SINAPI acquisition + real-case chain unit tests (no silent fixture-as-official)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.production_readiness.official_reference import load_official_manifest, match_items
from scripts.production_readiness.official_sinapi_acquire import (
    build_manifest,
    compare_budget_to_official,
    sidra_to_items,
)
from scripts.production_readiness.real_case_chain import run_chain


def test_sidra_to_items_maps_rows() -> None:
    rows = [
        {"NC": "header"},
        {"D3C": "202506", "D2N": "Índice nacional", "V": "100.5"},
        {"D3C": "202507", "D2N": "Índice nacional", "V": "101.0"},
    ]
    items = sidra_to_items(rows)
    assert len(items) == 2
    assert items[0]["code"].startswith("SINAPI-IDX-")
    assert items[0]["price"] == 100.5


def test_build_manifest_not_fixture(tmp_path: Path) -> None:
    items = [{"code": "SINAPI-IDX-1", "description": "idx", "unit": "índice", "price": 1.0}]
    m = build_manifest(
        out_dir=tmp_path,
        items=items,
        claim_level="OFFICIAL_SIDRA_INDEX",
        source_url="https://apisidra.ibge.gov.br/values/t/7060/n1/all/v/all/p/last%201",
        publisher="IBGE SIDRA",
        reference_month="2025-06",
        locality="BR",
        license_note="public",
    )
    assert m["is_fixture"] is False
    assert m["claim_level"] == "OFFICIAL_SIDRA_INDEX"
    assert (tmp_path / "manifest.json").is_file()
    loaded = load_official_manifest(tmp_path / "manifest.json")
    assert loaded["system"] == "SINAPI"


def test_compare_refuses_structure_only(tmp_path: Path) -> None:
    items = [{"code": "X", "description": "y", "unit": "m", "price": 1.0}]
    m = build_manifest(
        out_dir=tmp_path,
        items=items,
        claim_level="STRUCTURE_ONLY_NOT_OFFICIAL_ACQUISITION",
        source_url="https://example.invalid",
        publisher="demo",
        reference_month="2026-01",
        locality="SC",
        license_note="demo",
    )
    # force demo flags that matchers must refuse
    m["is_demo_structure"] = True
    with pytest.raises(ValueError, match="fixture|STRUCTURE|demo"):
        compare_budget_to_official([{"code": "X", "description": "y", "unit": "m"}], m)


def test_match_classes_on_official_items(tmp_path: Path) -> None:
    items = [
        {"code": "88389", "description": "Concreto fck 25 MPa", "unit": "m3", "price": 450.0},
        {"code": "99901", "description": "Tubo PVC 100mm", "unit": "m", "price": 35.0},
    ]
    m = build_manifest(
        out_dir=tmp_path,
        items=items,
        claim_level="OFFICIAL_COMPOSITION",
        source_url="https://apisidra.ibge.gov.br/example",
        publisher="test-official",
        reference_month="2026-06",
        locality="SC",
        license_note="test",
    )
    budget = [
        {"code": "88389", "description": "Concreto fck 25 MPa", "unit": "m3"},
        {"code": "99901", "description": "Tubo PVC 100mm", "unit": "un"},  # unit mismatch
        {"code": "00000", "description": "Item inexistente XYZ", "unit": "m"},
        {"code": None, "description": "concreto fck 25 mpa", "unit": "m3"},  # approximate by desc
    ]
    r = match_items(budget, m, budget_competence="2026-06", budget_locality="SC")
    assert r["is_official"] is True
    assert r["counts"]["exact"] >= 1
    assert r["counts"]["unit_incompatible"] >= 1
    assert r["counts"]["missing"] >= 1
    # competence mismatch run
    r2 = match_items(budget[:1], m, budget_competence="2020-01", budget_locality="SC")
    assert r2["counts"]["competence_incompatible"] >= 1


def test_real_case_chain_same_execution(tmp_path: Path) -> None:
    report = run_chain(tmp_path)
    assert report["same_execution"] is True
    assert report["execution_id"]
    assert report["ready_to_submit_auto"] is False
    assert (tmp_path / "real-case-analysis.json").is_file()
    names = [s["name"] for s in report["steps"]]
    assert names[:4] == ["edital_case", "budget_audit", "technical_acervo", "bid_readiness"]
