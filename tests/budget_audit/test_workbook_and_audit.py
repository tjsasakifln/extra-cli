"""Workbook reading, arithmetic, BDI, compositions, findings."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.budget_audit.arithmetic import audit_item_arithmetic, workbook_integrity
from scripts.budget_audit.bdi import _as_fraction, audit_bdi
from scripts.budget_audit.classify import classify_workbook
from scripts.budget_audit.compositions import audit_compositions
from scripts.budget_audit.findings import build_findings
from scripts.budget_audit.normalize import normalize_case
from scripts.budget_audit.workbook_reader import classify_formula, read_workbook
from tests.budget_audit.build_fixtures import build_golden


@pytest.fixture(scope="module")
def golden_path(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("fix") / "golden.xlsx"
    return build_golden(p)


def test_read_formulas_and_cached_separate(golden_path: Path) -> None:
    model = read_workbook(golden_path, document_id="golden")
    assert model["extraction_quality"]["macros_executed"] is False
    assert model["extraction_quality"]["calculation_mode"] == "NOT_RECALCULATED"
    assert model["extraction_quality"]["cell_count"] > 20
    formulas = model["formulas"]
    assert any(f.get("formula_status") == "BROKEN_REFERENCE" for f in formulas)
    # missing cache not coerced to zero
    for f in formulas:
        if f.get("formula_status") == "MISSING_CACHE":
            assert f.get("cached_value") is None


def test_classify_formula_statuses() -> None:
    assert classify_formula("=A1", 10) == "VALID"
    assert classify_formula("=A1", None) == "MISSING_CACHE"
    assert classify_formula("=#REF!", None) == "BROKEN_REFERENCE"
    assert classify_formula("='[ext.xlsx]S'!A1", 1) == "EXTERNAL_REFERENCE"


def test_bdi_scale_interpretation() -> None:
    f1, r1 = _as_fraction(0.25)
    assert abs(f1 - 0.25) < 1e-9
    assert "fraction" in r1
    f2, r2 = _as_fraction(25)
    assert abs(f2 - 0.25) < 1e-9
    assert "percent_points" in r2
    # never 25 -> 25.0 fraction (2500%)
    assert f2 < 1.0
    # Component rows: 0.97 means 0.97% (percent points), not 97%
    f3, r3 = _as_fraction(0.97, role="component")
    assert abs(f3 - 0.0097) < 1e-9
    assert "component" in r3
    # Excel percent format already a fraction
    f4, r4 = _as_fraction(0.2882, number_format="0.00%", role="component")
    assert abs(f4 - 0.2882) < 1e-9
    assert "excel_percent" in r4


def test_map_columns_valor_unit_com_bdi_not_bdi_pct() -> None:
    from scripts.budget_audit.normalize import map_columns

    headers = [
        "Item",
        "Código",
        "Descrição",
        "Und",
        "Quant.",
        "Valor Unit",
        "Valor Unit com BDI",
        "Total",
    ]
    m = map_columns(headers)
    assert m["unit_direct_cost"] == 5  # Valor Unit
    assert m["unit_sale_price"] == 6  # Valor Unit com BDI
    assert m["bdi_pct"] is None
    assert m["quantity"] == 4
    assert m["total_sale_price"] == 7


def test_golden_detects_material_and_double_bdi(golden_path: Path) -> None:
    model = read_workbook(golden_path, document_id="golden")
    classifications = classify_workbook(model)
    types = {c["classification"] for c in classifications}
    assert "BUDGET_ANALYTICAL" in types or "UNKNOWN" not in types or len(types) >= 3
    norm = normalize_case("golden", classifications, model["cells"])
    items = norm["budget_items"]
    assert len(items) >= 5

    arith = audit_item_arithmetic(items)
    assert arith["check_count"] >= 5
    assert any(c["status"] == "MATERIAL_DIFFERENCE" for c in arith["checks"])

    integrity = workbook_integrity(model["formulas"], model["cells"], items, model["hidden_content"])
    assert integrity["issue_count"] >= 1

    bdi = audit_bdi(norm["bdi_components"], items)
    assert bdi["component_count"] >= 5
    # duplicate component or double bdi
    kinds = {i.get("kind") for i in bdi["issues"]}
    assert "DUPLICATE_COMPONENT" in kinds or "POSSIBLE_DOUBLE_BDI" in kinds

    comp = audit_compositions(norm["compositions"], norm["composition_inputs"], items)
    assert comp["issue_count"] >= 1

    findings = build_findings(
        arithmetic=arith,
        integrity=integrity,
        compositions=comp,
        bdi=bdi,
        document_id="golden",
    )
    assert findings["finding_count"] >= 5
    # every finding with cells is list
    for f in findings["findings"]:
        assert isinstance(f.get("cells"), list)


def test_percent_25_vs_0_25_not_confused() -> None:
    # item with bdi 25 (percent points) vs 0.25 (fraction) should both mean 25%
    items = [
        {
            "item_id": "a",
            "quantity": 1,
            "unit_direct_cost": 100,
            "bdi_pct": 25,
            "unit_sale_price": 125,
            "total_sale_price": 125,
            "source_cells": {},
        },
        {
            "item_id": "b",
            "quantity": 1,
            "unit_direct_cost": 100,
            "bdi_pct": 0.25,
            "unit_sale_price": 125,
            "total_sale_price": 125,
            "source_cells": {},
        },
    ]
    arith = audit_item_arithmetic(items)
    bdi_checks = [c for c in arith["checks"] if "bdi" in c["check_id"]]
    assert len(bdi_checks) == 2
    assert all(c["status"] == "PASS" for c in bdi_checks)
