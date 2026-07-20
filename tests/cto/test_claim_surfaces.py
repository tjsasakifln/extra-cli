"""Mechanical gate: HANDOFF / HTML claim surfaces must match shipped contracts.

Fails closed on narrative drift that skeptics catch after code is already fixed.
"""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from scripts.cto.paths import repo_root
from scripts.cto.work_registry import IMPLEMENTED_IN_PR48, ISSUE_NUMBERS_IMPLEMENTED_IN_PR48


def _handoff() -> str:
    return (repo_root() / "docs" / "ops" / "cto-autopilot" / "HANDOFF.md").read_text(
        encoding="utf-8"
    )


def _html() -> str:
    return (repo_root() / "extra-consultoria-plano-executivo.html").read_text(
        encoding="utf-8", errors="replace"
    )


def _panel_payload() -> dict:
    html = _html()
    m = re.search(
        r'id=["\']cto-autopilot-data["\'][^>]*>(.*?)</script>',
        html,
        re.S | re.I,
    )
    assert m, "missing #cto-autopilot-data script in executive HTML"
    return json.loads(m.group(1).strip())


def test_handoff_dry_run_row_matches_publisher_contract():
    """Evidence row for dry-run must not claim WAITING_HUMAN exit 10."""
    text = _handoff()
    # Find the run-once dry-run evidence table row
    row_m = re.search(
        r"\|\s*`run-once --dry-run --mock --skip-tests`\s*\|\s*([^|\n]+)\|",
        text,
    )
    assert row_m, "HANDOFF missing run-once --dry-run evidence row"
    row = row_m.group(1)
    assert "ACCEPTED_DRY_RUN" in row, f"dry-run row must state ACCEPTED_DRY_RUN: {row}"
    assert "queue_mutated=false" in row or "queue_mutated=false" in row.replace(" ", "")
    # Forbidden stale claim from pre-publisher-contract era
    assert not re.search(r"WAITING_HUMAN.*\bexit\b.*\b10\b", row), row
    assert not re.search(r"\bexit\b.*\b10\b.*WAITING_HUMAN", row), row
    # Positive exit 0
    assert re.search(r"\bexit\b\s*\*?\*?0\*?\*?", row) or "exit **0**" in row or "exit 0" in row


