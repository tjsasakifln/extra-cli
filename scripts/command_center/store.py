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


# Explicit job lifecycle sets (shared by Store CAS + JobRunner).
NON_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        JobState.QUEUED.value,
        JobState.VALIDATING.value,
        JobState.RUNNING.value,
        JobState.CANCELLING.value,
    }
)
TERMINAL_STATES: frozenset[str] = frozenset(
    {
        JobState.CANCELLED.value,
        JobState.SUCCEEDED.value,
        JobState.SUCCEEDED_WITH_WARNINGS.value,
        JobState.PARTIAL.value,
        JobState.FAILED.value,
        JobState.TIMED_OUT.value,
        JobState.BLOCKED_EXTERNAL.value,
        JobState.BLOCKED_HUMAN.value,
        JobState.UNAVAILABLE.value,
    }
)


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
    # Consulting workspace filter (not a full CRM)
    workspace_id: str | None = None
    client_id: str | None = None
    project_id: str | None = None

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        # params already sanitized at write time
        return d


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of an atomic job transition."""

    record: JobRecord | None
    outcome: str  # applied | already_terminal | cancel_wins | state_mismatch | missing
    applied: bool
    terminal_confirmed: bool


# Known consulting workspaces for filter UI
CONSULTING_WORKSPACES: list[dict[str, str]] = [
    {
        "id": "extra-construtora",
        "label": "Extra Construtora",
        "client_id": "extra-construtora",
    },
    {
        "id": "confenge-suppliers",
        "label": "CONFENGE — Prospecção de Fornecedores",
        "client_id": "confenge-suppliers",
    },
    {
        "id": "confenge-agencies",
        "label": "CONFENGE — Órgãos Públicos",
        "client_id": "confenge-agencies",
    },
    {
        "id": "process-documents",
        "label": "Documentos de processos",
        "client_id": "process-documents",
    },
]


def workspace_for_capability(capability_id: str, params: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    """Map capability/workflow id → (workspace_id, client_id)."""
    params = params or {}
    if params.get("workspace_id"):
        wid = str(params["workspace_id"])
        for w in CONSULTING_WORKSPACES:
            if w["id"] == wid:
                return w["id"], w["client_id"]
        return wid, str(params.get("client_id") or wid)
    cid = str(capability_id or "")
    if cid.startswith("workflow.extra") or cid.startswith("extra."):
        return "extra-construtora", "extra-construtora"
    if "public_agencies" in cid or "public-agencies" in cid or cid.startswith("confenge.public"):
        return "confenge-agencies", "confenge-agencies"
    if "suppliers" in cid or cid.startswith("confenge."):
        return "confenge-suppliers", "confenge-suppliers"
    if "process_documents" in cid:
        return "process-documents", "process-documents"
    return None, None


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
                CREATE INDEX IF NOT EXISTS idx_review_items_status_ts
                    ON review_items(status, ts DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_review_items_job_id_unique
                    ON review_items(job_id)
                    WHERE job_id IS NOT NULL AND job_id != '';
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    meta TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    client_front TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    meta TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
                );
                CREATE INDEX IF NOT EXISTS idx_projects_ws ON projects(workspace_id);
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
        """Persist job; never lose cancel_requested; never overwrite terminal via blind write.

        Terminal status changes must go through ``transition_job``. This method
        preserves an existing terminal status and sticky cancel flag.
        """
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (rec.job_id,)).fetchone()
            if row:
                existing = JobRecord(**json.loads(row["payload"]))
                if existing.cancel_requested:
                    rec.cancel_requested = True
                if existing.status in TERMINAL_STATES:
                    # Terminal immutability — keep existing terminal snapshot
                    return existing
                if rec.cancel_requested and rec.status in TERMINAL_STATES and rec.status != JobState.CANCELLED.value:
                    rec.status = JobState.CANCELLED.value
            conn.execute(
                "UPDATE jobs SET payload = ? WHERE job_id = ?",
                (json.dumps(asdict(rec), ensure_ascii=False), rec.job_id),
            )
        return rec

    def patch_job(self, job_id: str, **fields: Any) -> JobRecord | None:
        """Atomic field merge under lock.

        Non-terminal field patches only. Terminal status writes must use
        ``transition_job`` so cancel-wins and terminal immutability hold.
        If ``status`` is terminal, this method routes through ``transition_job``.
        """
        status = fields.get("status")
        if status is not None and str(status) in TERMINAL_STATES:
            result = self.transition_job(
                job_id,
                expected_states=NON_TERMINAL_STATES,
                target_state=str(status),
                fields={k: v for k, v in fields.items() if k != "status"},
                cancel_wins=True,
            )
            return result.record
        with self._lock, self._conn() as conn:
            return self._patch_job_unlocked(conn, job_id, **fields)

    def _patch_job_unlocked(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        **fields: Any,
    ) -> JobRecord | None:
        """Merge fields under an already-held lock + open connection.

        Never demotes or overwrites a terminal status. Sticky cancel is preserved.
        If cancel is pending and the patch tries to move to a non-CANCELLING
        non-terminal state, force CANCELLING.
        """
        row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        current_status = str(data.get("status") or "")
        if current_status in TERMINAL_STATES:
            # Terminal immutability — return existing snapshot unchanged
            return JobRecord(**data)

        # cancel_requested is sticky: True once set; never false→false reverse
        if data.get("cancel_requested") or fields.get("cancel_requested"):
            fields = {**fields, "cancel_requested": True}
        elif "cancel_requested" in fields and not fields.get("cancel_requested"):
            fields = {**fields, "cancel_requested": bool(data.get("cancel_requested"))}

        cancel_requested = bool(data.get("cancel_requested")) or bool(fields.get("cancel_requested"))
        new_status = fields.get("status", current_status)
        if cancel_requested and new_status not in (
            JobState.CANCELLING.value,
            JobState.CANCELLED.value,
        ):
            if str(new_status) in TERMINAL_STATES:
                # Should have been routed via transition_job; force cancel
                fields = {**fields, "status": JobState.CANCELLED.value}
            else:
                fields = {
                    **fields,
                    "status": JobState.CANCELLING.value,
                    "human_message": fields.get("human_message")
                    or "Cancelamento solicitado — aguardando o processo encerrar.",
                }

        data.update(fields)
        if cancel_requested:
            data["cancel_requested"] = True
        rec = JobRecord(**{k: v for k, v in data.items() if k in JobRecord.__dataclass_fields__})
        # SQL CAS: only update while still non-terminal
        non_term = sorted(NON_TERMINAL_STATES)
        placeholders = ",".join("?" for _ in non_term)
        payload = json.dumps(asdict(rec), ensure_ascii=False)
        cur = conn.execute(
            f"UPDATE jobs SET payload = ? WHERE job_id = ? "
            f"AND json_extract(payload, '$.status') IN ({placeholders})",
            (payload, job_id, *non_term),
        )
        if cur.rowcount != 1:
            row2 = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row2:
                return None
            return JobRecord(**json.loads(row2["payload"]))
        return rec

    def transition_job(
        self,
        job_id: str,
        *,
        expected_states: set[str] | frozenset[str] | None = None,
        target_state: str | None = None,
        fields: dict[str, Any] | None = None,
        cancel_wins: bool = True,
    ) -> TransitionResult:
        """Compare-and-set job transition with cancel precedence and terminal immutability.

        Rules:
        - ``cancel_requested`` is monotonic (false → true only).
        - If ``cancel_requested`` is true before a terminal write and ``cancel_wins``,
          the final state is forced to CANCELLED.
        - Terminal states are never replaced by another terminal state.
        - Only a successful applied transition may emit terminal side-effects
          (caller must check ``applied`` / ``terminal_confirmed``).
        """
        fields = dict(fields or {})
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return TransitionResult(None, "missing", applied=False, terminal_confirmed=False)

            data = json.loads(row["payload"])
            current_status = str(data.get("status") or "")
            cancel_requested = bool(data.get("cancel_requested")) or bool(fields.get("cancel_requested"))

            # Monotonic cancel flag
            if cancel_requested:
                fields["cancel_requested"] = True

            # Terminal immutability: never replace a confirmed terminal state
            if current_status in TERMINAL_STATES:
                rec = JobRecord(**data)
                return TransitionResult(
                    rec,
                    "already_terminal",
                    applied=False,
                    terminal_confirmed=True,
                )

            if expected_states is not None and current_status not in expected_states:
                rec = JobRecord(**data)
                return TransitionResult(
                    rec,
                    "state_mismatch",
                    applied=False,
                    terminal_confirmed=False,
                )

            resolved_target = target_state if target_state is not None else current_status
            outcome = "applied"

            # Cancel wins over any non-CANCELLED terminal outcome
            if (
                cancel_wins
                and cancel_requested
                and resolved_target in TERMINAL_STATES
                and resolved_target != JobState.CANCELLED.value
            ):
                resolved_target = JobState.CANCELLED.value
                fields.setdefault("technical_code", "CANCELLED")
                fields.setdefault(
                    "human_message",
                    "Cancelado por você antes de concluir.",
                )
                fields.setdefault("attention", "attention")
                outcome = "cancel_wins"
            elif cancel_wins and cancel_requested and resolved_target == JobState.CANCELLING.value:
                # stay in CANCELLING until worker confirms terminal CANCELLED
                pass
            elif (
                cancel_wins
                and cancel_requested
                and resolved_target not in TERMINAL_STATES
                and resolved_target != JobState.CANCELLING.value
            ):
                # Non-terminal transition while cancel pending → CANCELLING
                resolved_target = JobState.CANCELLING.value
                fields.setdefault(
                    "human_message",
                    "Cancelamento solicitado — aguardando o processo encerrar.",
                )
                fields.setdefault("attention", "running")
                outcome = "cancel_wins"

            if target_state is not None or "status" in fields:
                fields["status"] = resolved_target

            # First terminal write stamps finished_at if caller omitted it
            becoming_terminal = resolved_target in TERMINAL_STATES
            if becoming_terminal and not fields.get("finished_at") and not data.get("finished_at"):
                fields["finished_at"] = _utcnow()

            data.update(fields)
            # Enforce sticky cancel again after merge
            if cancel_requested:
                data["cancel_requested"] = True
            if becoming_terminal and cancel_requested and cancel_wins:
                data["status"] = JobState.CANCELLED.value
                outcome = "cancel_wins" if resolved_target != JobState.CANCELLED.value or outcome == "cancel_wins" else outcome
                if data["status"] == JobState.CANCELLED.value:
                    data.setdefault("technical_code", data.get("technical_code") or "CANCELLED")
                    data.setdefault(
                        "human_message",
                        data.get("human_message") or "Cancelado por você antes de concluir.",
                    )

            # Conditional UPDATE: only if still non-terminal (CAS via JSON status)
            new_payload = json.dumps(asdict(JobRecord(**{k: v for k, v in data.items() if k in JobRecord.__dataclass_fields__})), ensure_ascii=False)
            # Build expected-status guard for SQL-level CAS
            if expected_states is not None:
                placeholders = ",".join("?" for _ in expected_states)
                sql = (
                    f"UPDATE jobs SET payload = ? WHERE job_id = ? "
                    f"AND json_extract(payload, '$.status') IN ({placeholders})"
                )
                cur = conn.execute(sql, (new_payload, job_id, *sorted(expected_states)))
            else:
                # Still refuse if concurrent terminal won
                non_term = sorted(NON_TERMINAL_STATES)
                placeholders = ",".join("?" for _ in non_term)
                sql = (
                    f"UPDATE jobs SET payload = ? WHERE job_id = ? "
                    f"AND json_extract(payload, '$.status') IN ({placeholders})"
                )
                cur = conn.execute(sql, (new_payload, job_id, *non_term))

            if cur.rowcount != 1:
                # Re-read winner
                row2 = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                if not row2:
                    return TransitionResult(None, "missing", applied=False, terminal_confirmed=False)
                winner = JobRecord(**json.loads(row2["payload"]))
                return TransitionResult(
                    winner,
                    "already_terminal" if winner.status in TERMINAL_STATES else "state_mismatch",
                    applied=False,
                    terminal_confirmed=winner.status in TERMINAL_STATES,
                )

            rec = JobRecord(**json.loads(new_payload))
            return TransitionResult(
                rec,
                outcome,
                applied=True,
                terminal_confirmed=rec.status in TERMINAL_STATES,
            )

    def request_cancel(self, job_id: str) -> TransitionResult:
        """Idempotent sticky cancel request with CAS.

        - Already CANCELLED → already_terminal (idempotent success for cancel API)
        - Other terminal → already_terminal (not cancelable)
        - Non-terminal → cancel_requested=True, status=CANCELLING
        """
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return TransitionResult(None, "missing", applied=False, terminal_confirmed=False)
            data = json.loads(row["payload"])
            current = str(data.get("status") or "")
            if current in TERMINAL_STATES:
                rec = JobRecord(**data)
                return TransitionResult(
                    rec,
                    "already_terminal",
                    applied=False,
                    terminal_confirmed=True,
                )
            data["cancel_requested"] = True
            data["status"] = JobState.CANCELLING.value
            data["human_message"] = "Cancelamento solicitado — aguardando o processo encerrar."
            data["attention"] = "running"
            rec = JobRecord(**{k: v for k, v in data.items() if k in JobRecord.__dataclass_fields__})
            payload = json.dumps(asdict(rec), ensure_ascii=False)
            non_term = sorted(NON_TERMINAL_STATES)
            placeholders = ",".join("?" for _ in non_term)
            cur = conn.execute(
                f"UPDATE jobs SET payload = ? WHERE job_id = ? "
                f"AND json_extract(payload, '$.status') IN ({placeholders})",
                (payload, job_id, *non_term),
            )
            if cur.rowcount != 1:
                row2 = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                if not row2:
                    return TransitionResult(None, "missing", applied=False, terminal_confirmed=False)
                winner = JobRecord(**json.loads(row2["payload"]))
                return TransitionResult(
                    winner,
                    "already_terminal" if winner.status in TERMINAL_STATES else "state_mismatch",
                    applied=False,
                    terminal_confirmed=winner.status in TERMINAL_STATES,
                )
            return TransitionResult(rec, "applied", applied=True, terminal_confirmed=False)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        return JobRecord(**data)

    def list_jobs(
        self,
        limit: int = 50,
        status: str | None = None,
        workspace_id: str | None = None,
        client_id: str | None = None,
    ) -> list[JobRecord]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM jobs ORDER BY rowid DESC LIMIT ?",
                (max(1, min(limit * 5 if workspace_id or client_id else limit, 2000)),),
            ).fetchall()
        jobs: list[JobRecord] = []
        for r in rows:
            data = json.loads(r["payload"])
            # Backfill workspace from capability for legacy rows
            if not data.get("workspace_id"):
                wid, cid = workspace_for_capability(str(data.get("capability_id") or ""), data.get("params") or {})
                data["workspace_id"] = wid
                data["client_id"] = data.get("client_id") or cid
            try:
                jobs.append(JobRecord(**{k: v for k, v in data.items() if k in JobRecord.__dataclass_fields__}))
            except TypeError:
                continue
        if status:
            jobs = [j for j in jobs if j.status == status]
        if workspace_id:
            jobs = [j for j in jobs if j.workspace_id == workspace_id]
        if client_id:
            jobs = [j for j in jobs if j.client_id == client_id]
        return jobs[: max(1, min(limit, 500))]

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
                d["payload"] = {}
            # surface obsolete flag stored on payload
            payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            d["obsolete"] = bool(payload.get("obsolete"))
            d["obsolete_reason"] = payload.get("obsolete_reason")
            d["artifact_hashes"] = payload.get("artifact_hashes") or {}
            out.append(d)
        return out

    def patch_decision_payload(self, decision_id: str, **fields: Any) -> dict[str, Any] | None:
        """Merge fields into a decision's JSON payload (e.g. obsolete flag)."""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT id, ts, item_id, decision, rationale, actor, confirmation, payload FROM human_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                payload = json.loads(d.get("payload") or "{}")
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            payload.update(fields)
            conn.execute(
                "UPDATE human_decisions SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), decision_id),
            )
            d["payload"] = payload
            d["obsolete"] = bool(payload.get("obsolete"))
            return d

    def mark_accepts_obsolete_for_item(
        self,
        item_id: str,
        *,
        current_hashes: dict[str, str],
        reason: str = "artifact_hash_changed",
    ) -> list[str]:
        """Mark ACCEPT decisions obsolete when presented hashes no longer match current."""
        from scripts.command_center.review_rules import decision_is_obsolete

        marked: list[str] = []
        for d in self.list_decisions(limit=200):
            if d.get("item_id") != item_id:
                continue
            if str(d.get("decision", "")).upper() != "ACCEPT":
                continue
            if d.get("obsolete"):
                continue
            stored = d.get("artifact_hashes") or {}
            if decision_is_obsolete(stored_hashes=stored, current_hashes=current_hashes):
                self.patch_decision_payload(
                    d["id"],
                    obsolete=True,
                    obsolete_reason=reason,
                    obsolete_at=_utcnow(),
                    current_hashes_at_invalidation=current_hashes,
                )
                marked.append(str(d["id"]))
        return marked

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
        """Idempotent enqueue. Safe under concurrent callers (unique job_id + IntegrityError recovery)."""
        rid = item_id or str(uuid.uuid4())
        with self._lock, self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM review_items WHERE id = ? OR (job_id IS NOT NULL AND job_id = ? AND job_id != '')",
                (rid, job_id or ""),
            ).fetchone()
            if existing:
                return str(existing["id"])
            try:
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
            except sqlite3.IntegrityError:
                # Concurrent insert won the race — return existing row (unique job_id / pk)
                row = conn.execute(
                    "SELECT id FROM review_items WHERE id = ? OR (job_id IS NOT NULL AND job_id = ? AND job_id != '')",
                    (rid, job_id or ""),
                ).fetchone()
                if row:
                    return str(row["id"])
                raise
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

    def list_reviews(
        self,
        status: str | None = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 200))
        off = max(0, int(offset))
        with self._lock, self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload
                    FROM review_items WHERE status = ? ORDER BY ts DESC LIMIT ? OFFSET ?
                    """,
                    (status, lim, off),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, ts, title, source, evidence, limitations, risks, status, job_id, capability_id, payload
                    FROM review_items ORDER BY ts DESC LIMIT ? OFFSET ?
                    """,
                    (lim, off),
                ).fetchall()
        return [self._row_to_review(r) for r in rows]

    def count_reviews(self, status: str | None = "pending") -> int:
        """Cheap COUNT for badge/home totals — never loads full rows."""
        with self._lock, self._conn() as conn:
            if status:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM review_items WHERE status = ?",
                    (status,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS c FROM review_items").fetchone()
        return int(row["c"] if row else 0)

    def reconcile_blocked_human_reviews(self, *, actor: str = "system") -> dict[str, Any]:
        """Idempotent enqueue for BLOCKED_HUMAN jobs. Safe under concurrent calls."""
        created = 0
        jobs = self.list_jobs(limit=200)
        for j in jobs:
            if j.status != "BLOCKED_HUMAN":
                continue
            before = self.count_reviews(status="pending")
            rid = self.enqueue_review(
                title=f"Revisão necessária: {j.action}",
                source=j.capability_id,
                evidence=(
                    f"Job {j.job_id}; status {j.status}; "
                    f"código {j.technical_code}; artifacts: {(j.artifacts or [])[:5]}"
                ),
                limitations=j.human_message
                or "Automação concluída, mas a decisão humana ainda é necessária.",
                risks="Aceitar sem evidência pode propagar classificação incorreta.",
                job_id=j.job_id,
                capability_id=j.capability_id,
                payload={"from_job": True, "technical_code": j.technical_code},
            )
            after = self.count_reviews(status="pending")
            if after > before:
                created += 1
                self.audit(
                    actor,
                    "review.reconcile",
                    {"id": rid, "job_id": j.job_id, "created": True},
                )
        return {
            "created": created,
            "total_pending": self.count_reviews(status="pending"),
        }

    def mark_review_decided(self, item_id: str, decision: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE review_items SET status = ? WHERE id = ?",
                (f"decided:{decision}", item_id),
            )

    # --- Local product model: Workspace / Project (Command Center SQLite only) ---

    def ensure_default_workspace(self) -> dict[str, Any]:
        """Idempotent default consulting workspace + client fronts as projects."""
        existing = self.list_workspaces()
        if existing:
            return existing[0]
        ws = self.create_workspace("Consultoria Tiago")
        for name, front in (
            ("Extra Construtora", "extra"),
            ("CONFENGE fornecedores", "confenge_suppliers"),
            ("CONFENGE órgãos públicos", "confenge_public_agencies"),
            ("Análises documentais", "process_documents"),
        ):
            self.create_project(workspace_id=ws["id"], name=name, client_front=front)
        return ws

    def create_workspace(self, name: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        wid = str(uuid.uuid4())
        ts = _utcnow()
        payload = json.dumps(meta or {}, ensure_ascii=False)
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO workspaces(id, name, created_at, meta) VALUES (?,?,?,?)",
                (wid, name, ts, payload),
            )
        return {"id": wid, "name": name, "created_at": ts, "meta": meta or {}}

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at, meta FROM workspaces ORDER BY created_at ASC"
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except json.JSONDecodeError:
                d["meta"] = {}
            out.append(d)
        return out

    def create_project(
        self,
        *,
        workspace_id: str,
        name: str,
        client_front: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pid = str(uuid.uuid4())
        ts = _utcnow()
        payload = json.dumps(meta or {}, ensure_ascii=False)
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO projects(id, workspace_id, name, client_front, created_at, meta) VALUES (?,?,?,?,?,?)",
                (pid, workspace_id, name, client_front, ts, payload),
            )
        return {
            "id": pid,
            "workspace_id": workspace_id,
            "name": name,
            "client_front": client_front,
            "created_at": ts,
            "meta": meta or {},
        }

    def list_projects(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT id, workspace_id, name, client_front, created_at, meta FROM projects "
                    "WHERE workspace_id = ? ORDER BY created_at ASC",
                    (workspace_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, workspace_id, name, client_front, created_at, meta FROM projects "
                    "ORDER BY created_at ASC"
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except json.JSONDecodeError:
                d["meta"] = {}
            out.append(d)
        return out

