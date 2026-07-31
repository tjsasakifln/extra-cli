"""Human-gated commercial outcome ledger (no auto-attribution of key states)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.company_registry.paths import ensure_layout, registry_root

# Extended commercial states for this campaign (ledger-local + exportable)
LEDGER_STATES = (
    "NOT_REVIEWED",
    "APPROVED_FOR_CONTACT",
    "REJECTED",
    "DEFERRED",
    "CONTACTED",
    "REPLIED",
    "NO_REPLY",
    "MEETING_SCHEDULED",
    "QUALIFIED",
    "NOT_QUALIFIED",
    "PROPOSAL_SENT",
    "WON",
    "LOST",
    "DO_NOT_CONTACT",
)

# Must never be auto-assigned by machine without explicit human actor
HUMAN_ONLY_STATES = frozenset(
    {
        "APPROVED_FOR_CONTACT",
        "CONTACTED",
        "REPLIED",
        "MEETING_SCHEDULED",
        "WON",
    }
)

_TRANSITIONS: dict[str, set[str]] = {
    "NOT_REVIEWED": {
        "APPROVED_FOR_CONTACT",
        "REJECTED",
        "DEFERRED",
        "DO_NOT_CONTACT",
    },
    "APPROVED_FOR_CONTACT": {"CONTACTED", "DEFERRED", "REJECTED", "DO_NOT_CONTACT"},
    "REJECTED": {"NOT_REVIEWED", "DO_NOT_CONTACT"},
    "DEFERRED": {"APPROVED_FOR_CONTACT", "REJECTED", "NOT_REVIEWED", "DO_NOT_CONTACT"},
    "CONTACTED": {
        "REPLIED",
        "NO_REPLY",
        "MEETING_SCHEDULED",
        "REJECTED",
        "DO_NOT_CONTACT",
    },
    "REPLIED": {
        "MEETING_SCHEDULED",
        "QUALIFIED",
        "NOT_QUALIFIED",
        "LOST",
        "DO_NOT_CONTACT",
    },
    "NO_REPLY": {"CONTACTED", "LOST", "DO_NOT_CONTACT", "DEFERRED"},
    "MEETING_SCHEDULED": {
        "QUALIFIED",
        "NOT_QUALIFIED",
        "PROPOSAL_SENT",
        "LOST",
        "DO_NOT_CONTACT",
    },
    "QUALIFIED": {"PROPOSAL_SENT", "LOST", "DO_NOT_CONTACT"},
    "NOT_QUALIFIED": {"DO_NOT_CONTACT", "NOT_REVIEWED"},
    "PROPOSAL_SENT": {"WON", "LOST", "DO_NOT_CONTACT"},
    "WON": {"DO_NOT_CONTACT"},
    "LOST": {"NOT_REVIEWED", "DO_NOT_CONTACT"},
    "DO_NOT_CONTACT": set(),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ledger_db_path() -> Path:
    ensure_layout()
    return registry_root() / "commercial_outcome_ledger.sqlite"


def connect_ledger(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else ledger_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outcome_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj14 TEXT NOT NULL,
            actor TEXT NOT NULL,
            ts TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            channel TEXT,
            campaign TEXT,
            template TEXT,
            observation TEXT,
            next_step TEXT,
            follow_up_date TEXT,
            rejection_or_loss_reason TEXT,
            registry_release_id TEXT,
            score_version TEXT,
            human_confirmed INTEGER NOT NULL DEFAULT 0,
            payload TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outcome_cnpj ON outcome_events(cnpj14);
        CREATE INDEX IF NOT EXISTS idx_outcome_ts ON outcome_events(ts);
        """
    )
    return conn


def latest_state(conn: sqlite3.Connection, cnpj14: str) -> str:
    row = conn.execute(
        """
        SELECT to_state FROM outcome_events
        WHERE cnpj14 = ?
        ORDER BY id DESC LIMIT 1
        """,
        (cnpj14,),
    ).fetchone()
    return str(row["to_state"]) if row else "NOT_REVIEWED"


