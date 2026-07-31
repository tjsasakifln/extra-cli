"""SQLite persistence for Command Center jobs, audit, preferences."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.command_center.status_normalize import JobState


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobRecord:
    job_id: str
    capability_id: str
    action: str
    params: dict[str, Any]
    status: str = JobState.QUEUED.value
    technical_code: str | None = None
    human_message: str | None = None
    attention: str | None = None
    next_action: str | None = None
    created_at: str = field(default_factory=_utcnow)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    pid: int | None = None
    exit_code: int | None = None
    canonical_command: list[str] = field(default_factory=list)
    stdout_path: str | None = None
    stderr_path: str | None = None
    run_id: str | None = None
    output_paths: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    blocker: str | None = None
    code_sha: str | None = None
    cancel_requested: bool = False

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        # params already sanitized at write time
        return d


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS human_decisions (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rationale TEXT,
                    actor TEXT NOT NULL,
                    confirmation TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_items (
                    id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    limitations TEXT NOT NULL,
                    risks TEXT NOT NULL,
                    status TEXT NOT NULL,
                    job_id TEXT,
                    capability_id TEXT,
                    payload TEXT
                );
                """
            )

    def create_job(self, rec: JobRecord) -> JobRecord:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs(job_id, payload) VALUES (?, ?)",
                (rec.job_id, json.dumps(asdict(rec), ensure_ascii=False)),
            )
        return rec

    def update_job(self, rec: JobRecord) -> JobRecord:
        """Persist job; never lose cancel_requested once set (merge, not blind overwrite)."""
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (rec.job_id,)).fetchone()
            if row:
                existing = JobRecord(**json.loads(row["payload"]))
                if existing.cancel_requested:
                    rec.cancel_requested = True
            conn.execute(
                "UPDATE jobs SET payload = ? WHERE job_id = ?",
                (json.dumps(asdict(rec), ensure_ascii=False), rec.job_id),
            )
        return rec

    def patch_job(self, job_id: str, **fields: Any) -> JobRecord | None:
        """Atomic field merge under lock — preferred for cancel and status transitions."""
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row["payload"])
            # cancel_requested is sticky: True once set
            if data.get("cancel_requested") and "cancel_requested" in fields:
                fields = {**fields, "cancel_requested": True}
            elif data.get("cancel_requested"):
                fields = {**fields, "cancel_requested": True}
            data.update(fields)
            rec = JobRecord(**data)
            conn.execute(
                "UPDATE jobs SET payload = ? WHERE job_id = ?",
                (json.dumps(asdict(rec), ensure_ascii=False), job_id),
            )
            return rec

    def request_cancel(self, job_id: str) -> JobRecord | None:
        """Set cancel flag and CANCELLING status without clobbering other fields."""
        return self.patch_job(
            job_id,
            cancel_requested=True,
            status=JobState.CANCELLING.value,
            human_message="Cancelamento solicitado — aguardando o processo encerrar.",
            attention="running",
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        return JobRecord(**data)

    def list_jobs(self, limit: int = 50, status: str | None = None) -> list[JobRecord]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM jobs ORDER BY rowid DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        jobs = [JobRecord(**json.loads(r["payload"])) for r in rows]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def active_jobs(self) -> list[JobRecord]:
        active = {
            JobState.QUEUED.value,
            JobState.VALIDATING.value,
            JobState.RUNNING.value,
            JobState.CANCELLING.value,
        }
        return [j for j in self.list_jobs(limit=200) if j.status in active]

    def append_log(self, job_id: str, stream: str, level: str, message: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO job_logs(job_id, ts, stream, level, message) VALUES (?,?,?,?,?)",
                (job_id, _utcnow(), stream, level, message),
            )

    def get_logs(self, job_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, stream, level, message
                FROM job_logs
                WHERE job_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (job_id, after_id, max(1, min(limit, 2000))),
            ).fetchall()
        return [dict(r) for r in rows]

    def audit(self, actor: str, action: str, detail: dict[str, Any] | str) -> None:
        payload = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO audit(ts, actor, action, detail) VALUES (?,?,?,?)",
                (_utcnow(), actor, action, payload),
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, actor, action, detail FROM audit ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_decision(
        self,
        *,
        item_id: str,
        decision: str,
        actor: str,
        rationale: str | None,
        confirmation: str | None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        decision_id = str(uuid.uuid4())
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO human_decisions(id, ts, item_id, decision, rationale, actor, confirmation, payload)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    decision_id,
                    _utcnow(),
                    item_id,
                    decision,
                    rationale,
                    actor,
                    confirmation,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
        return decision_id

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, item_id, decision, rationale, actor, confirmation, payload
                FROM human_decisions ORDER BY ts DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"] or "{}")
            except json.JSONDecodeError:
                pass
            out.append(d)
        return out

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_pref(self, key: str, value: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO preferences(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def job_counts(self) -> dict[str, int]:
        jobs = self.list_jobs(limit=500)
        counts: dict[str, int] = {}
        for j in jobs:
            counts[j.status] = counts.get(j.status, 0) + 1
        counts["total"] = len(jobs)
        counts["active"] = len(
            [
                j
                for j in jobs
                if j.status
                in {
                    JobState.QUEUED.value,
                    JobState.VALIDATING.value,
                    JobState.RUNNING.value,
                    JobState.CANCELLING.value,
                }
            ]
        )
        return counts

    def enqueue_review(
        self,
        *,
        title: str,
        source: str,
        evidence: str,
        limitations: str,
        risks: str,
        job_id: str | None = None,
        capability_id: str | None = None,
        payload: dict[str, Any] | None = None,
        item_id: str | None = None,
    ) -> str:
        rid = item_id or str(uuid.uuid4())
        with self._lock, self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM review_items WHERE id = ? OR (job_id IS NOT NULL AND job_id = ?)",
                (rid, job_id or ""),
            ).fetchone()
            if existing:
                return str(existing["id"])
            conn.execute(
                """
                INSERT INTO review_items(id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rid,
                    _utcnow(),
                    title,
                    source,
                    evidence,
                    limitations,
                    risks,
                    "pending",
                    job_id,
                    capability_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
        return rid

    def _row_to_review(self, r: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        return d

    def get_review(self, item_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload
                FROM review_items WHERE id = ?
                """,
                (item_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_review(row)

    def list_reviews(self, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload
                    FROM review_items WHERE status = ? ORDER BY ts DESC LIMIT ?
                    """,
                    (status, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload
                    FROM review_items ORDER BY ts DESC LIMIT ?
                    """,
                    (max(1, min(limit, 200)),),
                ).fetchall()
        return [self._row_to_review(r) for r in rows]

    def mark_review_decided(self, item_id: str, decision: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE review_items SET status = ? WHERE id = ?",
                (f"decided:{decision}", item_id),
            )
