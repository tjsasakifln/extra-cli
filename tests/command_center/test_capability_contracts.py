"""Contract tests: every capability builds a real argv against current CLIs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.command_center.capabilities.definitions import all_capabilities
from scripts.command_center.security import assert_argv_list


def _sample_params(cap) -> dict:
    params: dict = {}
    for p in cap.params:
        if p.default is not None:
            params[p.name] = p.default
        elif p.required or p.example:
            if p.type == "int":
                params[p.name] = 1
            elif p.type == "bool":
                params[p.name] = False
            elif p.type == "select" and p.choices:
                params[p.name] = p.choices[0]
            elif p.type == "path":
                params[p.name] = "output/sample"
            else:
                params[p.name] = p.example or "x"
    # commercial cycles need run_mode for stable contract
    if "run_mode" in {p.name for p in cap.params} and "run_mode" not in params:
        params["run_mode"] = "DRY_RUN"
    return params


@pytest.mark.parametrize("cap", all_capabilities(), ids=lambda c: c.id)
def test_capability_builds_safe_argv(cap) -> None:
    params = _sample_params(cap)
    argv = cap.argv_builder(params)
    cleaned = assert_argv_list(argv)
    assert cleaned
    assert all(isinstance(x, str) and x for x in cleaned)
    assert all("\x00" not in x for x in cleaned)
    # No shell wrapper
    joined = " ".join(cleaned)
    assert "&&" not in joined
    assert ";" not in cleaned  # whole tokens only; ; as part of string is rare


def test_commercial_suppliers_uses_canonical_router() -> None:
    caps = {c.id: c for c in all_capabilities()}
    cap = caps["confenge.suppliers.cycle.run"]
    argv = cap.argv_builder({"run_mode": "DRY_RUN"})
    assert "scripts.ops.confenge_commercial_target_router" in argv
    assert "--target" in argv
    assert "suppliers" in argv
    assert "--run-mode" in argv
    assert "DRY_RUN" in argv
    # Must NOT call frozen cycle directly (bypasses registry precheck path via router)
    assert "scripts.ops.confenge_commercial_cycle" not in argv


def test_commercial_public_agencies_uses_canonical_router() -> None:
    caps = {c.id: c for c in all_capabilities()}
    cap = caps["confenge.public_agencies.cycle.run"]
    argv = cap.argv_builder(
        {
            "run_mode": "DRY_RUN",
            "uf": "SC",
            "max_public_agency_leads": 15,
        }
    )
    assert "scripts.ops.confenge_commercial_target_router" in argv
    assert argv[argv.index("--target") + 1] == "public-agencies"
    assert "--uf" in argv
    assert "SC" in argv
    assert "--max-public-agency-leads" in argv
    assert "15" in argv
    assert "scripts.ops.deliverable_a_org_ranking" not in argv


def test_commercial_all_uses_canonical_router() -> None:
    caps = {c.id: c for c in all_capabilities()}
    cap = caps["confenge.all.cycle.run"]
    assert "confenge_commercial_target_router" in " ".join(cap.required_modules)
    argv = cap.argv_builder({"run_mode": "DRY_RUN"})
    assert "scripts.ops.confenge_commercial_target_router" in argv
    assert argv[argv.index("--target") + 1] == "all"
    assert "scripts.ops.confenge_combined_cycle" not in argv


def test_fixture_echo_is_python_c() -> None:
    caps = {c.id: c for c in all_capabilities()}
    argv = caps["cc.fixture.echo"].argv_builder({"message": "hello"})
    assert argv[0] == sys.executable
    assert argv[1] == "-c"
    assert "hello" in argv[2]


def test_weekly_cycle_argv_flags() -> None:
    caps = {c.id: c for c in all_capabilities()}
    argv = caps["extra.weekly.run"].argv_builder(
        {"strict": True, "skip_collect": True, "limit": 3, "output_dir": "output/weekly/x"}
    )
    assert "scripts.ops.weekly_cycle" in argv
    assert "--strict" in argv
    assert "--skip-collect" in argv
    assert "--limit" in argv
    assert "3" in argv
    assert "--output-dir" in argv


def test_registry_lookup_argv() -> None:
    caps = {c.id: c for c in all_capabilities()}
    argv = caps["confenge.suppliers.registry.lookup"].argv_builder({"cnpj": "12.345.678/0001-90"})
    assert "scripts.company_registry" in argv
    assert "lookup" in argv
    assert "12.345.678/0001-90" in argv


def test_dod_controller_path_exists() -> None:
    caps = {c.id: c for c in all_capabilities()}
    argv = caps["dod.status"].argv_builder({})
    path = Path(argv[0])
    assert path.name == "dod_controller.py"
    assert path.exists(), f"dod_controller missing at {path}"
