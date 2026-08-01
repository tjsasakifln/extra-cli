"""Unit tests for run comparison — shipped compare_manifests / compare_row_sets."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.command_center.run_compare import compare_manifests, compare_row_sets, find_previous_manifest
from scripts.command_center.workflows.runner import run_workflow


def test_compare_row_sets_added_removed_changed() -> None:
    prev = [
        {"id": "a", "score": 10, "name": "A"},
        {"id": "b", "score": 20, "name": "B"},
    ]
    curr = [
        {"id": "b", "score": 25, "name": "B2"},
        {"id": "c", "score": 5, "name": "C"},
    ]
    d = compare_row_sets(prev, curr)
    assert d["counts"]["added"] == 1
    assert d["counts"]["removed"] == 1
    assert d["counts"]["changed"] == 1
    assert d["score_increased"]
    assert d["added"][0]["id"] == "c"
    assert d["removed"][0]["id"] == "a"


def test_compare_two_workflow_runs(tmp_path: Path) -> None:
    out1 = tmp_path / "r1"
    out2 = tmp_path / "r2"
    r1 = run_workflow(
        "workflow.confenge.suppliers",
        {"use_fixture": True, "uf": "SC", "max_companies": 3},
        out_dir=out1,
        code_sha="a",
    )
    # second run with more companies = added items
    r2 = run_workflow(
        "workflow.confenge.suppliers",
        {"use_fixture": True, "uf": "SC", "max_companies": 5},
        out_dir=out2,
        code_sha="b",
    )
    diff = compare_manifests(Path(r1["manifest_path"]), Path(r2["manifest_path"]))
    assert diff["previous_run_id"]
    assert diff["current_run_id"]
    assert diff["summary"]
    assert diff["rows"] is not None
    assert diff["rows"]["counts"]["current"] == 5
    assert diff["rows"]["counts"]["previous"] == 3
    assert diff["rows"]["counts"]["added"] == 2


def test_find_previous_manifest(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    (jobs / "j1" / "deliverables").mkdir(parents=True)
    (jobs / "j2" / "deliverables").mkdir(parents=True)
    mf1 = jobs / "j1" / "deliverables" / "run-manifest.json"
    mf2 = jobs / "j2" / "deliverables" / "run-manifest.json"
    mf1.write_text(json.dumps({"schema_version": "1.0.0", "run_id": "r1", "workflow_id": "workflow.extra.opportunities", "status": "SUCCEEDED", "artifacts": []}), encoding="utf-8")
    import time

    time.sleep(0.02)
    mf2.write_text(json.dumps({"schema_version": "1.0.0", "run_id": "r2", "workflow_id": "workflow.extra.opportunities", "status": "SUCCEEDED", "artifacts": []}), encoding="utf-8")
    found = find_previous_manifest(
        workflow_id="workflow.extra.opportunities",
        current_manifest=mf2,
        jobs_dir=jobs,
    )
    assert found is not None
    assert found.resolve() == mf1.resolve()
