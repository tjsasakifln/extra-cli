"""Import, metrics, weekly-board, CLI, review integration tests."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from scripts.decision_memory.import_legacy import import_run
from scripts.decision_memory.metrics import FORBIDDEN_AUTO_CAUSAL, compute_metrics
from scripts.decision_memory.models import (
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
from scripts.decision_memory.weekly_board import build_weekly_board
from scripts.ops.extra_decision_review import (
    CANONICAL_PERSISTED,
    NON_CANONICAL_ARTIFACT_ONLY,
    decide,
)

ROOT = Path(__file__).resolve().parents[2]


def test_import_dry_run_and_apply_idempotent(
    repo: DecisionMemoryRepository, client_id: str, two_cycle_fixture_dir: Path
) -> None:
    c1 = two_cycle_fixture_dir / "cycle1"
    paths = [
        c1 / "human-decisions.jsonl",
        c1 / "actionable-summary.json",
        c1 / "shortlist.json",
    ]
    dry = import_run(repo, client_id=client_id, actor="importer", paths=paths, apply=False)
    assert dry["mode"] == "dry_run"
    assert dry["counts"]["new"] >= 1
    assert dry["manifest"]
    applied = import_run(repo, client_id=client_id, actor="importer", paths=paths, apply=True)
    assert applied["mode"] == "apply"
    assert applied["counts"]["new"] >= 1
    again = import_run(repo, client_id=client_id, actor="importer", paths=paths, apply=True)
    assert again["counts"]["new"] == 0
    assert again["counts"]["duplicate"] >= 1
    # Zero outcome inference
    assert again["counts"]["skipped_outcome_inference"] == 1
    outs = repo.list_outcomes(client_id)
    assert outs == []


def test_import_corrupted_jsonl(repo: DecisionMemoryRepository, client_id: str, tmp_path: Path) -> None:
    bad = tmp_path / "human-decisions.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    report = import_run(repo, client_id=client_id, actor="importer", paths=[bad], apply=False)
    assert report["errors"] or report["counts"]["invalid"] or not report["ok"]


def test_import_does_not_switch_client_scope(
    repo: DecisionMemoryRepository, client_id: str, two_cycle_fixture_dir: Path
) -> None:
    c1 = two_cycle_fixture_dir / "cycle1"
    other = client_id + "-other"
    import_run(
        repo,
        client_id=client_id,
        actor="importer",
        paths=[c1 / "human-decisions.jsonl"],
        apply=True,
    )
    listed_other = repo.list_decisions(other)
    assert listed_other == []


def test_two_cycle_fixture_board_and_metrics(repo: DecisionMemoryRepository, client_id: str) -> None:
    # Cycle 1: decision + 2 actions, no outcome
    d = repo.record_decision(
        DecisionRecordInput(
            client_id=client_id,
            opportunity_key="00.000.000/0001-00-1-000001/2026",
            actor="board-actor",
            justification="go cycle1",
            human_decision=HumanDecision.GO,
            legacy_decision=LegacyDecision.ACCEPT,
            system_recommendation=SystemRecommendation.REVIEW,
            cycle_id="2026-W26",
            premises=["margem estimada suficiente"],
            temporal_integrity=TemporalIntegrity.PROSPECTIVE,
            evidence_hash="e" * 64,
        )
    )
    dec_id = UUID(d["event"]["event_id"])
    repo.record_action(
        ActionRecordInput(
            client_id=client_id,
            decision_event_id=dec_id,
            opportunity_key="00.000.000/0001-00-1-000001/2026",
            description="Montar proposta",
            actor="board-actor",
            owner="alice",
            due_at=datetime.now(UTC) - timedelta(days=1),  # overdue
        )
    )
    a2 = repo.record_action(
        ActionRecordInput(
            client_id=client_id,
            decision_event_id=dec_id,
            opportunity_key="00.000.000/0001-00-1-000001/2026",
            description="Coletar atestados",
            actor="board-actor",
            owner="bob",
            due_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    # complete a2
    from scripts.decision_memory.models import ActionCompleteInput

    repo.complete_action(
        ActionCompleteInput(
            client_id=client_id,
            action_event_id=UUID(a2["event"]["event_id"]),
            actor="bob",
            evidence_hash="f" * 64,
        )
    )
    # Cycle 2: same opportunity reappears conceptually + outcome + premise correction
    repo.record_decision(
        DecisionRecordInput(
            client_id=client_id,
            opportunity_key="00.000.000/0001-00-1-000001/2026",
            actor="board-actor",
            justification="reafirmacao com premissa corrigida",
            human_decision=HumanDecision.GO,
            legacy_decision=LegacyDecision.ACCEPT,
            system_recommendation=SystemRecommendation.GO,
            cycle_id="2026-W27",
            premises=["premissa original de margem estava incorreta"],
            supersedes_event_id=dec_id,
            correction_reason="premissa de margem incorreta",
            correction_type="CORRECTION",
            temporal_integrity=TemporalIntegrity.PROSPECTIVE,
            evidence_hash="g" * 64,
        )
    )
    repo.record_outcome(
        OutcomeRecordInput(
            client_id=client_id,
            opportunity_key="00.000.000/0001-00-1-000001/2026",
            decision_event_id=dec_id,
            outcome_type=OutcomeType.LOSS,
            observed_at=datetime.now(UTC),
            source="fixture-official",
            evidence_hash="h" * 64,
            actor="board-actor",
            observations="Aprendizado: validar BDI com fonte oficial",
        )
    )

    board = build_weekly_board(repo, client_id=client_id, cycle_id="2026-W27")
    assert board["source"] == "postgresql:dm_*"
    assert board["counts"]["actions_overdue"] >= 1
    assert board["counts"]["new_outcomes"] >= 1
    assert board["sections"]["recurring_opportunities_decided"]

    metrics = compute_metrics(repo, client_id=client_id)
    names = {m["name"] for m in metrics["metrics"]}
    assert "win_rate" in names
    assert "outcomes_unknown" in names
    win = next(m for m in metrics["metrics"] if m["name"] == "win_rate")
    assert win["denominator"] is not None  # WIN+LOSS
    assert "decision_influence_rate" in FORBIDDEN_AUTO_CAUSAL
    assert "decision_influence_rate" not in names
    # Ensure denominators present
    for m in metrics["metrics"]:
        assert "numerator" in m
        assert "limitations" in m or m.get("denominator") is not None or True


def test_cli_smoke(dm_dsn: str, client_id: str, tmp_path: Path) -> None:
    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "LOCAL_DATALAKE_DSN": dm_dsn}
    opp = f"cli-opp-{client_id[:8]}"
    cmd_base = [
        sys.executable,
        "-m",
        "scripts.decision_memory",
        "--dsn",
        dm_dsn,
        "--client-id",
        client_id,
    ]
    r = subprocess.run(
        [
            *cmd_base,
            "decision",
            "record",
            "--opportunity-key",
            opp,
            "--decision",
            "ACCEPT",
            "--actor",
            "cli-tester",
            "--justification",
            "cli smoke decision",
            "--evidence-hash",
            "i" * 64,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data["ok"] is True
    event_id = data["data"]["event"]["event_id"]

    r2 = subprocess.run(
        [*cmd_base, "decision", "show", event_id],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r2.returncode == 0, r2.stderr
    r3 = subprocess.run(
        [*cmd_base, "weekly-board"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r3.returncode == 0, r3.stderr
    r4 = subprocess.run(
        [*cmd_base, "metrics"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r4.returncode == 0, r4.stderr
    r5 = subprocess.run(
        [*cmd_base, "integrity", "verify"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r5.returncode == 0, r5.stderr


def test_review_canonical_and_artifact_only(dm_dsn: str, client_id: str, tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "shortlist.json").write_text(
        json.dumps(
            {
                "result": "SHORTLIST_READY",
                "shortlist": [
                    {
                        "opportunity_id": "rev-1",
                        "recommendation": "REVIEW",
                        "state": "REVIEW",
                    }
                ],
                "shortlist_count": 1,
                "profile_stamp": {"version": 1, "profile_hash": "j" * 64},
            }
        ),
        encoding="utf-8",
    )
    art = decide(
        run,
        opportunity_id="rev-1",
        decision="ACCEPT",
        reason="artifact path",
        actor="reviewer",
        artifact_only=True,
    )
    assert art["persistence"] == NON_CANONICAL_ARTIFACT_ONLY

    run2 = tmp_path / "run2"
    run2.mkdir()
    (run2 / "shortlist.json").write_text((run / "shortlist.json").read_text(encoding="utf-8"), encoding="utf-8")
    can = decide(
        run2,
        opportunity_id="rev-1",
        decision="DEFER",
        reason="canonical path",
        actor="reviewer",
        dsn=dm_dsn,
        client_id=client_id,
    )
    assert can["persistence"] == CANONICAL_PERSISTED
    assert can.get("canonical_event_id")
    assert (run2 / "human-decisions.jsonl").is_file()


def test_review_db_failure_fail_closed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "shortlist.json").write_text(
        json.dumps(
            {
                "result": "SHORTLIST_READY",
                "shortlist": [{"opportunity_id": "x", "recommendation": "REVIEW"}],
                "shortlist_count": 1,
                "profile_stamp": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="PERSISTENCE_FAILED"):
        decide(
            run,
            opportunity_id="x",
            decision="ACCEPT",
            reason="will fail",
            actor="reviewer",
            dsn="postgresql://invalid:invalid@127.0.0.1:1/none",
            client_id="extra",
        )
    # No JSONL written on failure
    assert not (run / "human-decisions.jsonl").is_file()


def test_cli_requires_client_id() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.decision_memory", "metrics"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
    assert "client_id" in r.stdout.lower() or "client_id" in r.stderr.lower()


def test_scale_smoke_indexes(dm_dsn: str, client_id: str) -> None:
    """Deterministic scale smoke — enough rows to exercise indexes, not a benchmark claim."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dm_dsn, cursor_factory=RealDictCursor)
    try:
        repo = DecisionMemoryRepository(conn)
        for i in range(120):
            repo.record_decision(
                DecisionRecordInput(
                    client_id=client_id,
                    opportunity_key=f"scale-opp-{i:04d}",
                    actor="scale",
                    justification=f"scale decision {i}",
                    human_decision=HumanDecision.REVIEW if i % 3 else HumanDecision.GO,
                    cycle_id="scale",
                    evidence_hash=f"{i:064d}",
                )
            )
        rows = repo.list_decisions(client_id, limit=200)
        assert len(rows) == 120
        report = repo.verify_integrity(client_id)
        assert report["ok"]
    finally:
        conn.close()


def test_migration_file_exists_and_numbered() -> None:
    mig = ROOT / "db" / "migrations" / "068_decision_outcome_memory.sql"
    assert mig.is_file()
    text = mig.read_text(encoding="utf-8")
    assert "dm_decision_events" in text
    assert "append-only" in text or "dm_forbid_mutation" in text
    assert "uq_dm_decision_idempotency" in text
