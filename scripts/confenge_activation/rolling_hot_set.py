"""Rolling ACTIVE_HOT_SET — never a sticky Top-50 cohort.

Reservoir EMAIL_SEND_READY is ranked into a small window sized for current
throughput. When a lead is sent / replies / DNC / stale / loses eligibility,
another eligible company enters automatically.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Ineligibility reasons that force hot-set eviction
EVICT_REASONS = frozenset(
    {
        "sent",
        "replied",
        "dnc",
        "stale",
        "target_fit_lost",
        "provenance_invalid",
        "ineligible",
        "human_rejected",
        "bounced",
    }
)


@dataclass
class HotSetLead:
    cnpj_raiz: str
    rank_score: float = 0.0
    email: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def rank_key(lead: HotSetLead | dict[str, Any]) -> tuple[float, str]:
    if isinstance(lead, HotSetLead):
        return (-float(lead.rank_score), lead.cnpj_raiz)
    return (
        -float(lead.get("rank_score") or lead.get("score") or 0.0),
        str(lead.get("cnpj_raiz") or lead.get("cnpj") or ""),
    )


def is_eligible(
    lead: dict[str, Any],
    *,
    dnc: set[str] | None = None,
    replied: set[str] | None = None,
    sent_recent: set[str] | None = None,
    ineligible: set[str] | None = None,
) -> bool:
    """Eligibility for hot-set membership (fail-closed on bad flags)."""
    root = str(lead.get("cnpj_raiz") or lead.get("cnpj") or "")
    email = str(lead.get("email") or "").lower()
    if not root or not email:
        return False
    if not lead.get("email_send_ready", True):
        return False
    if lead.get("provenance_chain_valid") is False:
        return False
    if lead.get("target_fit_class") and lead.get("target_fit_class") != "TARGET_CONFIRMED":
        return False
    dnc = dnc or set()
    replied = replied or set()
    sent_recent = sent_recent or set()
    ineligible = ineligible or set()
    if root in dnc or email in dnc:
        return False
    if root in replied or email in replied:
        return False
    if root in sent_recent or email in sent_recent:
        return False
    if root in ineligible or email in ineligible:
        return False
    status = str(lead.get("status") or lead.get("evict_reason") or "").lower()
    if status in EVICT_REASONS:
        return False
    return True


def select_rolling_hot_set(
    reservoir: Iterable[dict[str, Any]],
    *,
    hot_set_size: int,
    dnc: set[str] | None = None,
    replied: set[str] | None = None,
    sent_recent: set[str] | None = None,
    ineligible: set[str] | None = None,
    previous_hot_set: list[str] | None = None,
) -> dict[str, Any]:
    """Build ACTIVE_HOT_SET from full EMAIL_SEND_READY reservoir.

    ``hot_set_size`` is throughput window (e.g. emails_per_hour or small multiple),
    never the national capacity and never stuck at 50 as a business objective.
    """
    size = max(1, int(hot_set_size))
    eligible = [
        dict(L)
        for L in reservoir
        if is_eligible(
            L,
            dnc=dnc,
            replied=replied,
            sent_recent=sent_recent,
            ineligible=ineligible,
        )
    ]
    eligible.sort(key=rank_key)
    selected = eligible[:size]
    roots = [str(L.get("cnpj_raiz") or L.get("cnpj")) for L in selected]
    prev = set(previous_hot_set or [])
    entered = [r for r in roots if r not in prev]
    exited = [r for r in prev if r not in set(roots)]
    return {
        "schema": "confenge.rolling_hot_set.v1",
        "as_of": _utcnow(),
        "ACTIVE_HOT_SET": len(selected),
        "hot_set_size_configured": size,
        "reservoir_eligible": len(eligible),
        "roots": roots,
        "leads": selected,
        "entered": entered,
        "exited": exited,
        "note": (
            "Rolling window over NATIONAL_EMAIL_SEND_READY_RESERVOIR; "
            "not a fixed Top-N commercial cohort."
        ),
    }
