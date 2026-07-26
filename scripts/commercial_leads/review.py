"""Commercial lead state transitions, human review and import/export."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads import COMMERCIAL_STATES
from scripts.commercial_leads.dbutil import connect, fetch_all

# Allowed transitions (from -> set of to). DO_NOT_CONTACT is absorbing.
_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {
        "REVIEWED",
        "QUALIFIED",
        "DISQUALIFIED",
        "CONTACTED",
        "DO_NOT_CONTACT",
    },
    "REVIEWED": {
        "QUALIFIED",
        "DISQUALIFIED",
        "CONTACTED",
        "DO_NOT_CONTACT",
        "REVIEWED",
    },
    "QUALIFIED": {
        "CONTACTED",
        "DISQUALIFIED",
        "DO_NOT_CONTACT",
        "MEETING",
        "PROPOSAL",
    },
    "DISQUALIFIED": {"REVIEWED", "DO_NOT_CONTACT"},
    "CONTACTED": {
        "REPLIED",
        "MEETING",
        "LOST",
        "DO_NOT_CONTACT",
        "DISQUALIFIED",
    },
    "REPLIED": {"MEETING", "PROPOSAL", "LOST", "DO_NOT_CONTACT"},
    "MEETING": {"PROPOSAL", "LOST", "WON", "DO_NOT_CONTACT"},
    "PROPOSAL": {"WON", "LOST", "MEETING", "DO_NOT_CONTACT"},
    "WON": {"DO_NOT_CONTACT"},
    "LOST": {"REVIEWED", "DO_NOT_CONTACT"},
    "DO_NOT_CONTACT": set(),  # absorbing
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_cnpj(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits


def validate_transition(from_status: str, to_status: str) -> None:
    if to_status not in COMMERCIAL_STATES:
        raise ValueError(f"invalid_to_status:{to_status}")
    if from_status not in COMMERCIAL_STATES:
        raise ValueError(f"invalid_from_status:{from_status}")
    if from_status == "DO_NOT_CONTACT" and to_status != "DO_NOT_CONTACT":
        raise ValueError("do_not_contact_is_absorbing")
    allowed = _TRANSITIONS.get(from_status, set())
    if to_status not in allowed and to_status != from_status:
        # Allow override path only when explicitly same or via override flag handled by caller
        raise ValueError(f"invalid_transition:{from_status}->{to_status}")


def get_latest_state(conn: Any, cnpj14: str) -> str:
    rows = fetch_all(
        conn,
        """
        SELECT new_state FROM commercial_lead_state_overrides
        WHERE cnpj14 = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (cnpj14,),
    )
    if rows:
        return str(rows[0]["new_state"])
    # fall back to latest lead row
    leads = fetch_all(
        conn,
        """
        SELECT commercial_state FROM commercial_leads
        WHERE cnpj14 = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (cnpj14,),
    )
    if leads:
        return str(leads[0]["commercial_state"])
    return "NEW"


def load_state_map(conn: Any) -> dict[str, str]:
    """Latest commercial_state per CNPJ14 from overrides (preferred) then leads.

    DO_NOT_CONTACT always wins when present in override history as the latest state.
    """
    out: dict[str, str] = {}
    # latest override per cnpj
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT ON (cnpj14) cnpj14, new_state
        FROM commercial_lead_state_overrides
        ORDER BY cnpj14, created_at DESC, id DESC
        """,
    )
    for r in rows:
        cnpj = str(r["cnpj14"])
        out[cnpj] = str(r["new_state"])
    # fill missing from latest lead rows
    lead_rows = fetch_all(
        conn,
        """
        SELECT DISTINCT ON (cnpj14) cnpj14, commercial_state
        FROM commercial_leads
        ORDER BY cnpj14, created_at DESC, id DESC
        """,
    )
    for r in lead_rows:
        cnpj = str(r["cnpj14"])
        if cnpj not in out:
            out[cnpj] = str(r["commercial_state"])
    return out


def apply_review(
    dsn: str,
    *,
    cnpj: str,
    status: str,
    reason: str,
    author: str,
    run_id: str | None = None,
    force_override: bool = False,
) -> dict[str, Any]:
    cnpj14 = normalize_cnpj(cnpj)
    if len(cnpj14) != 14:
        raise ValueError("cnpj14_required")
    if not reason or not str(reason).strip():
        raise ValueError("reason_required")
    if not author or not str(author).strip():
        raise ValueError("author_required")
    to_status = status.strip().upper()
    if to_status not in COMMERCIAL_STATES:
        raise ValueError(f"invalid_status:{to_status}")

    conn = connect(dsn)
    try:
        previous = get_latest_state(conn, cnpj14)
        if previous == "DO_NOT_CONTACT" and to_status != "DO_NOT_CONTACT":
            raise ValueError("do_not_contact_prevails")
        try:
            validate_transition(previous, to_status)
        except ValueError:
            if not force_override:
                raise
            if not reason.strip():
                raise ValueError("override_requires_reason") from None

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO commercial_lead_state_overrides (
                    cnpj14, author, previous_state, new_state, reason, run_id
                ) VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING id, created_at
                """,
                (cnpj14, author, previous, to_status, reason.strip(), run_id),
            )
            row = cur.fetchone()
            if row is None:
                event_id = None
                created_at = None
            elif isinstance(row, dict):
                event_id = row.get("id")
                created_at = row.get("created_at")
            else:
                event_id = row[0]
                created_at = row[1]
            # update latest leads rows for this cnpj (non-destructive history via overrides)
            cur.execute(
                """
                UPDATE commercial_leads
                SET commercial_state = %s
                WHERE cnpj14 = %s
                  AND id IN (
                    SELECT id FROM commercial_leads
                    WHERE cnpj14 = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                  )
                """,
                (to_status, cnpj14, cnpj14),
            )
            from psycopg2.extras import Json

            cur.execute(
                """
                INSERT INTO commercial_feedback_ledger (
                    run_id, cnpj14, event_type, payload, author
                ) VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    run_id,
                    cnpj14,
                    "STATE_CHANGE" if to_status != "REVIEWED" else "REVIEW",
                    Json(
                        {
                            "from_status": previous,
                            "to_status": to_status,
                            "reason": reason.strip(),
                            "force_override": force_override,
                            "event_id": event_id,
                        }
                    ),
                    author,
                ),
            )
        conn.commit()
        return {
            "ok": True,
            "event_id": event_id,
            "cnpj14": cnpj14,
            "from_status": previous,
            "to_status": to_status,
            "author": author,
            "reason": reason.strip(),
            "occurred_at": str(created_at or utc_now()),
            "run_id": run_id,
        }
    finally:
        conn.close()


