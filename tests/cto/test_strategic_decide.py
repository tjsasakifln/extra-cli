"""Strategic DeepSeek actions: ACCEPT_TOP / RECOMPUTE / ESCALATE / NOOP."""
from __future__ import annotations

import pytest

from scripts.cto.strategic_decide import (
    accept_top_from_ranking,
    build_strategic_payload,
    validate_strategic_decision,
)


def test_accept_top_ok():
    d = validate_strategic_decision(
        {
            "action": "ACCEPT_TOP",
            "selected_id": "cand-1",
            "selected_rank": 0,
            "reason": "top is valid",
            "confidence": 0.9,
        }
    )
    assert d["action"] == "ACCEPT_TOP"
    assert d["selected_rank"] == 0


def test_recompute_requires_cause():
    with pytest.raises(ValueError):
        validate_strategic_decision(
            {"action": "RECOMPUTE", "reason": "stale", "recompute_cause": "nope"}
        )
    d = validate_strategic_decision(
        {
            "action": "RECOMPUTE",
            "reason": "ranking is stale after PR merge",
            "recompute_cause": "stale_state",
            "confidence": 0.7,
        }
    )
    assert d["action"] == "RECOMPUTE"


def test_cannot_accept_without_selected():
    with pytest.raises(ValueError):
        validate_strategic_decision({"action": "ACCEPT_TOP", "reason": "x"})


def test_accept_top_from_ranking_helper():
    ranking = {"selected_id": "cand-dyn-1", "top": [{"id": "cand-dyn-1", "roi": 2.9}]}
    d = accept_top_from_ranking(ranking, cycle_id="cyc-1")
    assert d["action"] == "ACCEPT_TOP"
    assert d["selected_id"] == "cand-dyn-1"


def test_payload_limits_actions():
    p = build_strategic_payload(
        dod_snapshot={"checked": 1, "unchecked": 2},
        gates={},
        ranking={"top": [{"id": "a"}], "selected_id": "a"},
    )
    assert "ACCEPT_TOP" in p["allowed_actions"]
    assert "EXECUTE" not in p["allowed_actions"]
