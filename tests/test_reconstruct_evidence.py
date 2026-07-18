"""DoD §29 — evidence reconstruction recipes are executable maps."""
from __future__ import annotations

from scripts.ops.reconstruct_evidence import (
    EVIDENCE_KINDS,
    recipe_for,
    reconstruct_plan,
)


def test_all_kinds_have_recipes() -> None:
    for kind in EVIDENCE_KINDS:
        r = recipe_for(kind)
        assert r.reconstructible is True
        assert r.command


def test_reconstruct_plan_ok() -> None:
    plan = reconstruct_plan()
    assert plan["ok"] is True
    assert len(plan["items"]) == len(EVIDENCE_KINDS)


def test_cli_exit_zero() -> None:
    from scripts.ops.reconstruct_evidence import main

    assert main(["--json"]) == 0
