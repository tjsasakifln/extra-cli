"""Terminal contact-discovery states for every TARGET_CONFIRMED root.

States (mutually exclusive intent):
  CONTACT_READY              — ≥1 sendable company-owned email with valid provenance
  CONTACT_FOUND_NOT_SENDABLE — contact(s) found but not send-ready (mailbox/provenance/ownership)
  CONTACT_EXHAUSTED          — source ladder completed; no usable contact
  CONTACT_RETRY_PENDING      — transient failure; will retry
  CONTACT_EXTERNAL_BLOCKER   — captcha/auth/portal blocked; needs external action

CONTACT_EXHAUSTED requires sources_attempted non-empty after real ladder execution.
Offline/no-op runs must not mark exhausted or ready.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

CONTACT_READY = "CONTACT_READY"
CONTACT_FOUND_NOT_SENDABLE = "CONTACT_FOUND_NOT_SENDABLE"
CONTACT_EXHAUSTED = "CONTACT_EXHAUSTED"
CONTACT_RETRY_PENDING = "CONTACT_RETRY_PENDING"
CONTACT_EXTERNAL_BLOCKER = "CONTACT_EXTERNAL_BLOCKER"

TERMINAL_STATES = frozenset(
    {
        CONTACT_READY,
        CONTACT_FOUND_NOT_SENDABLE,
        CONTACT_EXHAUSTED,
        CONTACT_RETRY_PENDING,
        CONTACT_EXTERNAL_BLOCKER,
    }
)

# Source ladder order (configured cascade)
DEFAULT_SOURCE_LADDER: tuple[str, ...] = (
    "public_docs_datalake",
    "process_administrative_docs",
    "pncp_annexes",
    "official_site",
    "transparency_compras",
    "official_registry",
    "company_public_pages",
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ContactDiscoveryState:
    cnpj_raiz: str
    terminal_state: str
    sources_attempted: list[str] = field(default_factory=list)
    attempt_count: int = 0
    last_attempt_at: str | None = None
    next_retry_at: str | None = None
    terminal_reason: str | None = None
    email_count: int = 0
    email_send_ready_count: int = 0
    network_discovery: bool = False
    ladder_complete: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_contact_terminal(
    *,
    cnpj_raiz: str,
    sources_attempted: list[str] | None,
    email_candidates: int = 0,
    email_send_ready: int = 0,
    network_discovery: bool = False,
    ladder_complete: bool = False,
    external_blocker: str | None = None,
    retryable_error: bool = False,
    attempt_count: int = 1,
    next_retry_at: str | None = None,
    meta: dict[str, Any] | None = None,
) -> ContactDiscoveryState:
    """Derive terminal state from a real discovery attempt (not offline no-op)."""
    sources = list(sources_attempted or [])
    now = _utcnow()

    if not network_discovery and not sources and not ladder_complete:
        # Offline / structure pass — never count as discovery terminal completion
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_RETRY_PENDING,
            sources_attempted=[],
            attempt_count=attempt_count,
            last_attempt_at=now,
            next_retry_at=next_retry_at,
            terminal_reason="offline_or_noop_not_counted_as_discovery",
            email_count=email_candidates,
            email_send_ready_count=email_send_ready,
            network_discovery=False,
            ladder_complete=False,
            meta=dict(meta or {}),
        )

    if external_blocker:
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_EXTERNAL_BLOCKER,
            sources_attempted=sources,
            attempt_count=attempt_count,
            last_attempt_at=now,
            next_retry_at=next_retry_at,
            terminal_reason=str(external_blocker),
            email_count=email_candidates,
            email_send_ready_count=email_send_ready,
            network_discovery=network_discovery,
            ladder_complete=ladder_complete,
            meta=dict(meta or {}),
        )

    if email_send_ready > 0:
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_READY,
            sources_attempted=sources,
            attempt_count=attempt_count,
            last_attempt_at=now,
            terminal_reason="email_send_ready",
            email_count=email_candidates,
            email_send_ready_count=email_send_ready,
            network_discovery=network_discovery,
            ladder_complete=ladder_complete,
            meta=dict(meta or {}),
        )

    if email_candidates > 0:
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_FOUND_NOT_SENDABLE,
            sources_attempted=sources,
            attempt_count=attempt_count,
            last_attempt_at=now,
            next_retry_at=next_retry_at,
            terminal_reason="contacts_found_not_sendable",
            email_count=email_candidates,
            email_send_ready_count=0,
            network_discovery=network_discovery,
            ladder_complete=ladder_complete,
            meta=dict(meta or {}),
        )

    if retryable_error and not ladder_complete:
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_RETRY_PENDING,
            sources_attempted=sources,
            attempt_count=attempt_count,
            last_attempt_at=now,
            next_retry_at=next_retry_at,
            terminal_reason="retryable_error",
            email_count=0,
            email_send_ready_count=0,
            network_discovery=network_discovery,
            ladder_complete=False,
            meta=dict(meta or {}),
        )

    if ladder_complete and sources:
        return ContactDiscoveryState(
            cnpj_raiz=cnpj_raiz,
            terminal_state=CONTACT_EXHAUSTED,
            sources_attempted=sources,
            attempt_count=attempt_count,
            last_attempt_at=now,
            terminal_reason="source_ladder_exhausted_no_contact",
            email_count=0,
            email_send_ready_count=0,
            network_discovery=network_discovery,
            ladder_complete=True,
            meta=dict(meta or {}),
        )

    # Attempted something but ladder incomplete
    return ContactDiscoveryState(
        cnpj_raiz=cnpj_raiz,
        terminal_state=CONTACT_RETRY_PENDING,
        sources_attempted=sources,
        attempt_count=attempt_count,
        last_attempt_at=now,
        next_retry_at=next_retry_at,
        terminal_reason="ladder_incomplete",
        email_count=email_candidates,
        email_send_ready_count=email_send_ready,
        network_discovery=network_discovery,
        ladder_complete=False,
        meta=dict(meta or {}),
    )


def measure_terminal_coverage(
    states: list[ContactDiscoveryState] | list[dict[str, Any]],
    *,
    target_confirmed_total: int,
) -> dict[str, Any]:
    """Closed partition of CONFIRMED over contact terminal states."""
    counts = {s: 0 for s in TERMINAL_STATES}
    for st in states:
        d = st.as_dict() if isinstance(st, ContactDiscoveryState) else dict(st)
        term = str(d.get("terminal_state") or "")
        if term in counts:
            counts[term] += 1
    classified = sum(counts.values())
    never = max(0, int(target_confirmed_total) - classified)
    return {
        "schema": "confenge.contact_terminal_coverage.v1",
        "TARGET_CONFIRMED_total": int(target_confirmed_total),
        "terminal_counts": counts,
        "classified": classified,
        "never_attempted": never,
        "all_confirmed_have_terminal": never == 0 and classified == int(target_confirmed_total),
        "closed_sum": classified + never == int(target_confirmed_total),
    }
