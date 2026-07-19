from scripts.cto.decision import build_fallback_blocked_decision, decide_from_observation


def test_fallback_blocked():
    d = build_fallback_blocked_decision(cycle_id="c1", reason="timeout")
    assert d["decision"] == "BLOCK"
    assert "BLOCKED_CTO_UNAVAILABLE" in d["strategic_reason"]
    assert d["human_gate"]["required"] is True


def test_dry_run_decide(cto_repo):
    from scripts.cto.observer import observe

    obs = observe(cto_repo, write=True)
    # ensure ranking empty -> may NOOP or EXECUTE with paths
    decision = decide_from_observation(obs, dry_run=True)
    assert decision["decision"] in {"NOOP", "EXECUTE", "BLOCK"}
    assert "decision_id" in decision
