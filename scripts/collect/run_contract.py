"""Uniform collection/run contract for weekly operational cycles.

Inspired by Open Contracting Kingfisher (collection id + raw isolation),
adapted to Extra's existing `pipeline_runs` table and crawlers.

Terminal statuses are explicit. Absence of error is NOT success.
Cache hit is NOT a fresh collection. Interrupted runs are failure unless
the caller proves a partial scope with counts.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from scripts.crawl.run_evidence import get_git_meta, new_run_id, sha256_json

TerminalStatus = Literal[
    "success",
    "success_zero",
    "partial",
    "failure",
    "blocked",
    "reused_fresh",
    "running",
]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "success",
        "success_zero",
        "partial",
        "failure",
        "blocked",
        "reused_fresh",
    }
)

# Map our terminal status → pipeline_runs.status (legacy column)
_PIPELINE_STATUS_MAP: dict[str, str] = {
    "success": "completed",
    "success_zero": "completed",
    "partial": "partial",
    "failure": "failed",
    "blocked": "failed",
    "reused_fresh": "completed",
    "running": "running",
}


def new_collection_id(source: str = "weekly") -> str:
    """Stable collection id shared by all runs of one weekly cycle."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    safe = (source or "weekly").strip().replace(" ", "_")[:32] or "weekly"
    return f"col-{safe}-{stamp}-{short}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def classify_terminal_status(
    *,
    request_completed: bool,
    records_fetched: int,
    records_persisted: int,
    scope_complete: bool,
    source_available: bool,
    interrupted: bool = False,
    reused_within_sla: bool = False,
    error: str | None = None,
) -> TerminalStatus:
    """Fail-closed classification of a collection attempt.

    Rules:
    - reused_within_sla → reused_fresh (explicit reuse, not a new collect)
    - source unavailable → blocked
    - interrupted without completed request → failure
    - request not completed → failure
    - error with some persisted → partial only if request completed and scope incomplete
    - zero results only if request completed, scope complete, no error → success_zero
    - positive persisted + complete → success
    - positive but incomplete scope → partial
    """
    if reused_within_sla:
        return "reused_fresh"
    if not source_available:
        return "blocked"
    if interrupted and not request_completed:
        return "failure"
    if not request_completed:
        return "failure"
    if error and records_persisted <= 0 and records_fetched <= 0:
        return "failure"
    if records_fetched == 0 and records_persisted == 0:
        if scope_complete and not error:
            return "success_zero"
        return "failure" if error else "partial"
    if scope_complete and not error:
        return "success"
    if records_persisted > 0 or records_fetched > 0:
        return "partial"
    return "failure"


@dataclass
class CollectionRun:
    """Canonical execution record for one source collection attempt."""

    run_id: str
    collection_id: str
    source: str
    collector_version: str
    parameters: dict[str, Any] = field(default_factory=dict)
    period_start: str | None = None  # ISO date
    period_end: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    terminal_status: TerminalStatus = "running"
    records_obtained: int = 0
    records_rejected: int = 0
    records_persisted: int = 0
    watermark: str | None = None
    raw_uri: str | None = None
    content_hashes: list[str] = field(default_factory=list)
    terminal_error: str | None = None
    request_completed: bool = False
    scope_complete: bool = False
    source_available: bool = True
    mode: str = "incremental"
    git_sha: str | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        *,
        source: str,
        collection_id: str,
        collector_version: str,
        parameters: dict[str, Any] | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        mode: str = "incremental",
        run_id: str | None = None,
    ) -> CollectionRun:
        meta = get_git_meta()
        return cls(
            run_id=run_id or new_run_id(f"collect-{source}"),
            collection_id=collection_id,
            source=source,
            collector_version=collector_version,
            parameters=dict(parameters or {}),
            period_start=period_start,
            period_end=period_end,
            started_at=_utc_now().isoformat().replace("+00:00", "Z"),
            mode=mode,
            git_sha=meta.get("git_sha"),
        )

    def finish(
        self,
        *,
        records_obtained: int = 0,
        records_rejected: int = 0,
        records_persisted: int = 0,
        watermark: str | None = None,
        raw_uri: str | None = None,
        content_hashes: list[str] | None = None,
        request_completed: bool = False,
        scope_complete: bool = False,
        source_available: bool = True,
        interrupted: bool = False,
        reused_within_sla: bool = False,
        error: str | None = None,
        notes: list[str] | None = None,
    ) -> TerminalStatus:
        self.records_obtained = int(records_obtained)
        self.records_rejected = int(records_rejected)
        self.records_persisted = int(records_persisted)
        self.watermark = watermark
        self.raw_uri = raw_uri
        if content_hashes is not None:
            self.content_hashes = list(content_hashes)
        self.request_completed = request_completed
        self.scope_complete = scope_complete
        self.source_available = source_available
        self.terminal_error = error
        if notes:
            self.notes.extend(notes)
        self.finished_at = _utc_now().isoformat().replace("+00:00", "Z")
        self.terminal_status = classify_terminal_status(
            request_completed=request_completed,
            records_fetched=self.records_obtained,
            records_persisted=self.records_persisted,
            scope_complete=scope_complete,
            source_available=source_available,
            interrupted=interrupted,
            reused_within_sla=reused_within_sla,
            error=error,
        )
        return self.terminal_status

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["contract_version"] = "1.0"
        d["payload_hash"] = sha256_json(
            {
                "run_id": self.run_id,
                "collection_id": self.collection_id,
                "source": self.source,
                "terminal_status": self.terminal_status,
                "records_obtained": self.records_obtained,
                "records_persisted": self.records_persisted,
                "raw_uri": self.raw_uri,
                "content_hashes": self.content_hashes,
            }
        )
        return d

    def is_consultive_ok(self) -> bool:
        """Whether this run can feed consultive products for its source."""
        return self.terminal_status in {"success", "success_zero", "reused_fresh", "partial"}


