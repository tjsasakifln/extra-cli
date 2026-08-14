"""Publish 1–3 already-observed human recipients for the Warmbly pilot (#370).

Never invent name, email, role or consent. Generic/functional mailboxes stay
unpromoted. If no already-observed public named human validates, the path
fails closed with reason codes.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.mailbox_purpose import (
    PURPOSE_GENERIC_CONTACT,
    PURPOSE_UNKNOWN,
    SEND_ALLOWED_PURPOSES,
    classify_mailbox_purpose,
)

SCHEMA_ID = "confenge-pilot-recipients-v1"
VALIDATED = "VALIDATED"
REJECTED = "REJECTED"
GENERIC_PURPOSES = frozenset(
    {
        PURPOSE_GENERIC_CONTACT,
        "GENERIC_CONTACT",
        "NOREPLY",
        "SUPPORT_SAC",
        "HR_RECRUITING",
        "PRIVACY_DPO",
        "PRESS",
    }
)
_GENERIC_LOCALS = frozenset(
    {
        "contato",
        "contact",
        "comercial",
        "licitacoes",
        "licitações",
        "adm",
        "admin",
        "ouvidoria",
        "sac",
        "noreply",
        "no-reply",
        "financeiro",
        "rh",
        "imprensa",
        "comunicacao",
        "comunicação",
    }
)


@dataclass
class PilotRecipient:
    account_id: str
    name: str
    role: str
    email: str
    source_url: str
    observed_at: str
    ownership: str
    suitability: str
    status: str
    reasons: list[str] = field(default_factory=list)
    suppression: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _local_part(email: str) -> str:
    return (email or "").split("@", 1)[0].strip().lower()


def _looks_invented(record: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field_name in ("name", "role", "email"):
        value = str(record.get(field_name) or "").strip()
        if not value:
            reasons.append(f"missing_{field_name}")
        if value.lower() in {"tbd", "unknown", "n/a", "inferred", "placeholder"}:
            reasons.append(f"invented_{field_name}")
    if record.get("inferred") or record.get("invented"):
        reasons.append("inferred_flag")
    if record.get("name_explicitly_published") is False:
        reasons.append("name_not_published")
    if record.get("email_explicitly_published") is False:
        reasons.append("email_not_published")
    if record.get("role_explicitly_published") is False:
        reasons.append("role_not_published")
    return reasons


def evaluate_observed_recipient(record: Mapping[str, Any]) -> PilotRecipient:
    """Validate one already-observed public contact. Never fills missing PII."""
    email = str(record.get("email") or "").strip()
    name = str(record.get("name") or record.get("nome") or "").strip()
    role = str(record.get("role") or record.get("cargo") or "").strip()
    account = str(record.get("account_id") or record.get("target_id") or record.get("cnpj") or "").strip()
    source_url = str(
        record.get("source_url")
        or (record.get("source") or {}).get("source_url")
        or record.get("url")
        or ""
    ).strip()
    observed_at = str(
        record.get("observed_at")
        or (record.get("source") or {}).get("observed_at")
        or record.get("published_at")
        or ""
    ).strip()
    reasons = _looks_invented(
        {
            "name": name,
            "role": role,
            "email": email,
            "inferred": record.get("inferred"),
            "invented": record.get("invented"),
            "name_explicitly_published": record.get("name_explicitly_published", False),
            "email_explicitly_published": record.get("email_explicitly_published", False),
            "role_explicitly_published": record.get("role_explicitly_published", False),
        }
    )
    purpose = classify_mailbox_purpose(email)
    local = _local_part(email)
    if (
        purpose.purpose in GENERIC_PURPOSES
        or purpose.purpose not in SEND_ALLOWED_PURPOSES
        or purpose.purpose != PURPOSE_UNKNOWN
        or local in _GENERIC_LOCALS
    ):
        reasons.append("functional_mailbox_not_human_recipient")
    if " " not in name and name.count(".") == 0:
        # A single token is not a published human name.
        reasons.append("name_not_human_nominal")
    if not source_url:
        reasons.append("missing_source_url")
    if not observed_at:
        reasons.append("missing_observed_at")
    if record.get("suppression") in {"opt-out", "hard_bounce", "do_not_contact"}:
        reasons.append(f"suppressed:{record.get('suppression')}")

    status = VALIDATED if not reasons else REJECTED
    if status == VALIDATED:
        reasons = ["human_recipient_evidence_valid"]
    return PilotRecipient(
        account_id=account,
        name=name if status == VALIDATED else name,
        role=role,
        email=email,
        source_url=source_url,
        observed_at=observed_at,
        ownership=str(record.get("ownership") or record.get("ownership_status") or "UNPROVEN"),
        suitability=str(record.get("suitability") or "UNREVIEWED"),
        status=status,
        reasons=reasons,
        suppression=str(record.get("suppression") or "none"),
    )


def publish_pilot_recipients(
    observed: Iterable[Mapping[str, Any]],
    *,
    min_validated: int = 1,
    max_validated: int = 3,
) -> dict[str, Any]:
    """Republish only already-observed humans. Fail closed when none validate."""
    evaluated = [evaluate_observed_recipient(row) for row in observed]
    validated = [item for item in evaluated if item.status == VALIDATED]
    rejected = [item for item in evaluated if item.status != VALIDATED]
    selected = validated[:max_validated]
    fail_reasons: list[str] = []
    if len(selected) < min_validated:
        fail_reasons.append("insufficient_validated_humans")
        if not evaluated:
            fail_reasons.append("no_observed_evidence")
        if any("functional_mailbox_not_human_recipient" in item.reasons for item in rejected):
            fail_reasons.append("generic_mailbox_not_promoted")
        if any(reason.startswith("invented_") or reason.endswith("_not_published") for item in rejected for reason in item.reasons):
            fail_reasons.append("refused_to_invent_pii")
    return {
        "schema_id": SCHEMA_ID,
        "ok": not fail_reasons,
        "status": "READY" if not fail_reasons else "FAIL_CLOSED",
        "validated": [item.to_dict() for item in selected],
        "rejected": [item.to_dict() for item in rejected],
        "validated_count": len(selected),
        "reason_codes": fail_reasons,
        # Recipient list is not a Warmbly send-ready claim.
        "warmbly_ready": False,
    }


def load_observed_evidence(path: str | Path) -> list[dict[str, Any]]:
    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        rows = payload.get("recipients") or payload.get("contacts") or payload.get("observed") or []
        return [dict(item) for item in rows]
    raise ValueError("observed evidence must be a JSON list or object with recipients")
