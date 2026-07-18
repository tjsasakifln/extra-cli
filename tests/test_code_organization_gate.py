"""Tests for DoD §27 code organization gate."""
from __future__ import annotations

from scripts.ops.code_organization_gate import (
    SNAKE_MODULE,
    check_module_names,
    run_gate,
)
from pathlib import Path


def test_snake_module_regex():
    assert SNAKE_MODULE.match("operational_outputs.py")
    assert not SNAKE_MODULE.match("Bad-Name.py")


def test_run_gate_structure():
    r = run_gate()
    assert "module_names" in r
    assert "sys_path" in r
    assert "except_exception_pass" in r
    assert "public_api_sample" in r
    assert "summary" in r
    assert r["n_py_files"] > 10


def test_critical_path_no_except_pass():
    r = run_gate()
    assert r["except_exception_pass"]["n_critical_path"] == 0
    assert r["except_exception_pass"]["ok"] is True
