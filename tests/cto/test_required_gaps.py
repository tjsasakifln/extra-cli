"""§18 required cases previously missing."""
from __future__ import annotations

import httpx
import pytest

from scripts.cto.config import DeepSeekConfig
from scripts.cto.decision import DecisionValidationError, decide_from_observation, validate_decision
from scripts.cto.deepseek_client import DeepSeekClient, DeepSeekUnavailable
from scripts.cto.github_issues import reject_close_without_evidence, update_issue_for_cycle
from scripts.cto.grok_executor import execute
from scripts.cto.paths import repo_root


def test_deepseek_timeout_path():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test", max_retries=2, timeout_seconds=1),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(DeepSeekUnavailable):
        client.chat_json(system="s", user="u")


def test_repair_limit_in_decision_schema(sample_decision):
    sample_decision["max_repair_attempts"] = 3  # above allowed max 2
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_ranking_veto_field_allowed(sample_decision):
    sample_decision["ranking_veto"] = {
        "vetoed_candidate_id": "cand-x",
        "reason": "CI red on open PR blocks this candidate",
    }
    out = validate_decision(sample_decision, root=repo_root())
    assert out["ranking_veto"]["vetoed_candidate_id"] == "cand-x"


def test_issue_closed_without_evidence_rejected():
    assert reject_close_without_evidence(
        issue_body="## Required evidence\n- logs",
        evidence=[],
        verification_result="PASS",
    )
    assert reject_close_without_evidence(
        issue_body="ok",
        evidence=["pytest.log"],
        verification_result="FAIL",
    )
    assert not reject_close_without_evidence(
        issue_body="ok",
        evidence=["pytest.log"],
        verification_result="PASS",
    )


def test_issue_dod_inconsistency_flag():
    """Closing Issue while DoD checkbox still open is not auto-acceptance."""
    # Policy: Issue close != DoD — reject_close is independent of DoD checkbox
    assert reject_close_without_evidence(
        issue_body="DoD §2 still open",
        evidence=None,
        verification_result="PASS",
    )


def test_executor_blocks_push_in_test_commands(sample_decision, cto_repo):
    sample_decision["cycle_id"] = "cyc-push-block"
    sample_decision["test_commands"] = ["git push origin main"]
    sample_decision["forbidden_actions"] = ["merge"]  # push not listed as forbid-only
    out = execute(sample_decision, root=cto_repo, dry_run=True, mock=False)
    assert out["status"] == "unsafe"
    assert "push" in out["reason"]


def test_executor_outside_worktree_unsafe(sample_decision, cto_repo, tmp_path):
    sample_decision["cycle_id"] = "cyc-outside-wt"
    outside = tmp_path / "not-managed"
    outside.mkdir()
    # init git so branch check can run if path were allowed
    import subprocess

    subprocess.run(["git", "init"], cwd=outside, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feat/x"], cwd=outside, check=True, capture_output=True)
    out = execute(
        sample_decision,
        root=cto_repo,
        dry_run=True,
        worktree_override=outside,
    )
    assert out["status"] == "unsafe"
    assert "outside managed" in out["reason"]


def test_dry_run_decide_links_issue_number(cto_repo):
    from scripts.cto.work_registry import build_initial_registry, save_registry, upsert_item

    reg = build_initial_registry(cto_repo)
    item = reg["work_items"][0]
    item["issue_number"] = 30
    upsert_item(reg, item)
    save_registry(reg, cto_repo)

    obs = {
        "cycle": {"cycle_id": "cyc-link"},
        "ranking": {"top": []},
        "issues": {"by_state": {}, "items": []},
        "work_registry": {"ids": [item["work_id"]], "count": 1},
    }
    # decide_from_observation uses load_registry(cfg.root) — point root via monkeypatch
    from scripts.cto.config import load_config

    cfg = load_config(cto_repo)
    decision = decide_from_observation(obs, config=cfg, dry_run=True)
    assert decision["decision"] == "EXECUTE"
    assert decision["work_id"] == item["work_id"]
    assert decision["issue_number"] == 30


def test_update_issue_for_cycle_dry_run():
    out = update_issue_for_cycle(
        issue_number=30,
        work_id="cto-autopilot-infra",
        phase="accepted",
        cycle_id="c1",
        dry_run=True,
    )
    assert out["ok"] is True
    assert out["would_set_label"] == "state:review"
