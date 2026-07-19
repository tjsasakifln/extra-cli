"""Review fallback must never ACCEPT when DeepSeek is unavailable."""
from __future__ import annotations

from scripts.cto.decision import build_review_payload, review_execution
from scripts.cto.deepseek_client import DeepSeekUnavailable


class _BoomClient:
    def chat_json(self, **kwargs):  # noqa: ANN003
        raise DeepSeekUnavailable("simulated CTO down")


def test_verifier_pass_deepseek_down_never_accept(sample_decision):
    verification = {
        "result": "PASS",
        "failed_criteria": [],
        "repair_hints": [],
        "criterion_matrix": [
            {"criterion": "tests", "status": "PASS", "evidence": "pytest"},
        ],
        "diff": {"sha256": "abc", "text": "", "truncated": False, "char_len": 0},
        "files": {"modified": ["scripts/cto/x.py"]},
        "checks": [{"name": "tests", "results": [{"cmd": "pytest", "exit_code": 0}]}],
    }
    execution = {"status": "completed", "exit_code": 0, "worktree": "/tmp/wt"}
    review = review_execution(
        decision=sample_decision,
        verification=verification,
        execution=execution,
        client=_BoomClient(),  # type: ignore[arg-type]
        dry_run=False,
    )
    assert review["verdict"] in {"ESCALATE", "BLOCK"}
    assert review["verdict"] != "ACCEPT"
    assert "BLOCKED_CTO_UNAVAILABLE" in (review.get("summary") or "")
    assert review.get("blocked_code") == "BLOCKED_CTO_UNAVAILABLE" or "BLOCKED_CTO_UNAVAILABLE" in str(
        review.get("human_gate")
    )
    assert review["human_gate"]["required"] is True


def test_review_payload_has_full_context(sample_decision):
    verification = {
        "result": "PASS",
        "failed_criteria": [],
        "criterion_matrix": [
            {"criterion": "ac[0]", "status": "PASS", "evidence": "tests"},
            {"criterion": "secret_scan", "status": "PASS", "evidence": "regex"},
        ],
        "diff": {"sha256": "deadbeef", "text": "diff --git a/x", "truncated": False, "char_len": 14},
        "files": {"modified": ["scripts/cto/cli.py"], "staged": [], "unstaged": [], "untracked": []},
        "checks": [{"name": "tests", "results": [{"cmd": ["pytest"], "exit_code": 0}]}],
    }
    execution = {
        "status": "completed",
        "exit_code": 0,
        "worktree": "/wt",
        "branch": "cto/x",
        "session_id": "sess-1",
    }
    payload = build_review_payload(
        decision=sample_decision,
        verification=verification,
        execution=execution,
        prior_attempts=[{"attempt": 1, "review": "REPAIR"}],
        transcript_excerpt="redacted transcript",
    )
    assert "original_decision" in payload
    assert "work_item" in payload
    assert payload["diff"]["sha256"] == "deadbeef"
    assert payload["criterion_matrix"]
    assert payload["execution"]["exit_code"] == 0
    assert payload["prior_attempts"]
    assert payload["transcript_excerpt_redacted"]
    assert "note" in payload["matrix_counts"]
    # Counts alone must not be the only signal
    assert payload["criterion_matrix"][0]["evidence"]
