"""Tests for pytest skip policy gate."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.check_pytest_skip_policy import main, scan_file


def test_scan_detects_module_level_importorskip(tmp_path: Path) -> None:
    p = tmp_path / "test_x.py"
    p.write_text(
        "import pytest\npytest.importorskip('hypothesis')\n\ndef test_a():\n    assert True\n",
        encoding="utf-8",
    )
    hits = scan_file(p)
    assert hits and hits[0]["reason"] == "module_level_pytest_skip"


def test_scan_ignores_function_level_skip(tmp_path: Path) -> None:
    p = tmp_path / "test_y.py"
    p.write_text(
        "import pytest\n\ndef test_a():\n    pytest.skip('local')\n    assert False\n",
        encoding="utf-8",
    )
    assert scan_file(p) == []


def test_main_passes_on_current_tests() -> None:
    # budget adversarial no longer has module-level importorskip
    assert main(["--root", "tests"]) == 0
