"""Observer provides full decision context, not IDs/titles alone."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.cto.observer import _summarize_checks, ranking_freshness
from scripts.cto.work_registry import build_initial_registry, save_registry, work_item_public_view


def test_summarize_checks_failed_jobs():
    rollup = [
        {
            "name": "Lint (ruff)",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "detailsUrl": "https://example/1",
            "workflowName": "CI",
        },
        {
            "name": "Type Check",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
    ]
    s = _summarize_checks(rollup)
    assert s["overall"] == "FAILURE"
    assert "Lint (ruff)" in s["failed_job_names"]
    assert s["failed_jobs"]


def test_work_item_public_view_has_full_fields():
    item = {
        "work_id": "w1",
        "title": "t",
        "objective": "obj",
        "priority": "p0",
        "risk": "high",
        "state": "ready",
        "acceptance_criteria": ["a"],
        "allowed_paths": ["scripts/**"],
        "test_commands": ["pytest"],
        "dependencies": ["x"],
        "blockers": ["b"],
        "evidence": ["e"],
    }
    view = work_item_public_view(item)
    for key in (
        "objective",
        "priority",
        "risk",
        "state",
        "acceptance_criteria",
        "allowed_paths",
        "test_commands",
        "dependencies",
        "blockers",
        "evidence",
    ):
        assert key in view
        assert view[key] is not None


def test_ranking_freshness_missing(tmp_path: Path):
    info = ranking_freshness(tmp_path)
    assert info["stale"] is True
    assert info["available"] is False


def test_ranking_freshness_fresh_file(tmp_path: Path):
    p = tmp_path / "squads" / "extra-dod-roi" / "state" / "rankings"
    p.mkdir(parents=True)
    latest = p / "latest.json"
    latest.write_text(
        json.dumps({"generated_at": "2099-01-01T00:00:00Z", "ranking": [], "selected_id": None}),
        encoding="utf-8",
    )
    # mtime is now; generated_at far future → age negative → not stale
    info = ranking_freshness(tmp_path, max_age_seconds=3600)
    assert info["available"] is True


def test_observe_includes_extended_keys(cto_repo):
    from scripts.cto.observer import observe

    reg = build_initial_registry(cto_repo)
    save_registry(reg, cto_repo)
    with patch("scripts.cto.observer._gh_prs", return_value=[]), patch(
        "scripts.cto.observer._gh_issues_summary",
        return_value={"available": False, "open_count": 0, "items": [], "by_state": {}},
    ):
        obs = observe(cto_repo, write=True)
    assert "work_items" in obs
    assert "active_cycles" in obs
    assert "recent_tests" in obs
    assert "ops_freshness" in obs
    assert "divergences" in obs
    assert "ranking" in obs
    # work_items should carry full fields when present
    items = (obs.get("work_items") or {}).get("items") or []
    if items:
        assert "objective" in items[0] or "acceptance_criteria" in items[0]
