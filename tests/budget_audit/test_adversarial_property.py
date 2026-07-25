"""Adversarial and property-based tests."""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.budget_audit.arithmetic import audit_item_arithmetic
from scripts.budget_audit.bdi import _as_fraction
from scripts.budget_audit.export_safety import neutralize_formula_injection
from scripts.budget_audit.workbook_reader import read_csv, read_workbook
from scripts.budget_audit.zip_safety import safe_extract


@given(
    qty=st.floats(min_value=0.001, max_value=1e5, allow_nan=False, allow_infinity=False),
    price=st.floats(min_value=0.001, max_value=1e5, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40)
def test_property_qty_times_price(qty: float, price: float) -> None:
    total = qty * price
    items = [
        {
            "item_id": "p",
            "quantity": qty,
            "unit_sale_price": price,
            "total_sale_price": total,
            "source_cells": {},
        }
    ]
    result = audit_item_arithmetic(items)
    assert result["checks"][0]["status"] in {"PASS", "ROUNDING_DIFFERENCE"}


@given(raw=st.sampled_from([0.25, 25, 0.1, 10, 1.0, 100]))
def test_property_bdi_fraction_bounds(raw: float) -> None:
    frac, _rule = _as_fraction(raw)
    assert 0 <= frac <= 1.0 or raw > 100  # only out-of-scale exceeds


def test_csv_formula_not_executed(tmp_path: Path) -> None:
    p = tmp_path / "evil.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["desc", "val"])
        w.writerow(["x", "=2+2"])
        w.writerow(["y", "10"])
    model = read_csv(p, document_id="csv1")
    # formula-like not evaluated to 4
    formula_cells = [c for c in model["cells"] if c.get("formula")]
    assert formula_cells
    assert formula_cells[0]["cached_value"] is None
    assert formula_cells[0]["formula_status"] == "MISSING_CACHE"


def test_corrupt_xlsx_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not-an-xlsx")
    with pytest.raises(Exception):
        read_workbook(p)


def test_csv_injection_neutralized() -> None:
    assert neutralize_formula_injection("=1+1").startswith("'")


def test_absolute_zip_member_skipped(tmp_path: Path) -> None:
    zpath = tmp_path / "abs.zip"
    # zipfile may normalize; write path with ..
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escape.txt", "x")
    res = safe_extract(zpath, tmp_path / "out")
    assert res.skipped or not (tmp_path / "escape.txt").exists()
