"""Purity and import-boundary contract of scripts/confenge_claim_policy (AC 19, 23, 23a, 30)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "scripts" / "confenge_claim_policy"

FORBIDDEN_IMPORT_ROOTS = (
    "scripts.confenge_account_intelligence",
    "scripts.confenge_contact_resolution",
)

FORBIDDEN_CALLS = {
    "open",
    "input",
    "exec",
    "eval",
}

FORBIDDEN_ATTR_CALLS = {
    ("date", "today"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("os", "getenv"),
    ("time", "time"),
}

FORBIDDEN_MODULES = {"os", "socket", "requests", "httpx", "urllib", "psycopg", "psycopg2", "subprocess"}


def _module_files() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def _iter_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_ac23a_no_import_of_integration_packages(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _iter_imports(tree):
        for root in FORBIDDEN_IMPORT_ROOTS:
            assert not name.startswith(root), f"{path.name} imports {name} — circular boundary violated"


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: p.name)
def test_ac19_no_io_or_wall_clock_in_pure_module(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _iter_imports(tree):
        assert name.split(".")[0] not in FORBIDDEN_MODULES, f"{path.name} imports I/O module {name}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            assert func.id not in FORBIDDEN_CALLS, f"{path.name} calls {func.id}()"
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            pair = (func.value.id, func.attr)
            assert pair not in FORBIDDEN_ATTR_CALLS, f"{path.name} calls {pair[0]}.{pair[1]}()"


def test_the_only_allowed_local_dependency_is_contracts_truth() -> None:
    local: set[str] = set()
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _iter_imports(tree):
            if name.startswith("scripts."):
                local.add(name)
    assert local <= {"scripts.contracts_truth", "scripts.confenge_claim_policy.policy"}, local


def test_ac23_extract_contract_hook_default_is_backward_compatible() -> None:
    """Calling without ``purpose`` must reproduce the pre-story behaviour."""
    import inspect

    from scripts.confenge_account_intelligence.message_spine import extract_contract_hook

    sig = inspect.signature(extract_contract_hook)
    purpose = sig.parameters["purpose"]
    assert purpose.kind is inspect.Parameter.KEYWORD_ONLY
    assert purpose.default == "why_you"

    bag = {
        "contracts": [
            {
                "id": "C-1",
                "object": "Execução de obra de pavimentação asfáltica em CBUQ nas vias urbanas do município",
                "orgao": "Prefeitura de Coxilha",
                "uf": "RS",
                "value_brl": 1_200_000,
                "start_date": "2019-01-01",
                "end_date": "2020-01-01",
            }
        ]
    }
    # Historical contract: default (why_you) still returns it, why_now does not.
    assert extract_contract_hook(bag) == extract_contract_hook(bag, purpose="why_you")
    hook, ids = extract_contract_hook(bag)
    assert "objeto: Execução de obra" in hook
    assert ids == ["cf-contract-C-1"]
    assert extract_contract_hook(bag, purpose="why_now") == ("", [])