def test_handoff_test_count_matches_suite_collection():
    """HANDOFF must not inflate tests/cto counts vs pytest --collect-only.

    Exact equality is required on the #48 feature branch (remediation owner).
    Stacked cycle PRs (#50/#51) may add material tests, so collected >= claimed
    is allowed there — claimed > collected (narrative inflation) is never OK.
    """
    text = _handoff()
    counts = [int(x) for x in re.findall(r"\b(\d+)\s+passed\b", text)]
    assert counts, "HANDOFF has no 'N passed' counts"
    # All explicit "N passed" must agree with each other
    assert len(set(counts)) == 1, f"inconsistent passed counts in HANDOFF: {counts}"
    claimed = counts[0]

    root = repo_root()
    proc = subprocess.run(
        ["python3", "-m", "pytest", "tests/cto", "--collect-only", "-q", "--no-cov"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    # "91 tests collected" or similar
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout + proc.stderr)
    assert m, proc.stdout[-500:]
    collected = int(m.group(1))
    assert claimed <= collected, (
        f"HANDOFF inflates suite: claims {claimed} passed but only {collected} collected"
    )
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # Owner branch of the remediation HANDOFF baseline must stay exact.
    if branch == "feat/cto-autopilot-issues-deepseek-20260719":
        assert claimed == collected, (
            f"HANDOFF claims {claimed} passed but suite has {collected} tests on {branch}"
        )


def test_html_cto_panel_not_all_ready_when_pr48_items_exist():
    """HTML must not show every open issue as state:ready while PR#48 items exist."""
    data = _panel_payload()
    issues = data.get("issues") or {}
    open_count = int(issues.get("open_count") or 0)
    by_state = issues.get("by_state") or {}
    ready = int(by_state.get("state:ready") or 0)
    review = int(by_state.get("state:review") or 0)
    blocked = int(by_state.get("state:blocked") or 0)
    human = int(by_state.get("state:human") or 0)

    assert open_count > 0, "panel open_count empty — refresh-executive not run?"
    # With PR#48 implemented set, must not be all-ready
    assert IMPLEMENTED_IN_PR48, "expected implemented set"
    assert ISSUE_NUMBERS_IMPLEMENTED_IN_PR48
    if open_count >= 10:
        assert ready < open_count, (
            f"HTML still all-ready: ready={ready} open={open_count} by_state={by_state}"
        )
        assert (review + blocked + human) > 0, (
            f"HTML missing review/blocked/human split: {by_state}"
        )


def test_html_cto_panel_commit_is_ancestor_of_head():
    """Panel commit must be an ancestor of HEAD (or HEAD itself).

    Exact equality with HEAD is impossible when the HTML file is committed
    after a stamp (self-referential SHA). A fixed last-N window also fails
    whenever docs/SSOT commits land after the stamp. Ancestor check proves
    the panel is still on this branch history without infinite re-stamp loops.
    """
    data = _panel_payload()
    panel_commit = str(data.get("commit") or "").strip()
    assert panel_commit, "panel missing commit"
    root = repo_root()
    # Resolve short SHAs
    rev = subprocess.run(
        ["git", "rev-parse", "--verify", panel_commit],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert rev.returncode == 0, f"panel commit not resolvable: {panel_commit!r}"
    full = rev.stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if full == head:
        return
    anc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", full, head],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert anc.returncode == 0, (
        f"panel commit {panel_commit!r} ({full[:12]}) is not an ancestor of HEAD {head[:12]}"
    )


def test_html_panel_recommendations_align_with_ssot_when_present():
    """If remediation SSOT exists, READY claims must not contradict BLOCKED PRs."""
    root = repo_root()
    ssot_path = root / "docs" / "ops" / "cto-pr-remediation-48-50-51-52" / "pr-state.json"
    if not ssot_path.is_file():
        pytest.skip("remediation SSOT not present")
    ssot = json.loads(ssot_path.read_text(encoding="utf-8"))
    recs = ssot.get("recommendations") or {}
    # Incomplete SDC stories must not be READY
    for pr, story in (ssot.get("stories") or {}).items():
        incomplete = (not story.get("po_validated")) or (
            str(story.get("qa_verdict") or "").upper() in {"", "PENDING", "NONE"}
        )
        if incomplete:
            assert recs.get(pr) in {
                "BLOCKED_HUMAN",
                "CHANGES_REQUIRED",
                "BLOCKED_EXTERNAL",
                "FAIL_REWORK",
                "ABORTED_UNSAFE_STATE",
            }, f"PR {pr} incomplete SDC but rec={recs.get(pr)!r}"
    # Panel must not invent forbidden ready seals in claims
    data = _panel_payload()
    claims = data.get("claims") or {}
    forbidden = claims.get("forbidden") or []
    for seal in ("LOCAL_READY", "VPS_OPERATIONAL", "PROJECT_DONE"):
        assert seal in forbidden or not claims.get("allowed") or seal not in (
            claims.get("allowed") or []
        )


def test_html_not_stale_waiting_human_with_all_ready():
    """Reject the known-bad snapshot: WAITING_HUMAN + all issues ready."""
    data = _panel_payload()
    issues = data.get("issues") or {}
    open_count = int(issues.get("open_count") or 0)
    by_state = issues.get("by_state") or {}
    ready = int(by_state.get("state:ready") or 0)
    cto_state = data.get("cto_state")
    if cto_state == "WAITING_HUMAN" and open_count > 0 and ready == open_count:
        pytest.fail(
            "stale claim surface: cto_state=WAITING_HUMAN with all issues state:ready"
        )
