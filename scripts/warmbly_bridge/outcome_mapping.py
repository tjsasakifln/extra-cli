"""Map confenge.outcome.v1 wire events → Decision Memory + commercial state.

Never auto-creates WON from machine classification alone.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from scripts.decision_memory.models import (
    ConfirmationDegree,
    EventOrigin,
    OutcomeRecordInput,
    OutcomeType,
    TemporalIntegrity,
)
from scripts.warmbly_bridge import OUTCOME_EVENT_TYPES, SCHEMA_OUTCOME
from scripts.warmbly_bridge.constants import (
    CHANNEL_ALIASES,
    EVENT_TO_COMMERCIAL_STATE,
    EVENT_TO_DM_OUTCOME_TYPE,
)


class OutcomeValidationError(ValueError):
    """Invalid or policy-rejected outcome payload."""


def normalize_event_type(raw: str) -> str:
    t = (raw or "").strip().upper()
    aliases = {
        "DNC": "DO_NOT_CONTACT",
        "BOUNCE": "BOUNCED",
        "REVIEWED": "LEAD_REVIEWED",
        "SENT": "SENT",
    }
    return aliases.get(t, t)


def normalize_channel(raw: str | None, metadata: dict[str, Any] | None = None) -> str:
    meta = metadata or {}
    ch = (raw or meta.get("channel") or meta.get("medium") or "").strip().lower()
    return CHANNEL_ALIASES.get(ch, ch or "unknown")


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _evidence_hash(envelope: dict[str, Any]) -> str:
    body = json.dumps(envelope, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise OutcomeValidationError("payload must be a JSON object")
    if envelope.get("schema_version") != SCHEMA_OUTCOME:
        raise OutcomeValidationError(
            f"unsupported schema_version {envelope.get('schema_version')!r} (want {SCHEMA_OUTCOME})"
        )
    for req in ("event_id", "idempotency_key", "occurred_at", "source", "event_type"):
        if not str(envelope.get(req) or "").strip():
            raise OutcomeValidationError(f"missing required field: {req}")
    event_type = normalize_event_type(str(envelope["event_type"]))
    if event_type not in OUTCOME_EVENT_TYPES and event_type not in {
        "LEAD_REVIEWED",
        "DO_NOT_CONTACT",
        "BOUNCED",
        "SENT",
    }:
        raise OutcomeValidationError(f"unknown event_type: {event_type}")
    out = dict(envelope)
    out["event_type"] = event_type
    return out


def human_confirmed_won(envelope: dict[str, Any]) -> bool:
    """WON is accepted only with explicit human signal in metadata/payload."""
    meta = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
    if meta.get("human_confirmed") is True:
        return True
    if str(meta.get("actor_type") or "").lower() in {"human", "user", "operator"}:
        return True
    if str(meta.get("source_of_truth") or "").lower() == "human":
        return True
    # Top-level optional flags
    if envelope.get("human_confirmed") is True:
        return True
    return False


def suggested_commercial_state(event_type: str) -> str | None:
    return EVENT_TO_COMMERCIAL_STATE.get(event_type)


def build_outcome_record_input(
    envelope: dict[str, Any],
    *,
    client_id: str,
    actor: str = "warmbly-outcome-receptor",
) -> OutcomeRecordInput:
    """Build Decision Memory OutcomeRecordInput. Raises on auto-WON policy reject."""
    env = validate_envelope(envelope)
    event_type = env["event_type"]

    if event_type == "WON" and not human_confirmed_won(env):
        raise OutcomeValidationError(
            "WON rejected: never auto-create commercial win from machine classification; "
            "require metadata.human_confirmed=true (or actor_type=human)"
        )

    dm_type_s = EVENT_TO_DM_OUTCOME_TYPE.get(event_type, "UNKNOWN")
    dm_type = OutcomeType(dm_type_s)

    meta = env.get("metadata") if isinstance(env.get("metadata"), dict) else {}
    channel = normalize_channel(env.get("channel"), meta)
    cnpj = "".join(ch for ch in str(env.get("cnpj14") or "") if ch.isdigit())
    source_lead_id = str(env.get("source_lead_id") or "").strip()
    opportunity_key = source_lead_id or (f"cnpj:{cnpj}" if cnpj else str(env["event_id"]))

    commercial = suggested_commercial_state(event_type)
    structured = {
        "warmbly_event_type": event_type,
        "warmbly_event_id": env["event_id"],
        "channel": channel,
        "cnpj14": cnpj or None,
        "source_lead_id": source_lead_id or None,
        "campaign_id": env.get("campaign_id"),
        "message_id": env.get("message_id"),
        "contact_email_present": bool(str(env.get("contact_email") or "").strip()),
        "suggested_commercial_state": commercial,
        "won_human_confirmed": human_confirmed_won(env) if event_type == "WON" else None,
        "schema_version": SCHEMA_OUTCOME,
    }

    observed = _parse_dt(str(env["occurred_at"]))
    idem = str(env["idempotency_key"]).strip()

    return OutcomeRecordInput(
        client_id=client_id,
        opportunity_key=opportunity_key,
        outcome_type=dm_type,
        observed_at=observed,
        source="warmbly",
        evidence_hash=_evidence_hash(env),
        actor=actor,
        confirmation_degree=ConfirmationDegree.DECLARED,
        structured_facts=structured,
        observations=f"warmbly outcome {event_type} channel={channel}",
        limitations=[
            "Outreach event mapped into Decision Memory OutcomeType without full enum isomorphism.",
            "Commercial state suggestion is advisory; dominant human states must be preserved by callers.",
        ],
        temporal_integrity=TemporalIntegrity.PROSPECTIVE,
        origin=EventOrigin.API,
        idempotency_key=idem,
        payload={
            "warmbly_envelope": {
                "event_id": env["event_id"],
                "event_type": event_type,
                "source": env.get("source"),
                "campaign_id": env.get("campaign_id"),
                "message_id": env.get("message_id"),
                # contact_email intentionally omitted from durable payload logs path;
                # presence flag lives in structured_facts.
            },
            "metadata": {
                k: v
                for k, v in meta.items()
                if k not in {"contact_email", "email", "phone", "raw_body", "message_body"}
            },
        },
    )
