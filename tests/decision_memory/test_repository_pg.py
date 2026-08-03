"""Real-PostgreSQL tests: append-only, idempotency, isolation, concurrency, supersession."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from scripts.decision_memory.models import (
    ActionCompleteInput,
    ActionRecordInput,
    DecisionRecordInput,
    HumanDecision,
    LegacyDecision,
    OutcomeRecordInput,
    OutcomeType,
    SystemRecommendation,
    TemporalIntegrity,
)
from scripts.decision_memory.repository import DecisionMemoryRepository


def _decision(client_id: str, opp: str = "opp-1", **over: object) -> DecisionRecordInput:
    data = {
        "client_id": client_id,
        "opportunity_key": opp,
        "actor": "tester",
        "justification": "justified decision",
        "human_decision": HumanDecision.GO,
        "legacy_decision": LegacyDecision.ACCEPT,
        "system_recommendation": SystemRecommendation.REVIEW,
        "evidence_hash": "e" * 64,
        "profile_hash": "p" * 64,
        "cycle_id": "cycle-1",
        "run_id": "run-1",
        "temporal_integrity": TemporalIntegrity.PROSPECTIVE,
    }
    data.update(over)
    return DecisionRecordInput(**data)  # type: ignore[arg-type]


def test_record_decision_and_idempotent(repo: DecisionMemoryRepository, client_id: str) -> None:
    r1 = repo.record_decision(_decision(client_id))
    assert r1["created"] is True
    r2 = repo.record_decision(_decision(client_id))
    assert r2["created"] is False
    assert r2["event"]["event_id"] == r1["event"]["event_id"]
    rows = repo.list_decisions(client_id)
    assert len(rows) == 1


def test_append_only_blocks_update_delete(dm_conn, repo: DecisionMemoryRepository, client_id: str) -> None:
    r = repo.record_decision(_decision(client_id, opp="append-1"))
    eid = r["event"]["event_id"]
    with dm_conn.cursor() as cur:
        with pytest.raises(Exception, match="append-only"):
            cur.execute(
                "UPDATE public.dm_decision_events SET actor = 'hacked' WHERE event_id = %s",
                (eid,),
            )
        dm_conn.rollback()
        with pytest.raises(Exception, match="append-only"):
            cur.execute("DELETE FROM public.dm_decision_events WHERE event_id = %s", (eid,))
        dm_conn.rollback()


def test_supersession_preserves_history(repo: DecisionMemoryRepository, client_id: str) -> None:
    first = repo.record_decision(_decision(client_id, opp="sup-1", justification="original"))
    second = repo.record_decision(
        _decision(
            client_id,
            opp="sup-1",
            justification="corrected premise",
            human_decision=HumanDecision.NO_GO,
            legacy_decision=LegacyDecision.REJECT,
            supersedes_event_id=UUID(first["event"]["event_id"]),
            correction_reason="premissa original incorreta",
            correction_type="CORRECTION",
            # different idem key via different justification
        )
    )
    assert second["created"] is True
    hist = repo.decision_history(client_id, "sup-1")
    assert len(hist) == 2
    current = repo.list_decisions(client_id, opportunity_key="sup-1", current_only=True)
    assert len(current) == 1
    assert current[0]["human_decision"] == "NO_GO"


def test_action_complete_and_owner_policy(repo: DecisionMemoryRepository, client_id: str) -> None:
    d = repo.record_decision(_decision(client_id, opp="act-1"))
    dec_id = UUID(d["event"]["event_id"])
    a1 = repo.record_action(
        ActionRecordInput(
            client_id=client_id,
            decision_event_id=dec_id,
            opportunity_key="act-1",
            description="Preparar proposta",
            actor="tester",
            owner="alice",
            due_at=datetime.now(UTC) + timedelta(days=3),
        )
    )
    assert a1["created"] is True
    done = repo.complete_action(
        ActionCompleteInput(
            client_id=client_id,
            action_event_id=UUID(a1["event"]["event_id"]),
            actor="tester",
            evidence_hash="c" * 64,
            evidence_locators=["fixture://completion"],
        )
    )
    assert done["created"] is True
    assert done["event"]["status"] == "COMPLETED"
    current = repo.list_actions(client_id, current_only=True)
    completed = [a for a in current if a["status"] == "COMPLETED"]
    assert completed


def test_outcome_unknown_not_loss_and_temporal(repo: DecisionMemoryRepository, client_id: str) -> None:
    d = repo.record_decision(_decision(client_id, opp="out-1"))
    # No outcome yet → metrics path treats as UNKNOWN (tested in metrics)
    outs = repo.list_outcomes(client_id, opportunity_key="out-1")
    assert outs == []
    # Outcome without linking decision_event_id still ok but temporal marks accordingly
    o = repo.record_outcome(
        OutcomeRecordInput(
            client_id=client_id,
            opportunity_key="out-orphan",
            outcome_type=OutcomeType.WIN,
            observed_at=datetime.now(UTC),
            source="fixture",
            evidence_hash="d" * 64,
            actor="tester",
        )
    )
    assert o["event"]["temporal_integrity"] == "OUTCOME_WITHOUT_PRIOR_DECISION"
    # Prospective outcome after decision
    o2 = repo.record_outcome(
        OutcomeRecordInput(
            client_id=client_id,
            opportunity_key="out-1",
            decision_event_id=UUID(d["event"]["event_id"]),
            outcome_type=OutcomeType.PROPOSAL_SUBMITTED,
            observed_at=datetime.now(UTC),
            source="fixture",
            evidence_hash="e" * 64,
            actor="tester",
        )
    )
    assert o2["event"]["temporal_integrity"] == "PROSPECTIVE"


def test_client_isolation_adversarial(dm_dsn: str, client_id: str) -> None:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    other = f"other-{uuid4().hex[:8]}"
    conn = psycopg2.connect(dm_dsn, cursor_factory=RealDictCursor)
    try:
        repo = DecisionMemoryRepository(conn)
        a = repo.record_decision(_decision(client_id, opp="iso-1"))
        b = repo.record_decision(_decision(other, opp="iso-1"))
        assert a["event"]["client_id"] == client_id
        assert b["event"]["client_id"] == other
        listed_a = repo.list_decisions(client_id)
        listed_b = repo.list_decisions(other)
        assert all(r["client_id"] == client_id for r in listed_a)
        assert all(r["client_id"] == other for r in listed_b)
        # Action cannot reference other client's decision
        with pytest.raises((Exception, ValueError)):  # noqa: B017 — cross-client trigger or value
            repo.record_action(
                ActionRecordInput(
                    client_id=other,
                    decision_event_id=UUID(a["event"]["event_id"]),
                    opportunity_key="iso-1",
                    description="cross client",
                    actor="evil",
                    owner="evil",
                    due_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
        conn.rollback()
        # Outcome cross-client blocked
        with pytest.raises((Exception, ValueError)):  # noqa: B017 — cross-client trigger or value
            repo.record_outcome(
                OutcomeRecordInput(
                    client_id=other,
                    opportunity_key="iso-1",
                    decision_event_id=UUID(a["event"]["event_id"]),
                    outcome_type=OutcomeType.LOSS,
                    observed_at=datetime.now(UTC),
                    source="x",
                    evidence_hash="f" * 64,
                    actor="evil",
                )
            )
        conn.rollback()
        # show for wrong client
        assert repo.get_decision(other, a["event"]["event_id"]) is None
    finally:
        conn.close()


def test_concurrency_idempotent(dm_dsn: str, client_id: str) -> None:
    barrier = threading.Barrier(8)
    results: list[dict] = []
    lock = threading.Lock()

    def worker() -> None:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(dm_dsn, cursor_factory=RealDictCursor)
        try:
            repo = DecisionMemoryRepository(conn)
            barrier.wait(timeout=10)
            r = repo.record_decision(
                _decision(
                    client_id,
                    opp="conc-1",
                    justification="same concurrent payload",
                    decided_at=datetime(2026, 6, 1, tzinfo=UTC),
                )
            )
            with lock:
                results.append(r)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(worker) for _ in range(8)]
        for f in futs:
            f.result(timeout=30)

    created = [r for r in results if r.get("created")]
    dups = [r for r in results if not r.get("created")]
    assert len(created) == 1
    assert len(dups) == 7
    ids = {r["event"]["event_id"] for r in results}
    assert len(ids) == 1


def test_integrity_verify(repo: DecisionMemoryRepository, client_id: str) -> None:
    repo.record_decision(_decision(client_id, opp="iv-1"))
    report = repo.verify_integrity(client_id)
    assert report["ok"] is True
    assert report["counts"]["decisions"] >= 1
    assert report["append_only"] is True


def test_timezone_utc_roundtrip(repo: DecisionMemoryRepository, client_id: str) -> None:
    dt = datetime(2026, 3, 15, 14, 30, 0, tzinfo=UTC)
    r = repo.record_decision(_decision(client_id, opp="tz-1", decided_at=dt))
    got = r["event"]["decided_at"]
    assert "2026-03-15" in str(got)
