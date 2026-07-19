import pytest

from scripts.cto.state_machine import LockError, ProcessLock, StateError, StateMachine


def test_transition_happy(cto_repo):
    sm = StateMachine(cto_repo)
    sm.transition("OBSERVING", reason="start")
    sm.transition("DECIDING", reason="obs done")
    st = sm.load()
    assert st.status == "DECIDING"
    assert len(st.history) >= 2


def test_illegal_transition(cto_repo):
    sm = StateMachine(cto_repo)
    with pytest.raises(StateError):
        sm.transition("EXECUTING", reason="skip")


def test_lock_concurrent(cto_repo):
    lock1 = ProcessLock(cto_repo)
    lock1.acquire("a")
    lock2 = ProcessLock(cto_repo)
    with pytest.raises(LockError):
        lock2.acquire("b")
    lock1.release()
    lock2.acquire("b")
    lock2.release()


def test_resume_after_crash(cto_repo):
    sm = StateMachine(cto_repo)
    sm.transition("OBSERVING", reason="x", cycle_id="c1")
    sm.transition("DECIDING", reason="y", cycle_id="c1")
    assert sm.resume_target() == "DECIDING"
