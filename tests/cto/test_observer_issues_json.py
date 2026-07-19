"""Observer must not truncate gh --json stdout (corrupts issue lists)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.cto.observer import _gh_issues_summary, _run, observe


def test_run_json_mode_no_tail_truncation(tmp_path: Path):
    # Simulate large JSON that would break if only last 8000 chars kept
    payload = json.dumps([{"number": i, "title": f"t{i}" * 50} for i in range(200)])
    assert len(payload) > 8000

    class FakeProc:
        returncode = 0
        stdout = payload
        stderr = ""

    with patch("scripts.cto.observer.subprocess.run", return_value=FakeProc()):
        res = _run(["gh", "issue", "list", "--json", "number"], tmp_path, max_stdout=None)
    assert res["stdout"] == payload
    assert json.loads(res["stdout"])[0]["number"] == 0


def test_run_default_still_truncates_logs(tmp_path: Path):
    class FakeProc:
        returncode = 0
        stdout = "x" * 9000
        stderr = ""

    with patch("scripts.cto.observer.subprocess.run", return_value=FakeProc()):
        res = _run(["echo"], tmp_path, max_stdout=8000)
    assert len(res["stdout"]) == 8000


def test_gh_issues_summary_parses_full_json(tmp_path: Path):
    body = "<!-- extra-work-id: cto-autopilot-infra -->\nOutcome"
    items = [
        {
            "number": 30,
            "title": "infra",
            "labels": [{"name": "state:ready"}],
            "updatedAt": "2026-07-19T00:00:00Z",
            "state": "OPEN",
            "body": body,
        },
        {
            "number": 31,
            "title": "ci",
            "labels": [{"name": "state:ready"}, {"name": "priority:p0"}],
            "updatedAt": "2026-07-19T00:00:00Z",
            "state": "OPEN",
            "body": "<!-- extra-work-id: stabilize-open-pr-ci -->",
        },
    ]
    raw = json.dumps(items)

    class FakeProc:
        returncode = 0
        stdout = raw
        stderr = ""

    with patch("scripts.cto.observer.subprocess.run", return_value=FakeProc()):
        summary = _gh_issues_summary(tmp_path)
    assert summary["available"] is True
    assert summary["open_count"] == 2
    assert "state:ready" in summary["by_state"]
    assert summary["items"][0]["work_id"] == "cto-autopilot-infra"
