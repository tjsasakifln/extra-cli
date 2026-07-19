"""Decide/run-once must not re-select PR#48-implemented work as ready."""
from __future__ import annotations

from scripts.cto.decision import decide_from_observation, enforce_executable_readiness
from scripts.cto.work_registry import (
    IMPLEMENTED_IN_PR48,
    apply_readiness_gates,
    build_initial_registry,
    reconcile_implemented_items,
    save_registry,
    upsert_item,
)


def test_enforce_rejects_implemented_issue_46(sample_decision):
    sample_decision["work_id"] = "publication-policy-docs"
    sample_decision["issue_number"] = 46
    sample_decision["decision"] = "EXECUTE"
    out = enforce_executable_readiness(sample_decision, root=None)
    # Without registry file, still rejects by IMPLEMENTED_IN_PR48 set
    assert out["decision"] == "NOOP"
    assert out["work_id"] is None
    assert "PR #48" in out["strategic_reason"] or "READINESS_GATE" in out["strategic_reason"]


def test_dry_decide_skips_implemented_registry(cto_repo):
    reg = build_initial_registry(cto_repo)
    reconcile_implemented_items(reg)
    apply_readiness_gates(reg)
    # Only one truly ready non-implemented item — demote all others
    for item in reg["work_items"]:
        if item["work_id"] == "freshness-coverage-sla":
            item["state"] = "ready"
            item["blockers"] = []
            item["dependencies"] = []
            item["issue_number"] = 34
            item["priority"] = "p0"
        elif str(item.get("state") or "").lower() == "ready":
            item["state"] = "blocked"
            item["blockers"] = ["test demote"]
        upsert_item(reg, item)
    save_registry(reg, cto_repo)

    from scripts.cto.config import load_config

    cfg = load_config(cto_repo)
    # Observation claims ready issues for implemented items — gate must ignore
    obs = {
        "cycle": {"cycle_id": "cyc-ready-gate"},
        "ranking": {"top": [], "stale": True},
        "issues": {
            "by_state": {
                "state:ready": [
                    {"number": 46, "work_id": "publication-policy-docs", "effective_state": "state:ready"},
                    {"number": 30, "work_id": "cto-autopilot-infra", "effective_state": "state:ready"},
                    {
                        "number": 34,
                        "work_id": "freshness-coverage-sla",
                        "effective_state": "state:ready",
                        "state_labels": ["state:ready"],
                    },
                ]
            },
            "items": [],
        },
        "work_registry": {"ids": list(IMPLEMENTED_IN_PR48) + ["freshness-coverage-sla"]},
    }
    decision = decide_from_observation(obs, config=cfg, dry_run=True, root=cto_repo)
    assert decision["decision"] in {"EXECUTE", "NOOP"}
    if decision["decision"] == "EXECUTE":
        assert decision["work_id"] not in IMPLEMENTED_IN_PR48
        assert decision["issue_number"] not in {30, 37, 38, 39, 43, 44, 46, 47}
        assert decision["work_id"] == "freshness-coverage-sla"
        assert decision["issue_number"] == 34


def test_dry_decide_noop_when_only_implemented(cto_repo):
    reg = build_initial_registry(cto_repo)
    reconcile_implemented_items(reg)
    apply_readiness_gates(reg)
    # All remaining ready items get blockers
    for item in reg["work_items"]:
        if item.get("state") == "ready":
            item["blockers"] = ["forced blocker for test"]
            upsert_item(reg, item)
    apply_readiness_gates(reg)
    save_registry(reg, cto_repo)

    from scripts.cto.config import load_config

    cfg = load_config(cto_repo)
    obs = {
        "cycle": {"cycle_id": "cyc-only-impl"},
        "ranking": {"top": []},
        "issues": {
            "by_state": {
                "state:ready": [
                    {"number": 47, "work_id": "budget-and-fallback", "state_labels": ["state:ready"]},
                ]
            },
            "items": [],
        },
        "work_registry": {"ids": ["budget-and-fallback"]},
    }
    decision = decide_from_observation(obs, config=cfg, dry_run=True, root=cto_repo)
    assert decision["decision"] == "NOOP"
    assert decision.get("work_id") in (None, "")


def test_set_state_label_used_on_sync(monkeypatch, cto_repo):
    """sync_issues --apply must call exclusive state label replace."""
    from scripts.cto import github_issues as gi
    from scripts.cto.work_registry import build_initial_registry, save_registry

    reg = build_initial_registry(cto_repo)
    for item in reg["work_items"]:
        if item["work_id"] == "cto-autopilot-infra":
            item["state"] = "review"
            item["issue_number"] = 30
    save_registry(reg, cto_repo)

    calls: list[tuple] = []

    def fake_set(root, num, state):
        calls.append((num, state))
        return {"ok": True, "state": state}

    monkeypatch.setattr(gi, "gh_auth_ok", lambda root=None: True)
    monkeypatch.setattr(
        gi,
        "list_managed_issues",
        lambda root=None: {
            "cto-autopilot-infra": {
                "number": 30,
                "title": "x",
                "state": "OPEN",
                "url": "u",
                "labels": ["state:ready"],
            }
        },
    )
    monkeypatch.setattr(gi, "_set_state_label", fake_set)
    monkeypatch.setattr(
        gi,
        "_run_gh",
        lambda args, cwd, timeout=90: {"exit_code": 0, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(gi, "ensure_labels", lambda *a, **k: [])
    monkeypatch.setattr(gi, "ensure_milestones", lambda *a, **k: [])

    out = gi.sync_issues(cto_repo, apply=True)
    assert out["mode"] == "apply"
    assert any(c[0] == 30 and c[1] == "state:review" for c in calls), calls
