"""Standalone observe must return OBSERVING → IDLE without crash."""
from scripts.cto.state_machine import StateMachine


def test_observing_to_idle_allowed(cto_repo):
    sm = StateMachine(cto_repo)
    sm.transition("OBSERVING", reason="cli observe")
    st = sm.transition("IDLE", reason="observe complete")
    assert st.status == "IDLE"
