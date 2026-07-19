"""Issue readiness: deps/blockers block ready; PR#48 items reconciled."""
from __future__ import annotations

from scripts.cto.work_registry import (
    IMPLEMENTED_IN_PR48,
    apply_readiness_gates,
    readiness_for_item,
    reconcile_implemented_items,
)


def test_blockers_prevent_ready():
    item = {
        "work_id": "x",
        "state": "ready",
        "blockers": ["External network dependency"],
        "dependencies": [],
    }
    info = readiness_for_item(item, {"work_items": [item]})
    assert info["ready"] is False
    assert any("blockers" in r for r in info["reasons"])


def test_open_dependencies_prevent_ready():
    dep = {"work_id": "dep-a", "state": "ready", "blockers": [], "dependencies": []}
    item = {
        "work_id": "child",
        "state": "ready",
        "blockers": [],
        "dependencies": ["dep-a"],
    }
    reg = {"work_items": [dep, item]}
    info = readiness_for_item(item, reg)
    assert info["ready"] is False
    assert any("dependencies" in r for r in info["reasons"])


def test_done_dependency_allows_ready():
    dep = {"work_id": "dep-a", "state": "done", "blockers": [], "dependencies": []}
    item = {
        "work_id": "child",
        "state": "ready",
        "blockers": [],
        "dependencies": ["dep-a"],
    }
    reg = {"work_items": [dep, item]}
    info = readiness_for_item(item, reg)
    assert info["ready"] is True


def test_pr48_items_not_ready():
    for wid in IMPLEMENTED_IN_PR48:
        item = {
            "work_id": wid,
            "state": "ready",
            "blockers": [],
            "dependencies": [],
            "issue_number": 30 if wid == "cto-autopilot-infra" else None,
        }
        info = readiness_for_item(item, {"work_items": [item]})
        assert info["ready"] is False, wid
        assert any("PR #48" in r or "implemented" in r for r in info["reasons"])


def test_reconcile_moves_without_auto_close():
    reg = {
        "work_items": [
            {
                "work_id": "cto-autopilot-infra",
                "state": "ready",
                "issue_number": 30,
                "blockers": [],
                "dependencies": [],
                "evidence": [],
            },
            {
                "work_id": "stabilize-open-pr-ci",
                "state": "ready",
                "issue_number": 31,
                "blockers": ["May require human merge decision"],
                "dependencies": [],
            },
        ]
    }
    moved = reconcile_implemented_items(reg, evidence=["PR #48 evidence"])
    assert moved["auto_closed"] is False
    assert moved["count"] >= 1
    infra = next(i for i in reg["work_items"] if i["work_id"] == "cto-autopilot-infra")
    assert infra["state"] == "review"
    assert any("PR #48" in e for e in infra["evidence"])
    # other item not in IMPLEMENTED set remains (until readiness gate)
    gates = apply_readiness_gates(reg)
    assert gates["count"] >= 1
    other = next(i for i in reg["work_items"] if i["work_id"] == "stabilize-open-pr-ci")
    assert other["state"] != "ready"