def list_leads(
    dsn: str,
    *,
    limit: int = 20,
    changed_since_last_run: bool = False,
) -> dict[str, Any]:
    conn = connect(dsn)
    try:
        runs = fetch_all(
            conn,
            """
            SELECT run_id, as_of, status, profile_version, snapshot_hash, created_at
            FROM commercial_lead_runs
            ORDER BY created_at DESC
            LIMIT 2
            """,
        )
        if not runs:
            return {"ok": True, "leads": [], "runs": [], "note": "no_runs"}
        latest = runs[0]["run_id"]
        if changed_since_last_run and len(runs) >= 2:
            prev = runs[1]["run_id"]
            rows = fetch_all(
                conn,
                """
                SELECT l.*
                FROM commercial_leads l
                WHERE l.run_id = %s
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM commercial_leads p
                      WHERE p.run_id = %s AND p.cnpj14 = l.cnpj14
                    )
                    OR EXISTS (
                      SELECT 1 FROM commercial_leads p
                      WHERE p.run_id = %s AND p.cnpj14 = l.cnpj14
                        AND (
                          p.score_total IS DISTINCT FROM l.score_total
                          OR p.priority IS DISTINCT FROM l.priority
                          OR p.rank_position IS DISTINCT FROM l.rank_position
                        )
                    )
                  )
                ORDER BY l.rank_position NULLS LAST, l.score_total DESC
                LIMIT %s
                """,
                (latest, prev, prev, limit),
            )
            mode = "changed_since_last_run"
        else:
            rows = fetch_all(
                conn,
                """
                SELECT * FROM commercial_leads
                WHERE run_id = %s
                ORDER BY rank_position NULLS LAST, score_total DESC
                LIMIT %s
                """,
                (latest, limit),
            )
            mode = "latest_run"
        # overlay DO_NOT_CONTACT
        out = []
        for r in rows:
            cnpj14 = r["cnpj14"]
            state = get_latest_state(conn, cnpj14)
            item = dict(r)
            item["commercial_state"] = state
            if state == "DO_NOT_CONTACT":
                item["suppressed"] = True
            out.append(item)
        return {
            "ok": True,
            "mode": mode,
            "run_id": latest,
            "count": len(out),
            "leads": out,
            "runs": runs,
        }
    finally:
        conn.close()


def explain_lead(dsn: str, cnpj: str) -> dict[str, Any]:
    cnpj14 = normalize_cnpj(cnpj)
    conn = connect(dsn)
    try:
        rows = fetch_all(
            conn,
            """
            SELECT * FROM commercial_leads
            WHERE cnpj14 = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (cnpj14,),
        )
        if not rows:
            return {"ok": False, "error": "lead_not_found", "cnpj14": cnpj14}
        lead = dict(rows[0])
        lead["commercial_state"] = get_latest_state(conn, cnpj14)
        history = fetch_all(
            conn,
            """
            SELECT id, previous_state, new_state, author, reason, run_id, created_at
            FROM commercial_lead_state_overrides
            WHERE cnpj14 = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (cnpj14,),
        )
        return {
            "ok": True,
            "cnpj14": cnpj14,
            "lead": lead,
            "state_history": history,
            "language_note": (
                "Score e sinais são prioridade para revisão humana; "
                "não representam claim estatístico de conversão."
            ),
        }
    finally:
        conn.close()


def export_reviews_csv(dsn: str, path: str | Path) -> dict[str, Any]:
    data = list_leads(dsn, limit=500)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "cnpj14",
        "razao_social",
        "score_total",
        "priority",
        "commercial_state",
        "rank_position",
        "run_id",
        "suggested_offer",
        "next_human_step",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for lead in data.get("leads") or []:
            w.writerow(lead)
    return {"ok": True, "path": str(p), "count": data.get("count", 0)}


def import_reviews_csv(
    dsn: str,
    path: str | Path,
    *,
    author: str,
    default_run_id: str | None = None,
) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    applied: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get("human_status") or row.get("commercial_state") or "").strip()
            reason = (row.get("human_reason") or row.get("reason") or "").strip()
            cnpj = row.get("cnpj14") or ""
            if not status or not reason:
                conflicts.append({"row": row, "error": "missing_status_or_reason"})
                continue
            try:
                res = apply_review(
                    dsn,
                    cnpj=cnpj,
                    status=status,
                    reason=reason,
                    author=row.get("reviewer") or author,
                    run_id=row.get("run_id") or default_run_id,
                    force_override=str(row.get("force_override") or "").lower() in {"1", "true", "yes"},
                )
                applied.append(res)
            except Exception as exc:  # noqa: BLE001 — collect conflicts
                conflicts.append({"cnpj14": cnpj, "error": str(exc), "row": row})
    return {
        "ok": len(conflicts) == 0,
        "applied": len(applied),
        "conflicts": conflicts,
        "results": applied,
    }
