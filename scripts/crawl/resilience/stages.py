"""Recoverable pipeline stages — no fake atomicity across FS and PostgreSQL."""

from __future__ import annotations

from enum import StrEnum


class CheckpointStatus(StrEnum):
    """Validated checkpoint state machine."""

    PENDING = "pending"
    RAW_PERSISTED = "raw_persisted"
    NORMALIZED = "normalized"
    DB_COMMITTED = "db_committed"
    EVIDENCE_COMMITTED = "evidence_committed"
    WATERMARK_COMMITTED = "watermark_committed"
    SUCCESS = "success"
    EMPTY_CONFIRMED = "empty_confirmed"
    PARTIAL = "partial"
    RATE_LIMITED = "rate_limited"
    AUTH_BLOCKED = "auth_blocked"
    ERROR = "error"

    @property
    def completed_terminal(self) -> bool:
        return self in {CheckpointStatus.SUCCESS, CheckpointStatus.EMPTY_CONFIRMED, CheckpointStatus.WATERMARK_COMMITTED}

    @property
    def operational_complete(self) -> bool:
        return self in {
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
            CheckpointStatus.WATERMARK_COMMITTED,
        }


# Forward-only operational progress (recoverable protocol).
_STAGE_ORDER = (
    CheckpointStatus.PENDING,
    CheckpointStatus.RAW_PERSISTED,
    CheckpointStatus.NORMALIZED,
    CheckpointStatus.DB_COMMITTED,
    CheckpointStatus.EVIDENCE_COMMITTED,
    CheckpointStatus.WATERMARK_COMMITTED,
)

# Terminal fetch outcomes that may overwrite progress only on failure paths.
_FAILURE_TERMINALS = {
    CheckpointStatus.PARTIAL,
    CheckpointStatus.RATE_LIMITED,
    CheckpointStatus.AUTH_BLOCKED,
    CheckpointStatus.ERROR,
}

# Allowed transitions: from → set of next states
ALLOWED_TRANSITIONS: dict[CheckpointStatus, frozenset[CheckpointStatus]] = {
    CheckpointStatus.PENDING: frozenset(
        {
            CheckpointStatus.RAW_PERSISTED,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.RATE_LIMITED,
            CheckpointStatus.AUTH_BLOCKED,
            CheckpointStatus.ERROR,
            CheckpointStatus.SUCCESS,  # empty path with no raw
            CheckpointStatus.EMPTY_CONFIRMED,
        }
    ),
    CheckpointStatus.RAW_PERSISTED: frozenset(
        {
            CheckpointStatus.NORMALIZED,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.RATE_LIMITED,
            CheckpointStatus.AUTH_BLOCKED,
            CheckpointStatus.ERROR,
            CheckpointStatus.SUCCESS,  # promoted after full pipeline in cycle
            CheckpointStatus.EMPTY_CONFIRMED,
            CheckpointStatus.DB_COMMITTED,  # resume may skip normalize if already pure
        }
    ),
    CheckpointStatus.NORMALIZED: frozenset(
        {
            CheckpointStatus.DB_COMMITTED,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.ERROR,
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
        }
    ),
    CheckpointStatus.DB_COMMITTED: frozenset(
        {
            CheckpointStatus.EVIDENCE_COMMITTED,
            CheckpointStatus.ERROR,
            CheckpointStatus.PARTIAL,
            # Page-level promote after full pipeline may jump to terminal
            # (run-level still goes evidence_committed → watermark first).
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
        }
    ),
    CheckpointStatus.EVIDENCE_COMMITTED: frozenset(
        {
            CheckpointStatus.WATERMARK_COMMITTED,
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
            CheckpointStatus.ERROR,
        }
    ),
    CheckpointStatus.WATERMARK_COMMITTED: frozenset(
        {
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
            CheckpointStatus.WATERMARK_COMMITTED,  # idempotent
        }
    ),
    CheckpointStatus.SUCCESS: frozenset({CheckpointStatus.SUCCESS, CheckpointStatus.WATERMARK_COMMITTED}),
    CheckpointStatus.EMPTY_CONFIRMED: frozenset(
        {CheckpointStatus.EMPTY_CONFIRMED, CheckpointStatus.WATERMARK_COMMITTED}
    ),
    CheckpointStatus.PARTIAL: frozenset(
        {
            CheckpointStatus.PENDING,
            CheckpointStatus.RAW_PERSISTED,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.RATE_LIMITED,
            CheckpointStatus.ERROR,
            CheckpointStatus.SUCCESS,
            CheckpointStatus.EMPTY_CONFIRMED,
        }
    ),
    CheckpointStatus.RATE_LIMITED: frozenset(
        {
            CheckpointStatus.PENDING,
            CheckpointStatus.RAW_PERSISTED,
            CheckpointStatus.RATE_LIMITED,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.ERROR,
            CheckpointStatus.SUCCESS,
        }
    ),
    CheckpointStatus.AUTH_BLOCKED: frozenset({CheckpointStatus.AUTH_BLOCKED, CheckpointStatus.ERROR, CheckpointStatus.PENDING}),
    CheckpointStatus.ERROR: frozenset(
        {
            CheckpointStatus.PENDING,
            CheckpointStatus.RAW_PERSISTED,
            CheckpointStatus.ERROR,
            CheckpointStatus.PARTIAL,
            CheckpointStatus.RATE_LIMITED,
            CheckpointStatus.SUCCESS,
        }
    ),
}


class InvalidCheckpointTransitionError(ValueError):
    """Raised when a checkpoint tries an illegal state change."""


# Backward-compatible alias
InvalidCheckpointTransition = InvalidCheckpointTransitionError


def parse_checkpoint_status(value: str | CheckpointStatus) -> CheckpointStatus:
    if isinstance(value, CheckpointStatus):
        return value
    try:
        return CheckpointStatus(str(value))
    except ValueError as exc:
        raise InvalidCheckpointTransition(f"status de checkpoint desconhecido: {value!r}") from exc


def validate_transition(current: str | CheckpointStatus, nxt: str | CheckpointStatus) -> CheckpointStatus:
    cur = parse_checkpoint_status(current)
    target = parse_checkpoint_status(nxt)
    if target == cur:
        return target
    allowed = ALLOWED_TRANSITIONS.get(cur, frozenset())
    if target not in allowed:
        raise InvalidCheckpointTransition(f"transicao invalida: {cur.value} -> {target.value}")
    return target


def stage_rank(status: str | CheckpointStatus) -> int:
    parsed = parse_checkpoint_status(status)
    try:
        return _STAGE_ORDER.index(parsed)
    except ValueError:
        if parsed in _FAILURE_TERMINALS:
            return -1
        if parsed.completed_terminal:
            return len(_STAGE_ORDER)
        return -1


def is_pending_operational(status: str | CheckpointStatus) -> bool:
    parsed = parse_checkpoint_status(status)
    return not parsed.operational_complete and parsed not in {
        CheckpointStatus.WATERMARK_COMMITTED,
        CheckpointStatus.SUCCESS,
        CheckpointStatus.EMPTY_CONFIRMED,
    }
