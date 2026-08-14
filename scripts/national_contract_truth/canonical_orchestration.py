"""#293 — advance public facts to a canonical terminal without an operator.

Every input ends CANONICAL_READY or BLOCKED (poison → DLQ). Restart does
not duplicate work. The last valid revision stays servable while BUILDING.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

JobState = Literal["PENDING", "BUILDING", "CANONICAL_READY", "BLOCKED", "DLQ"]
TERMINAL: frozenset[str] = frozenset({"CANONICAL_READY", "BLOCKED", "DLQ"})


@dataclass(frozen=True)
class CanonicalJob:
    job_id: str
    input_hash: str
    state: JobState
    attempt: int
    poison: bool = False
    blocker: str | None = None
    last_valid_revision: str | None = None
    last_valid_at: datetime | None = None
    current_revision: str | None = None
    work_token: str | None = None


@dataclass(frozen=True)
class AdvanceResult:
    job: CanonicalJob
    http_or_ocr_scheduled: bool
    served_revision: str | None


def advance_fact(job: CanonicalJob, *, now: datetime, success: bool, reason: str | None = None) -> AdvanceResult:
    """Push one job toward a terminal. Already-terminal jobs are no-ops."""
    if job.state in TERMINAL:
        return AdvanceResult(job=job, http_or_ocr_scheduled=False, served_revision=job.last_valid_revision)
    if job.poison:
        parked = CanonicalJob(
            job_id=job.job_id,
            input_hash=job.input_hash,
            state="DLQ",
            attempt=job.attempt,
            poison=True,
            blocker=reason or "POISON_JOB",
            last_valid_revision=job.last_valid_revision,
            last_valid_at=job.last_valid_at,
            current_revision=job.current_revision,
            work_token=job.work_token,
        )
        return AdvanceResult(job=parked, http_or_ocr_scheduled=False, served_revision=job.last_valid_revision)
    if success:
        revision = job.current_revision or f"{job.input_hash}:{job.attempt}"
        ready = CanonicalJob(
            job_id=job.job_id,
            input_hash=job.input_hash,
            state="CANONICAL_READY",
            attempt=job.attempt,
            poison=False,
            blocker=None,
            last_valid_revision=revision,
            last_valid_at=now,
            current_revision=revision,
            work_token=job.work_token,
        )
        return AdvanceResult(job=ready, http_or_ocr_scheduled=False, served_revision=revision)
    blocked = CanonicalJob(
        job_id=job.job_id,
        input_hash=job.input_hash,
        state="BLOCKED",
        attempt=job.attempt,
        poison=False,
        blocker=reason or "STRUCTURED_BLOCKER",
        last_valid_revision=job.last_valid_revision,
        last_valid_at=job.last_valid_at,
        current_revision=job.current_revision,
        work_token=job.work_token,
    )
    return AdvanceResult(job=blocked, http_or_ocr_scheduled=False, served_revision=job.last_valid_revision)


def resume_job(job: CanonicalJob) -> AdvanceResult:
    """Restart must not reschedule HTTP/OCR for a terminal or already-tokened job."""
    if job.state in TERMINAL:
        return AdvanceResult(job=job, http_or_ocr_scheduled=False, served_revision=job.last_valid_revision)
    if job.work_token:
        return AdvanceResult(job=job, http_or_ocr_scheduled=False, served_revision=job.last_valid_revision)
    building = CanonicalJob(
        job_id=job.job_id,
        input_hash=job.input_hash,
        state="BUILDING",
        attempt=job.attempt + 1,
        poison=job.poison,
        blocker=None,
        last_valid_revision=job.last_valid_revision,
        last_valid_at=job.last_valid_at,
        current_revision=job.current_revision,
        work_token=f"{job.job_id}:{job.input_hash}:{job.attempt + 1}",
    )
    return AdvanceResult(job=building, http_or_ocr_scheduled=True, served_revision=job.last_valid_revision)


def invalidate_derivatives(changed_input_hash: str, jobs: list[CanonicalJob]) -> list[CanonicalJob]:
    """Document change invalidates only jobs whose input_hash matches."""
    updated: list[CanonicalJob] = []
    for job in jobs:
        if job.input_hash != changed_input_hash:
            updated.append(job)
            continue
        updated.append(
            CanonicalJob(
                job_id=job.job_id,
                input_hash=job.input_hash,
                state="PENDING",
                attempt=job.attempt,
                poison=False,
                blocker=None,
                last_valid_revision=job.last_valid_revision,
                last_valid_at=job.last_valid_at,
                current_revision=None,
                work_token=None,
            )
        )
    return updated
