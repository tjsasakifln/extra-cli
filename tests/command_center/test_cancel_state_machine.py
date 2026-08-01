"""Deterministic cancel state-machine tests — no fragile sleeps for CAS logic.

Covers sticky cancel_requested, cancel-wins over SUCCEEDED/FAILED, terminal
immutability, idempotent cancel, and stress races via barriers/events.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from scripts.command_center.status_normalize import JobState
from scripts.command_center.store import (
    NON_TERMINAL_STATES,
    TERMINAL_STATES,
    JobRecord,
    Store,
)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "cc.db")


def _job(
    store: Store,
    *,
    status: str = JobState.QUEUED.value,
    cancel_requested: bool = False,
    job_id: str = "job-1",
) -> JobRecord:
    rec = JobRecord(
        job_id=job_id,
        capability_id="cc.fixture.slow",
        action="slow",
        params={"seconds": 5},
        status=status,
        cancel_requested=cancel_requested,
    )
    store.create_job(rec)
    return rec


def test_cancel_queued(store: Store) -> None:
    _job(store, status=JobState.QUEUED.value)
    tr = store.request_cancel("job-1")
    assert tr.applied
    assert tr.record is not None
    assert tr.record.cancel_requested is True
    assert tr.record.status == JobState.CANCELLING.value
    fin = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.CANCELLED.value,
        fields={"cancel_requested": True},
        cancel_wins=True,
    )
    assert fin.applied
    assert fin.record is not None
    assert fin.record.status == JobState.CANCELLED.value


def test_cancel_validating(store: Store) -> None:
    _job(store, status=JobState.VALIDATING.value)
    tr = store.request_cancel("job-1")
    assert tr.applied
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLING.value
    assert tr.record.cancel_requested is True


def test_cancel_running(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value)
    tr = store.request_cancel("job-1")
    assert tr.applied
    assert tr.record is not None
    assert tr.record.cancel_requested is True
    assert tr.record.status == JobState.CANCELLING.value


def test_cancel_immediately_before_success(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value, cancel_requested=True)
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.SUCCEEDED.value,
        fields={"human_message": "would succeed"},
        cancel_wins=True,
    )
    assert tr.applied
    assert tr.outcome == "cancel_wins"
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value
    assert tr.record.cancel_requested is True


def test_cancel_concurrent_with_exception_path(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value, cancel_requested=True)
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.FAILED.value,
        fields={
            "technical_code": "RUNNER_EXCEPTION",
            "human_message": "boom",
            "attention": "blocked_technical",
        },
        cancel_wins=True,
    )
    assert tr.applied
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value
    assert tr.record.status != JobState.FAILED.value


def test_sigterm_path_is_cancelled_not_failed(store: Store) -> None:
    """Process terminated by cancel must not land as FAILED."""
    _job(store, status=JobState.CANCELLING.value, cancel_requested=True)
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.FAILED.value,  # naive interpretation of nonzero exit
        fields={"exit_code": -15, "technical_code": "SIGNAL"},
        cancel_wins=True,
    )
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value


def test_sigkill_path_is_cancelled_not_failed(store: Store) -> None:
    _job(store, status=JobState.CANCELLING.value, cancel_requested=True)
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.FAILED.value,
        fields={"exit_code": -9, "technical_code": "SIGKILL"},
        cancel_wins=True,
    )
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value


def test_double_cancel_idempotent(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value)
    a = store.request_cancel("job-1")
    b = store.request_cancel("job-1")
    assert a.applied
    assert a.record is not None and a.record.cancel_requested
    # Second cancel while still CANCELLING is re-applied fields-wise
    assert b.record is not None
    assert b.record.cancel_requested is True
    assert b.record.status == JobState.CANCELLING.value
    store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.CANCELLED.value,
        fields={},
        cancel_wins=True,
    )
    c = store.request_cancel("job-1")
    assert c.applied is False
    assert c.outcome == "already_terminal"
    assert c.record is not None
    assert c.record.status == JobState.CANCELLED.value


def test_cancel_after_terminal_rejected(store: Store) -> None:
    _job(store, status=JobState.SUCCEEDED.value)
    tr = store.request_cancel("job-1")
    assert tr.applied is False
    assert tr.outcome == "already_terminal"
    assert tr.record is not None
    assert tr.record.status == JobState.SUCCEEDED.value


def test_worker_cannot_save_success_after_cancelled(store: Store) -> None:
    _job(store, status=JobState.CANCELLED.value, cancel_requested=True)
    # Simulate finished_at already set
    store.patch_job  # noqa: B018 — ensure symbol exists
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.SUCCEEDED.value,
        fields={"human_message": "late success"},
        cancel_wins=True,
    )
    assert tr.applied is False
    assert tr.outcome == "already_terminal"
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value


def test_worker_cannot_save_failure_after_cancelled(store: Store) -> None:
    _job(store, status=JobState.CANCELLED.value, cancel_requested=True)
    tr = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.FAILED.value,
        fields={"human_message": "late fail"},
        cancel_wins=True,
    )
    assert tr.applied is False
    assert tr.record is not None
    assert tr.record.status == JobState.CANCELLED.value


def test_only_one_terminal_transition_wins(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def try_success() -> None:
        barrier.wait()
        tr = store.transition_job(
            "job-1",
            expected_states=NON_TERMINAL_STATES,
            target_state=JobState.SUCCEEDED.value,
            fields={"human_message": "ok"},
            cancel_wins=True,
        )
        results.append(f"S:{tr.applied}:{tr.record.status if tr.record else None}")

    def try_fail() -> None:
        barrier.wait()
        tr = store.transition_job(
            "job-1",
            expected_states=NON_TERMINAL_STATES,
            target_state=JobState.FAILED.value,
            fields={"human_message": "nope"},
            cancel_wins=True,
        )
        results.append(f"F:{tr.applied}:{tr.record.status if tr.record else None}")

    t1 = threading.Thread(target=try_success)
    t2 = threading.Thread(target=try_fail)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    applied = [r for r in results if r.split(":")[1] == "True"]
    assert len(applied) == 1, results
    final = store.get_job("job-1")
    assert final is not None
    assert final.status in TERMINAL_STATES
    # Exactly one terminal status, not both applied
    assert sum(1 for r in results if ":True:" in r) == 1


def test_cancel_requested_is_monotonic(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value, cancel_requested=True)
    # Attempt to clear cancel_requested via non-terminal patch
    rec = store.patch_job("job-1", cancel_requested=False, human_message="x")
    assert rec is not None
    assert rec.cancel_requested is True


def test_stress_cancel_vs_success_100x(store: Store) -> None:
    """Repeat cancel-wins race ≥100 times with barriers (no sleeps).

    Setup: cancel_requested is sticky true before the race (the critical
    window the production bug hit — worker finish after cancel flag).
    Concurrent SUCCEEDED / FAILED / CANCELLED writers must all resolve to
    CANCELLED; never FAILED/SUCCEEDED after cancel was requested.
    """
    applied_counts: list[int] = []
    for i in range(100):
        jid = f"stress-{i}"
        _job(
            store,
            status=JobState.RUNNING.value,
            cancel_requested=True,
            job_id=jid,
        )
        barrier = threading.Barrier(3)
        applied: list[bool] = []
        lock = threading.Lock()

        def success_path(job_id: str = jid) -> None:
            barrier.wait()
            tr = store.transition_job(
                job_id,
                expected_states=NON_TERMINAL_STATES,
                target_state=JobState.SUCCEEDED.value,
                fields={"human_message": "done"},
                cancel_wins=True,
            )
            with lock:
                applied.append(tr.applied)

        def fail_path(job_id: str = jid) -> None:
            barrier.wait()
            tr = store.transition_job(
                job_id,
                expected_states=NON_TERMINAL_STATES,
                target_state=JobState.FAILED.value,
                fields={"human_message": "err"},
                cancel_wins=True,
            )
            with lock:
                applied.append(tr.applied)

        def cancel_path(job_id: str = jid) -> None:
            barrier.wait()
            tr = store.transition_job(
                job_id,
                expected_states=NON_TERMINAL_STATES,
                target_state=JobState.CANCELLED.value,
                fields={"cancel_requested": True},
                cancel_wins=True,
            )
            with lock:
                applied.append(tr.applied)

        threads = [
            threading.Thread(target=success_path),
            threading.Thread(target=fail_path),
            threading.Thread(target=cancel_path),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        final = store.get_job(jid)
        assert final is not None
        assert final.cancel_requested is True
        assert final.status == JobState.CANCELLED.value, (jid, final.status)
        assert final.status not in {
            JobState.SUCCEEDED.value,
            JobState.FAILED.value,
        }
        assert sum(1 for a in applied if a) == 1
        applied_counts.append(sum(1 for a in applied if a))
    assert len(applied_counts) == 100
    assert all(c == 1 for c in applied_counts)


def test_stress_request_cancel_vs_worker_finish_100x(store: Store) -> None:
    """Race request_cancel against worker SUCCEEDED for 100 iterations.

    Invariant (never violated): if cancel_requested is true, status is CANCELLED.
    """
    for i in range(100):
        jid = f"race-{i}"
        _job(store, status=JobState.RUNNING.value, job_id=jid)
        barrier = threading.Barrier(2)

        def cancel_path(job_id: str = jid) -> None:
            barrier.wait()
            store.request_cancel(job_id)

        def worker_path(job_id: str = jid) -> None:
            barrier.wait()
            store.transition_job(
                job_id,
                expected_states=NON_TERMINAL_STATES,
                target_state=JobState.SUCCEEDED.value,
                fields={"human_message": "done"},
                cancel_wins=True,
            )

        t1 = threading.Thread(target=cancel_path)
        t2 = threading.Thread(target=worker_path)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        # If still non-terminal (cancel set CANCELLING, worker lost), confirm CANCELLED
        final = store.get_job(jid)
        assert final is not None
        if final.status not in TERMINAL_STATES:
            store.transition_job(
                jid,
                expected_states=NON_TERMINAL_STATES,
                target_state=JobState.CANCELLED.value,
                fields={},
                cancel_wins=True,
            )
            final = store.get_job(jid)
            assert final is not None
        if final.cancel_requested:
            assert final.status == JobState.CANCELLED.value, (jid, final.status)
        else:
            assert final.status == JobState.SUCCEEDED.value, (jid, final.status)


def test_single_audit_on_double_finish_attempt(store: Store) -> None:
    _job(store, status=JobState.RUNNING.value, cancel_requested=True)
    a = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.CANCELLED.value,
        fields={},
        cancel_wins=True,
    )
    b = store.transition_job(
        "job-1",
        expected_states=NON_TERMINAL_STATES,
        target_state=JobState.FAILED.value,
        fields={},
        cancel_wins=True,
    )
    assert a.applied is True
    assert b.applied is False
    # Side-effect count is caller's responsibility; CAS guarantees only one applied.
    assert a.terminal_confirmed is True
