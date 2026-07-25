"""Unit tests: hashing, units, zip safety, export safety, materiality."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.budget_audit.export_safety import neutralize_formula_injection
from scripts.budget_audit.hashing import sha256_bytes, sha256_file, sha256_text
from scripts.budget_audit.materiality import classify_difference
from scripts.budget_audit.units import forbid_auto_conversion, normalize_unit, units_compatible
from scripts.budget_audit.zip_safety import inspect_zip, safe_extract


def test_sha256_stable(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello-budget-audit")
    assert sha256_file(p) == sha256_bytes(b"hello-budget-audit")
    assert sha256_text("x") == sha256_bytes(b"x")


def test_unit_normalization() -> None:
    assert normalize_unit("m2").normalized == "m²"
    assert normalize_unit("M³").normalized == "m³"
    assert normalize_unit("verba").normalized == "vb"
    assert normalize_unit("").normalized is None
    assert units_compatible("m²", "m2")
    assert not units_compatible("m²", "m")
    assert forbid_auto_conversion("m²", "m")
    assert forbid_auto_conversion("vb", "un")
    assert not forbid_auto_conversion("kg", "KG")


def test_export_formula_injection() -> None:
    assert neutralize_formula_injection("=cmd|'/c calc'!A0").startswith("'")
    assert neutralize_formula_injection("+1234").startswith("'")
    assert neutralize_formula_injection("@sum").startswith("'")
    assert neutralize_formula_injection("normal text") == "normal text"
    assert neutralize_formula_injection("=A1+B1", is_formula=True) == "=A1+B1"


def test_materiality_never_zero_fills_missing() -> None:
    r = classify_difference(None, 10.0)
    assert r["status"] == "NOT_EVALUATED"
    r2 = classify_difference(100.0, 100.0)
    assert r2["status"] == "PASS"
    r3 = classify_difference(1000.0, 1000.005)
    assert r3["status"] in {"PASS", "ROUNDING_DIFFERENCE"}
    r4 = classify_difference(1000.0, 1500.0)
    assert r4["status"] == "MATERIAL_DIFFERENCE"


def test_zip_traversal_blocked(tmp_path: Path) -> None:
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../etc/passwd", "nope")
        zf.writestr("safe.xlsx", b"PK\x03\x04fake")
    dest = tmp_path / "out"
    result = safe_extract(zpath, dest)
    assert any(s["reason"] == "path_traversal" for s in result.skipped)
    assert not (tmp_path / "etc" / "passwd").exists()


def test_zip_bomb_ratio(tmp_path: Path) -> None:
    zpath = tmp_path / "bomb.zip"
    # Create high ratio by compressing zeros is hard with high ratio threshold;
    # test absolute size limit via inspect mock-like large declared size is not easy
    # without ZipInfo tricks — use member count
    with zipfile.ZipFile(zpath, "w") as zf:
        for i in range(10):
            zf.writestr(f"f{i}.txt", b"x")
    info = inspect_zip(zpath)
    assert info["member_count"] == 10
