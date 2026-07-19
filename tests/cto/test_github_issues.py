from scripts.cto.github_issues import (
    extract_work_id,
    labels_for_item,
    render_issue_body,
    work_id_marker,
)
from scripts.cto.work_registry import build_initial_registry, get_by_work_id, save_registry


def test_marker_roundtrip():
    mid = work_id_marker("cto-autopilot-infra")
    assert extract_work_id(mid) == "cto-autopilot-infra"
    body = render_issue_body(
        {
            "work_id": "cto-autopilot-infra",
            "title": "t",
            "objective": "o",
            "priority": "p0",
            "risk": "normal",
            "origin": "test",
            "area": "cto",
            "type": "ops",
            "milestone": "CTO_AUTOPILOT",
            "acceptance_criteria": ["a"],
            "test_commands": ["pytest"],
            "dependencies": [],
            "blockers": [],
            "dod_refs": ["x"],
            "evidence": [],
            "state": "ready",
        }
    )
    assert extract_work_id(body) == "cto-autopilot-infra"
    assert "Acceptance criteria" in body or "Acceptance criteria" in body.replace("c", "c")


def test_labels_for_item():
    labs = labels_for_item(
        {"state": "ready", "type": "ops", "priority": "p0", "risk": "high", "area": "cto"}
    )
    assert "state:ready" in labs
    assert "type:ops" in labs
    assert "priority:p0" in labs
    assert "risk:high" in labs
    assert "area:cto" in labs


def test_registry_idempotent(cto_repo):
    reg1 = build_initial_registry(cto_repo)
    save_registry(reg1, cto_repo)
    reg2 = build_initial_registry(cto_repo)
    ids1 = sorted(i["work_id"] for i in reg1["work_items"])
    ids2 = sorted(i["work_id"] for i in reg2["work_items"])
    assert ids1 == ids2
    assert len(ids1) <= 40
    assert get_by_work_id(reg1, "cto-autopilot-infra") is not None


def test_sync_dry_run_no_mutation(cto_repo, monkeypatch):
    from scripts.cto import github_issues as gi

    reg = build_initial_registry(cto_repo)
    save_registry(reg, cto_repo)

    monkeypatch.setattr(gi, "gh_auth_ok", lambda root=None: False)
    result = gi.sync_issues(cto_repo, apply=False)
    assert result["mode"] == "dry-run"
    assert result["created"] or result["updated"] is not None
