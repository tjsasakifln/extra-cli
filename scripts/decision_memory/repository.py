"""Append-only PostgreSQL repository for Decision & Outcome Memory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg2.extras import Json, RealDictCursor

from scripts.decision_memory.db import require_client_id
from scripts.decision_memory.idempotency import (
    action_idempotency_key,
    decision_idempotency_key,
    outcome_idempotency_key,
)
from scripts.decision_memory.models import (
    ActionCompleteInput,
    ActionRecordInput,
    DecisionRecordInput,
    OutcomeRecordInput,
)
from scripts.decision_memory.temporal import classify_outcome_temporal


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _enum_val(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _row(d: Any) -> dict[str, Any] | None:
    if d is None:
        return None
    if isinstance(d, dict):
        out = dict(d)
    elif hasattr(d, "keys"):
        out = {k: d[k] for k in d.keys()}
    else:
        raise TypeError(f"unexpected DB row type: {type(d)!r}")
    for k, v in list(out.items()):
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat().replace("+00:00", "Z")
    return out


class DecisionMemoryRepository:
    """All methods require explicit client_id — never assume 'extra'."""

    def __init__(self, conn: Any):
        self.conn = conn

    def _cursor(self) -> Any:
        return self.conn.cursor(cursor_factory=RealDictCursor)

    # --- Decision -----------------------------------------------------------

    def record_decision(self, inp: DecisionRecordInput) -> dict[str, Any]:
        client_id = require_client_id(inp.client_id)
        decided_at = inp.decided_at or _utcnow()
        decided_at_s = decided_at.isoformat().replace("+00:00", "Z")
        idem = inp.idempotency_key or decision_idempotency_key(
            client_id=client_id,
            opportunity_key=inp.opportunity_key,
            human_decision=_enum_val(inp.human_decision),
            actor=inp.actor,
            justification=inp.justification,
            decided_at=decided_at_s,
            evidence_hash=inp.evidence_hash,
            legacy_decision=_enum_val(inp.legacy_decision) if inp.legacy_decision else None,
            supersedes_event_id=str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
        )
        existing = self.get_decision_by_idempotency(client_id, idem)
        if existing:
            return {"status": "duplicate", "event": existing, "created": False}

        event_id = uuid4()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.dm_decision_events (
                    event_id, client_id, opportunity_key, source_identifiers,
                    cycle_id, run_id, decided_at, session_deadline_at,
                    system_recommendation, human_decision, legacy_decision,
                    actor, justification, premises, constraints_known, data_limitations,
                    profile_id, profile_version, profile_hash, evidence_hash,
                    evidence_locators, schema_version, engine_version, prediction_ref,
                    temporal_integrity, origin, idempotency_key,
                    supersedes_event_id, correction_reason, correction_type, payload
                ) VALUES (
                    %(event_id)s, %(client_id)s, %(opportunity_key)s, %(source_identifiers)s,
                    %(cycle_id)s, %(run_id)s, %(decided_at)s, %(session_deadline_at)s,
                    %(system_recommendation)s, %(human_decision)s, %(legacy_decision)s,
                    %(actor)s, %(justification)s, %(premises)s, %(constraints_known)s,
                    %(data_limitations)s, %(profile_id)s, %(profile_version)s, %(profile_hash)s,
                    %(evidence_hash)s, %(evidence_locators)s, %(schema_version)s,
                    %(engine_version)s, %(prediction_ref)s, %(temporal_integrity)s,
                    %(origin)s, %(idempotency_key)s, %(supersedes_event_id)s,
                    %(correction_reason)s, %(correction_type)s, %(payload)s
                )
                ON CONFLICT (client_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                {
                    "event_id": str(event_id),
                    "client_id": client_id,
                    "opportunity_key": inp.opportunity_key,
                    "source_identifiers": Json(inp.source_identifiers),
                    "cycle_id": inp.cycle_id,
                    "run_id": inp.run_id,
                    "decided_at": decided_at,
                    "session_deadline_at": inp.session_deadline_at,
                    "system_recommendation": _enum_val(inp.system_recommendation),
                    "human_decision": _enum_val(inp.human_decision),
                    "legacy_decision": _enum_val(inp.legacy_decision) if inp.legacy_decision else None,
                    "actor": inp.actor,
                    "justification": inp.justification,
                    "premises": Json(inp.premises),
                    "constraints_known": Json(inp.constraints_known),
                    "data_limitations": Json(inp.data_limitations),
                    "profile_id": inp.profile_id,
                    "profile_version": inp.profile_version,
                    "profile_hash": inp.profile_hash,
                    "evidence_hash": inp.evidence_hash,
                    "evidence_locators": Json(inp.evidence_locators),
                    "schema_version": "decision-memory/1.0",
                    "engine_version": inp.engine_version,
                    "prediction_ref": Json(inp.prediction_ref) if inp.prediction_ref else None,
                    "temporal_integrity": _enum_val(inp.temporal_integrity),
                    "origin": _enum_val(inp.origin),
                    "idempotency_key": idem,
                    "supersedes_event_id": str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
                    "correction_reason": inp.correction_reason,
                    "correction_type": _enum_val(inp.correction_type) if inp.correction_type else None,
                    "payload": Json(inp.payload),
                },
            )
            row = cur.fetchone()
        if row is None:
            existing = self.get_decision_by_idempotency(client_id, idem)
            return {"status": "duplicate", "event": existing, "created": False}
        self.conn.commit()
        return {"status": "created", "event": _row(row), "created": True}

    def get_decision_by_idempotency(self, client_id: str, key: str) -> dict[str, Any] | None:
        client_id = require_client_id(client_id)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM public.dm_decision_events
                WHERE client_id = %s AND idempotency_key = %s
                """,
                (client_id, key),
            )
            row = cur.fetchone()
        return _row(row) if row else None

    def get_decision(self, client_id: str, event_id: str) -> dict[str, Any] | None:
        client_id = require_client_id(client_id)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM public.dm_decision_events
                WHERE client_id = %s AND event_id = %s
                """,
                (client_id, event_id),
            )
            row = cur.fetchone()
        return _row(row) if row else None

    def list_decisions(
        self,
        client_id: str,
        *,
        opportunity_key: str | None = None,
        limit: int = 100,
        current_only: bool = False,
    ) -> list[dict[str, Any]]:
        client_id = require_client_id(client_id)
        if current_only:
            sql = (
                "SELECT * FROM public.dm_decision_current WHERE client_id = %s"
            )
        else:
            sql = (
                "SELECT * FROM public.dm_decision_events WHERE client_id = %s"
            )
        params: list[Any] = [client_id]
        if opportunity_key:
            sql += " AND opportunity_key = %s"
            params.append(opportunity_key)
        sql += " ORDER BY decided_at DESC, created_at DESC LIMIT %s"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [_row(r) for r in rows]  # type: ignore[misc]

    def decision_history(self, client_id: str, opportunity_key: str) -> list[dict[str, Any]]:
        return self.list_decisions(client_id, opportunity_key=opportunity_key, limit=1000, current_only=False)

    # --- Action -------------------------------------------------------------

    def record_action(self, inp: ActionRecordInput) -> dict[str, Any]:
        client_id = require_client_id(inp.client_id)
        # Verify decision exists in same client (trigger also enforces)
        dec = self.get_decision(client_id, str(inp.decision_event_id))
        if not dec:
            raise ValueError(f"decision_event_id {inp.decision_event_id} not found for client_id={client_id}")
        due_s = inp.due_at.isoformat().replace("+00:00", "Z") if inp.due_at else None
        idem = inp.idempotency_key or action_idempotency_key(
            client_id=client_id,
            decision_event_id=str(inp.decision_event_id),
            description=inp.description,
            owner=inp.owner,
            due_at=due_s,
            status=_enum_val(inp.status),
            supersedes_event_id=str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
        )
        existing = self._get_action_by_idem(client_id, idem)
        if existing:
            return {"status": "duplicate", "event": existing, "created": False}

        event_id = uuid4()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.dm_action_events (
                    event_id, client_id, decision_event_id, opportunity_key,
                    description, owner, owner_absent_reason, due_at, due_absent_reason,
                    criticality, status, actor, temporal_integrity, origin,
                    idempotency_key, supersedes_event_id, schema_version, payload
                ) VALUES (
                    %(event_id)s, %(client_id)s, %(decision_event_id)s, %(opportunity_key)s,
                    %(description)s, %(owner)s, %(owner_absent_reason)s, %(due_at)s,
                    %(due_absent_reason)s, %(criticality)s, %(status)s, %(actor)s,
                    %(temporal_integrity)s, %(origin)s, %(idempotency_key)s,
                    %(supersedes_event_id)s, %(schema_version)s, %(payload)s
                )
                ON CONFLICT (client_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                {
                    "event_id": str(event_id),
                    "client_id": client_id,
                    "decision_event_id": str(inp.decision_event_id),
                    "opportunity_key": inp.opportunity_key,
                    "description": inp.description,
                    "owner": inp.owner,
                    "owner_absent_reason": inp.owner_absent_reason,
                    "due_at": inp.due_at,
                    "due_absent_reason": inp.due_absent_reason,
                    "criticality": _enum_val(inp.criticality),
                    "status": _enum_val(inp.status),
                    "actor": inp.actor,
                    "temporal_integrity": _enum_val(inp.temporal_integrity),
                    "origin": _enum_val(inp.origin),
                    "idempotency_key": idem,
                    "supersedes_event_id": str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
                    "schema_version": "decision-memory/1.0",
                    "payload": Json(inp.payload),
                },
            )
            row = cur.fetchone()
        if row is None:
            existing = self._get_action_by_idem(client_id, idem)
            return {"status": "duplicate", "event": existing, "created": False}
        self.conn.commit()
        return {"status": "created", "event": _row(row), "created": True}

    def complete_action(self, inp: ActionCompleteInput) -> dict[str, Any]:
        client_id = require_client_id(inp.client_id)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM public.dm_action_events
                WHERE client_id = %s AND event_id = %s
                """,
                (client_id, str(inp.action_event_id)),
            )
            prev = cur.fetchone()
        if not prev:
            raise ValueError(f"action_event_id {inp.action_event_id} not found for client")
        prev_d = dict(prev)
        completed_at = inp.completed_at or _utcnow()
        return self._complete_action_insert(prev_d, inp, completed_at)

    def _complete_action_insert(
        self,
        prev_d: dict[str, Any],
        inp: ActionCompleteInput,
        completed_at: datetime,
    ) -> dict[str, Any]:
        client_id = require_client_id(inp.client_id)
        idem = inp.idempotency_key or action_idempotency_key(
            client_id=client_id,
            decision_event_id=str(prev_d["decision_event_id"]),
            description=str(prev_d["description"]),
            owner=prev_d.get("owner"),
            due_at=None,
            status="COMPLETED",
            supersedes_event_id=str(prev_d["event_id"]),
        )
        existing = self._get_action_by_idem(client_id, idem)
        if existing:
            return {"status": "duplicate", "event": existing, "created": False}
        event_id = uuid4()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.dm_action_events (
                    event_id, client_id, decision_event_id, opportunity_key,
                    description, owner, owner_absent_reason, due_at, due_absent_reason,
                    criticality, status, completion_evidence_hash,
                    completion_evidence_locators, completed_at, actor,
                    temporal_integrity, origin, idempotency_key, supersedes_event_id,
                    schema_version, payload
                ) VALUES (
                    %(event_id)s, %(client_id)s, %(decision_event_id)s, %(opportunity_key)s,
                    %(description)s, %(owner)s, %(owner_absent_reason)s, %(due_at)s,
                    %(due_absent_reason)s, %(criticality)s, 'COMPLETED',
                    %(completion_evidence_hash)s, %(completion_evidence_locators)s,
                    %(completed_at)s, %(actor)s, %(temporal_integrity)s, 'supersession',
                    %(idempotency_key)s, %(supersedes_event_id)s, 'decision-memory/1.0',
                    %(payload)s
                )
                ON CONFLICT (client_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                {
                    "event_id": str(event_id),
                    "client_id": client_id,
                    "decision_event_id": str(prev_d["decision_event_id"]),
                    "opportunity_key": str(prev_d["opportunity_key"]),
                    "description": str(prev_d["description"]),
                    "owner": prev_d.get("owner"),
                    "owner_absent_reason": prev_d.get("owner_absent_reason"),
                    "due_at": prev_d.get("due_at"),
                    "due_absent_reason": prev_d.get("due_absent_reason"),
                    "criticality": prev_d.get("criticality") or "NORMAL",
                    "completion_evidence_hash": inp.evidence_hash,
                    "completion_evidence_locators": Json(inp.evidence_locators),
                    "completed_at": completed_at,
                    "actor": inp.actor,
                    "temporal_integrity": prev_d.get("temporal_integrity") or "PROSPECTIVE",
                    "idempotency_key": idem,
                    "supersedes_event_id": str(prev_d["event_id"]),
                    "payload": Json({"notes": inp.notes}),
                },
            )
            row = cur.fetchone()
        if row is None:
            existing = self._get_action_by_idem(client_id, idem)
            return {"status": "duplicate", "event": existing, "created": False}
        self.conn.commit()
        return {"status": "created", "event": _row(row), "created": True}

    def _get_action_by_idem(self, client_id: str, key: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM public.dm_action_events
                WHERE client_id = %s AND idempotency_key = %s
                """,
                (client_id, key),
            )
            row = cur.fetchone()
        return _row(row) if row else None

    def list_actions(
        self,
        client_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        client_id = require_client_id(client_id)
        if current_only:
            sql = "SELECT * FROM public.dm_action_current WHERE client_id = %s"
        else:
            sql = "SELECT * FROM public.dm_action_events WHERE client_id = %s"
        params: list[Any] = [client_id]
        if status:
            sql += " AND status = %s"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [_row(r) for r in rows]  # type: ignore[misc]

    # --- Outcome ------------------------------------------------------------

    def record_outcome(self, inp: OutcomeRecordInput) -> dict[str, Any]:
        client_id = require_client_id(inp.client_id)
        prior_decision_at = None
        if inp.decision_event_id:
            dec = self.get_decision(client_id, str(inp.decision_event_id))
            if not dec:
                raise ValueError(f"decision_event_id {inp.decision_event_id} not found for client_id={client_id}")
            prior_decision_at = dec.get("decided_at")
            if isinstance(prior_decision_at, str):
                prior_decision_at = datetime.fromisoformat(prior_decision_at.replace("Z", "+00:00"))
        else:
            # Look up current decision for opportunity
            current = self.list_decisions(client_id, opportunity_key=inp.opportunity_key, limit=1, current_only=True)
            if current:
                prior_decision_at = current[0].get("decided_at")
                if isinstance(prior_decision_at, str):
                    prior_decision_at = datetime.fromisoformat(prior_decision_at.replace("Z", "+00:00"))

        temporal = inp.temporal_integrity
        if temporal is None:
            temporal = classify_outcome_temporal(
                observed_at=inp.observed_at,
                prior_decision_at=prior_decision_at,
                is_backfill=False,
                order_provable=True,
            )

        observed_s = inp.observed_at.isoformat().replace("+00:00", "Z")
        idem = inp.idempotency_key or outcome_idempotency_key(
            client_id=client_id,
            opportunity_key=inp.opportunity_key,
            outcome_type=_enum_val(inp.outcome_type),
            observed_at=observed_s,
            evidence_hash=inp.evidence_hash,
            source=inp.source,
            supersedes_event_id=str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
        )
        existing = self._get_outcome_by_idem(client_id, idem)
        if existing:
            return {"status": "duplicate", "event": existing, "created": False}

        event_id = uuid4()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.dm_outcome_events (
                    event_id, client_id, opportunity_key, decision_event_id,
                    outcome_type, observed_at, effective_at, source, locator,
                    evidence_hash, confirmation_degree, actor, structured_facts,
                    observations, limitations, expected_margin, realized_margin,
                    temporal_integrity, origin, idempotency_key, supersedes_event_id,
                    correction_reason, correction_type, schema_version, payload
                ) VALUES (
                    %(event_id)s, %(client_id)s, %(opportunity_key)s, %(decision_event_id)s,
                    %(outcome_type)s, %(observed_at)s, %(effective_at)s, %(source)s, %(locator)s,
                    %(evidence_hash)s, %(confirmation_degree)s, %(actor)s, %(structured_facts)s,
                    %(observations)s, %(limitations)s, %(expected_margin)s, %(realized_margin)s,
                    %(temporal_integrity)s, %(origin)s, %(idempotency_key)s,
                    %(supersedes_event_id)s, %(correction_reason)s, %(correction_type)s,
                    'decision-memory/1.0', %(payload)s
                )
                ON CONFLICT (client_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                {
                    "event_id": str(event_id),
                    "client_id": client_id,
                    "opportunity_key": inp.opportunity_key,
                    "decision_event_id": str(inp.decision_event_id) if inp.decision_event_id else None,
                    "outcome_type": _enum_val(inp.outcome_type),
                    "observed_at": inp.observed_at,
                    "effective_at": inp.effective_at,
                    "source": inp.source,
                    "locator": inp.locator,
                    "evidence_hash": inp.evidence_hash,
                    "confirmation_degree": _enum_val(inp.confirmation_degree),
                    "actor": inp.actor,
                    "structured_facts": Json(inp.structured_facts),
                    "observations": inp.observations,
                    "limitations": Json(inp.limitations),
                    "expected_margin": inp.expected_margin,
                    "realized_margin": inp.realized_margin,
                    "temporal_integrity": _enum_val(temporal),
                    "origin": _enum_val(inp.origin),
                    "idempotency_key": idem,
                    "supersedes_event_id": str(inp.supersedes_event_id) if inp.supersedes_event_id else None,
                    "correction_reason": inp.correction_reason,
                    "correction_type": _enum_val(inp.correction_type) if inp.correction_type else None,
                    "payload": Json(inp.payload),
                },
            )
            row = cur.fetchone()
        if row is None:
            existing = self._get_outcome_by_idem(client_id, idem)
            return {"status": "duplicate", "event": existing, "created": False}
        self.conn.commit()
        return {"status": "created", "event": _row(row), "created": True}

    def _get_outcome_by_idem(self, client_id: str, key: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT * FROM public.dm_outcome_events
                WHERE client_id = %s AND idempotency_key = %s
                """,
                (client_id, key),
            )
            row = cur.fetchone()
        return _row(row) if row else None

    def list_outcomes(
        self,
        client_id: str,
        *,
        opportunity_key: str | None = None,
        limit: int = 100,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        client_id = require_client_id(client_id)
        if current_only:
            sql = "SELECT * FROM public.dm_outcome_current WHERE client_id = %s"
        else:
            sql = "SELECT * FROM public.dm_outcome_events WHERE client_id = %s"
        params: list[Any] = [client_id]
        if opportunity_key:
            sql += " AND opportunity_key = %s"
            params.append(opportunity_key)
        sql += " ORDER BY observed_at DESC, created_at DESC LIMIT %s"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [_row(r) for r in rows]  # type: ignore[misc]

    def verify_integrity(self, client_id: str) -> dict[str, Any]:
        client_id = require_client_id(client_id)
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM public.dm_decision_events WHERE client_id = %s",
                (client_id,),
            )
            n_dec = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM public.dm_action_events WHERE client_id = %s",
                (client_id,),
            )
            n_act = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(*) AS n FROM public.dm_outcome_events WHERE client_id = %s",
                (client_id,),
            )
            n_out = int(cur.fetchone()["n"])
            # Orphan actions (should be 0 due to FK + trigger)
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM public.dm_action_events a
                LEFT JOIN public.dm_decision_events d
                  ON d.event_id = a.decision_event_id AND d.client_id = a.client_id
                WHERE a.client_id = %s AND d.event_id IS NULL
                """,
                (client_id,),
            )
            orphan_actions = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM public.dm_outcome_events o
                WHERE o.client_id = %s
                  AND o.decision_event_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM public.dm_decision_events d
                    WHERE d.event_id = o.decision_event_id AND d.client_id = o.client_id
                  )
                """,
                (client_id,),
            )
            orphan_outcomes = int(cur.fetchone()["n"])
            # Cross-client leakage probe: decisions for this client referenced by other clients
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM public.dm_action_events a
                JOIN public.dm_decision_events d ON d.event_id = a.decision_event_id
                WHERE d.client_id = %s AND a.client_id <> %s
                """,
                (client_id, client_id),
            )
            leak_actions = int(cur.fetchone()["n"])

        ok = orphan_actions == 0 and orphan_outcomes == 0 and leak_actions == 0
        return {
            "ok": ok,
            "client_id": client_id,
            "counts": {
                "decisions": n_dec,
                "actions": n_act,
                "outcomes": n_out,
            },
            "orphan_actions": orphan_actions,
            "orphan_outcomes": orphan_outcomes,
            "cross_client_action_refs": leak_actions,
            "temporal_note": ("Only temporal_integrity=PROSPECTIVE may feed strong prospective metrics"),
            "append_only": True,
            "limitations": [
                "Integrity verify does not prove remote VPS state",
                "Missing outcomes remain UNKNOWN — never inferred as LOSS",
            ],
        }


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
