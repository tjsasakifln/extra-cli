"""Honesty gate for docs/ops/cto-pr-remediation-48-50-51-52 package.

SSOT is pr-state.json. FINAL-REPORT / PR-MATRIX / manifest must match.
If any story has po_validated=false or qa_verdict=PENDING, that PR's
recommendation must not be READY_FOR_HUMAN_REVIEW.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PKG = Path("docs/ops/cto-pr-remediation-48-50-51-52")
SSOT = PKG / "pr-state.json"


@pytest.fixture(scope="module")
def ssot() -> dict:
    assert SSOT.is_file(), f"missing SSOT {SSOT}"
    return json.loads(SSOT.read_text(encoding="utf-8"))


def test_ssot_has_required_keys(ssot: dict) -> None:
    for key in (
        "heads",
        "recommendations",
        "stories",
        "terminal_state",
        "next_actions",
    ):
        assert key in ssot
    assert ssot["terminal_state"] == "WAITING_HUMAN"
    for pr in ("48", "50", "51", "52"):
        assert pr in ssot["heads"]
        assert pr in ssot["recommendations"]
        assert len(ssot["heads"][pr]) >= 12


def test_incomplete_sdc_forbids_ready(ssot: dict) -> None:
    stories = ssot.get("stories") or {}
    recs = ssot["recommendations"]
    for pr, story in stories.items():
        incomplete = (not story.get("po_validated")) or (
            str(story.get("qa_verdict") or "").upper() in {"PENDING", "NONE", ""}
        )
        if incomplete:
            assert recs[pr] in {
                "BLOCKED_HUMAN",
                "CHANGES_REQUIRED",
                "BLOCKED_EXTERNAL",
                "FAIL_REWORK",
                "ABORTED_UNSAFE_STATE",
            }, f"PR #{pr} incomplete SDC but recommendation={recs[pr]!r}"


def test_final_report_matches_ssot_recommendations(ssot: dict) -> None:
    text = (PKG / "FINAL-REPORT.md").read_text(encoding="utf-8")
    for pr, rec in ssot["recommendations"].items():
        # table row or bold recommendation must appear with PR number
        assert rec in text, f"FINAL-REPORT missing recommendation {rec} for PR {pr}"
        # READY must not appear as the verdict for blocked PRs
        if rec == "BLOCKED_HUMAN":
            # allow mentioning READY only for other PRs; block "READY" as state for this PR
            # require BLOCKED_HUMAN near #50 / #51
            if pr in {"50", "51"}:
                assert re.search(
                    rf"#\s*{pr}.*BLOCKED_HUMAN|BLOCKED_HUMAN.*#\s*{pr}|PR #{pr}.*BLOCKED_HUMAN",
                    text,
                    re.I | re.S,
                ) or f"**{rec}**" in text


def test_pr_matrix_estado_column_matches_ssot(ssot: dict) -> None:
    text = (PKG / "PR-MATRIX.md").read_text(encoding="utf-8")
    for pr, rec in ssot["recommendations"].items():
        # matrix row for PR should contain recommendation
        row_match = re.search(rf"\|\s*#{pr}\s*\|[^\n]+", text)
        assert row_match, f"PR-MATRIX missing row for #{pr}"
        row = row_match.group(0)
        assert rec in row, f"PR-MATRIX row #{pr} missing {rec}: {row}"


def test_pr_matrix_heads_prefix_match_ssot(ssot: dict) -> None:
    text = (PKG / "PR-MATRIX.md").read_text(encoding="utf-8")
    for pr, sha in ssot["heads"].items():
        if pr == "main":
            continue
        prefix = sha[:12]
        assert prefix in text, f"PR-MATRIX missing head prefix {prefix} for #{pr}"


def test_manifest_heads_match_ssot(ssot: dict) -> None:
    man = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    assert man.get("heads") == ssot["heads"]
    assert man.get("recommendations") == ssot["recommendations"]
    assert man.get("terminal_state") == "WAITING_HUMAN"


def test_no_ready_for_50_or_51_in_matrix_estado(ssot: dict) -> None:
    assert ssot["recommendations"]["50"] != "READY_FOR_HUMAN_REVIEW"
    assert ssot["recommendations"]["51"] != "READY_FOR_HUMAN_REVIEW"
    text = (PKG / "PR-MATRIX.md").read_text(encoding="utf-8")
    for pr in ("50", "51"):
        row = re.search(rf"\|\s*#{pr}\s*\|[^\n]+", text)
        assert row
        assert "READY_FOR_HUMAN_REVIEW" not in row.group(0)
        assert "BLOCKED_HUMAN" in row.group(0)