def persist_pipeline_run(conn: Any, run: CollectionRun) -> None:
    """Upsert into existing pipeline_runs; store extended fields in params JSONB."""
    params = {
        "collection_id": run.collection_id,
        "collector_version": run.collector_version,
        "parameters": run.parameters,
        "terminal_status": run.terminal_status,
        "records_obtained": run.records_obtained,
        "records_rejected": run.records_rejected,
        "records_persisted": run.records_persisted,
        "watermark": run.watermark,
        "raw_uri": run.raw_uri,
        "content_hashes": run.content_hashes,
        "terminal_error": run.terminal_error,
        "request_completed": run.request_completed,
        "scope_complete": run.scope_complete,
        "source_available": run.source_available,
        "git_sha": run.git_sha,
        "notes": run.notes,
        "contract_version": "1.0",
    }
    pipeline_status = _PIPELINE_STATUS_MAP.get(run.terminal_status, "failed")
    started = run.started_at
    finished = run.finished_at
    duration_ms = 0
    if started and finished:
        try:
            t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            duration_ms = max(0, int((t1 - t0).total_seconds() * 1000))
        except ValueError:
            duration_ms = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_runs (
                run_id, source, mode, params, started_at, completed_at, status,
                period_start, period_end,
                records_fetched, records_upserted, records_failed, records_dlq,
                duration_ms, error_message
            ) VALUES (
                %(run_id)s, %(source)s, %(mode)s, %(params)s::jsonb,
                %(started_at)s::timestamptz, %(completed_at)s::timestamptz, %(status)s,
                %(period_start)s::date, %(period_end)s::date,
                %(records_fetched)s, %(records_upserted)s, %(records_failed)s, %(records_dlq)s,
                %(duration_ms)s, %(error_message)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
                params = EXCLUDED.params,
                completed_at = EXCLUDED.completed_at,
                status = EXCLUDED.status,
                records_fetched = EXCLUDED.records_fetched,
                records_upserted = EXCLUDED.records_upserted,
                records_failed = EXCLUDED.records_failed,
                records_dlq = EXCLUDED.records_dlq,
                duration_ms = EXCLUDED.duration_ms,
                error_message = EXCLUDED.error_message
            """,
            {
                "run_id": run.run_id,
                "source": run.source,
                "mode": run.mode,
                "params": json.dumps(params, ensure_ascii=False, default=str),
                "started_at": started,
                "completed_at": finished,
                "status": pipeline_status,
                "period_start": run.period_start,
                "period_end": run.period_end,
                "records_fetched": run.records_obtained,
                "records_upserted": run.records_persisted,
                "records_failed": run.records_rejected,
                "records_dlq": 0,
                "duration_ms": duration_ms,
                "error_message": run.terminal_error,
            },
        )
    conn.commit()