def record_transition(
    *,
    cnpj14: str,
    to_state: str,
    actor: str,
    human_confirmed: bool = False,
    channel: str | None = None,
    campaign: str | None = None,
    template: str | None = None,
    observation: str | None = None,
    next_step: str | None = None,
    follow_up_date: str | None = None,
    rejection_or_loss_reason: str | None = None,
    registry_release_id: str | None = None,
    score_version: str | None = None,
    force: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    to_state = to_state.strip().upper()
    if to_state not in LEDGER_STATES:
        raise ValueError(f"invalid_state:{to_state}")
    if not actor or not str(actor).strip():
        raise ValueError("actor_required")
    if to_state in HUMAN_ONLY_STATES and not human_confirmed and not force:
        raise PermissionError(
            f"human_only_state_requires_confirmation:{to_state}"
        )
    # Machine must never claim human_confirmed for auto paths
    if actor.strip().lower() in {"system", "auto", "bot", "machine"} and to_state in HUMAN_ONLY_STATES:
        raise PermissionError(f"machine_actor_forbidden_for:{to_state}")

    conn = connect_ledger(db_path)
    try:
        prev = latest_state(conn, cnpj14)
        allowed = _TRANSITIONS.get(prev, set())
        if to_state != prev and to_state not in allowed and not force:
            raise ValueError(f"invalid_transition:{prev}->{to_state}")
        ts = utc_now()
        cur = conn.execute(
            """
            INSERT INTO outcome_events (
                cnpj14, actor, ts, from_state, to_state, channel, campaign, template,
                observation, next_step, follow_up_date, rejection_or_loss_reason,
                registry_release_id, score_version, human_confirmed, payload
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                cnpj14,
                actor.strip(),
                ts,
                prev,
                to_state,
                channel,
                campaign,
                template,
                observation,
                next_step,
                follow_up_date,
                rejection_or_loss_reason,
                registry_release_id,
                score_version,
                1 if human_confirmed else 0,
                json.dumps({"force": force}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return {
            "ok": True,
            "id": cur.lastrowid,
            "cnpj14": cnpj14,
            "from_state": prev,
            "to_state": to_state,
            "actor": actor.strip(),
            "ts": ts,
            "human_confirmed": human_confirmed,
        }
    finally:
        conn.close()


def feedback_metrics(db_path: Path | str | None = None) -> dict[str, Any]:
    """Deterministic counters — no opaque model, no invented performance claims."""
    conn = connect_ledger(db_path)
    try:
        rows = conn.execute(
            "SELECT to_state, COUNT(*) AS n FROM outcome_events GROUP BY to_state"
        ).fetchall()
        by_state = {r["to_state"]: int(r["n"]) for r in rows}
        total = sum(by_state.values())
        rejections = conn.execute(
            """
            SELECT rejection_or_loss_reason AS reason, COUNT(*) AS n
            FROM outcome_events
            WHERE to_state IN ('REJECTED','LOST','NOT_QUALIFIED')
              AND rejection_or_loss_reason IS NOT NULL
            GROUP BY rejection_or_loss_reason
            ORDER BY n DESC
            """
        ).fetchall()
        return {
            "schema_version": "outcome-feedback-v1",
            "generated_at": utc_now(),
            "events_total": total,
            "by_state": by_state,
            "rejection_loss_reasons": [
                {"reason": r["reason"], "n": int(r["n"])} for r in rejections
            ],
            "human_only_states": sorted(HUMAN_ONLY_STATES),
            "note": (
                "Rates are descriptive counters only. "
                "Do not declare commercial precision without volume + human labels."
            ),
            "min_volume_for_performance_claims": 30,
            "performance_claims_allowed": total >= 30,
        }
    finally:
        conn.close()
