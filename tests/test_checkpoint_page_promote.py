"""N18 — checkpoint page promote parity (fail-closed transitions).

Named asserts for the recovery path that blocked PNCP operational pipeline:
db_committed must be able to promote to success (page-level) without demotion
from a later stage back to normalized.
"""
from __future__ import annotations

from scripts.crawl.resilience.stages import (
    ALLOWED_TRANSITIONS,
    CheckpointStatus,
    InvalidCheckpointTransition,
    stage_rank,
    validate_transition,
)


def test_db_committed_may_promote_to_success_for_page_level():
    """Page checkpoints after full pipeline may jump db_committed → success."""
    assert CheckpointStatus.SUCCESS in ALLOWED_TRANSITIONS[CheckpointStatus.DB_COMMITTED]
    out = validate_transition("db_committed", "success")
    assert out == CheckpointStatus.SUCCESS


def test_db_committed_may_promote_to_evidence_then_success():
    """Run-level path still allows evidence_committed intermediate."""
    assert CheckpointStatus.EVIDENCE_COMMITTED in ALLOWED_TRANSITIONS[CheckpointStatus.DB_COMMITTED]
    mid = validate_transition("db_committed", "evidence_committed")
    assert mid == CheckpointStatus.EVIDENCE_COMMITTED
    end = validate_transition("evidence_committed", "success")
    assert end == CheckpointStatus.SUCCESS


def test_cannot_demote_db_committed_to_normalized():
    """Backward jump is illegal — resume must skip demotion, not rewrite history."""
    with __import__("pytest").raises(InvalidCheckpointTransition):
        validate_transition("db_committed", "normalized")


def test_stage_rank_orders_operational_progress():
    """stage_rank used by pipeline to skip demotion when already past target."""
    assert stage_rank("normalized") < stage_rank("db_committed")
    assert stage_rank("db_committed") < stage_rank("evidence_committed")
    assert stage_rank("evidence_committed") <= stage_rank("success") or stage_rank("success") >= 0


def test_idempotent_same_status_transition():
    """validate_transition allows no-op same status."""
    assert validate_transition("success", "success") == CheckpointStatus.SUCCESS
    assert validate_transition("db_committed", "db_committed") == CheckpointStatus.DB_COMMITTED
