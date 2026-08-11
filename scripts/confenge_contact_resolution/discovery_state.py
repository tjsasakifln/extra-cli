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

# Minimum set that must be attempted before CONTACT_EXHAUSTED is legal.
# Process-only harvest is never enough — official_site / registry / company pages
# must run (or be proven unavailable with explicit EXTERNAL_BLOCKER).
REQUIRED_FOR_EXHAUSTION: frozenset[str] = frozenset(
    {
        "process_administrative_docs",
        "pncp_annexes",
        "official_site",
        "official_registry",
        "company_public_pages",
    }
)

# Aliases accepted as covering a required ladder step
_SOURCE_ALIASES: dict[str, frozenset[str]] = {
    "process_administrative_docs": frozenset(
        {"process_administrative_docs", "public_process_document", "public_docs"}
    ),
    "pncp_annexes": frozenset({"pncp_annexes", "pncp_annex", "pncp"}),
    "official_site": frozenset(
        {"official_site", "site", "OFFICIAL_COMPANY_SITE", "REAL_OFFICIAL_SITE"}
    ),
    "official_registry": frozenset({"official_registry", "registry"}),
    "company_public_pages": frozenset(
        {"company_public_pages", "contact_page", "web_search", "site_crawl"}
    ),
    "public_docs_datalake": frozenset({"public_docs_datalake", "datalake", "public_docs"}),
    "transparency_compras": frozenset(
        {"transparency_compras", "transparency", "compras", "municipal_portal"}
    ),
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sources_cover_required_ladder(sources_attempted: list[str] | None) -> bool:
    """True only when every REQUIRED_FOR_EXHAUSTION step was really attempted."""
    attempted = {str(s).strip() for s in (sources_attempted or []) if s}
    if not attempted:
        return False
    for required in REQUIRED_FOR_EXHAUSTION:
        aliases = _SOURCE_ALIASES.get(required, frozenset({required}))
        if not (attempted & aliases) and required not in attempted:
            return False
    return True


def missing_ladder_steps(sources_attempted: list[str] | None) -> list[str]:
    """Required steps not yet covered by sources_attempted."""
    attempted = {str(s).strip() for s in (sources_attempted or []) if s}
    missing: list[str] = []
    for required in DEFAULT_SOURCE_LADDER:
        aliases = _SOURCE_ALIASES.get(required, frozenset({required}))
        if required not in attempted and not (attempted & aliases):
            missing.append(required)
    return missing


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

    # CONTACT_EXHAUSTED is illegal when only process docs were tried.
    full_ladder = sources_cover_required_ladder(sources)
    if ladder_complete and sources and full_ladder:
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

    # Attempted something but ladder incomplete (incl. process-only "exhaustion")
    missing = missing_ladder_steps(sources)
    reason = "ladder_incomplete"
    if ladder_complete and sources and not full_ladder:
        reason = "process_only_not_full_ladder"
    return ContactDiscoveryState(
        cnpj_raiz=cnpj_raiz,
        terminal_state=CONTACT_RETRY_PENDING,
        sources_attempted=sources,
        attempt_count=attempt_count,
        last_attempt_at=now,
        next_retry_at=next_retry_at,
        terminal_reason=reason,
        email_count=email_candidates,
        email_send_ready_count=email_send_ready,
        network_discovery=network_discovery,
        ladder_complete=False,
        meta={**(meta or {}), "missing_ladder_steps": missing},
    )


def measure_terminal_coverage(
    states: list[ContactDiscoveryState] | list[dict[str, Any]],
    *,
    population_total: int,
    population_name: str = "TARGET_CONFIRMED",
) -> dict[str, Any]:
    """Closed partition of a named population over contact terminal states."""
    counts = {s: 0 for s in TERMINAL_STATES}
    for st in states:
        d = st.as_dict() if isinstance(st, ContactDiscoveryState) else dict(st)
        term = str(d.get("terminal_state") or "")
        if term in counts:
            counts[term] += 1
    classified = sum(counts.values())
    never = max(0, int(population_total) - classified)
    population_key = str(population_name or "TARGET_CONFIRMED").strip().upper()
    result = {
        "schema": "confenge.contact_terminal_coverage.v1",
        "population_name": population_key,
        "population_total": int(population_total),
        "terminal_counts": counts,
        "classified": classified,
        "never_attempted": never,
        "all_population_has_terminal": never == 0 and classified == int(population_total),
        "closed_sum": classified + never == int(population_total),
    }
    if population_key == "TARGET_CONFIRMED":
        result["TARGET_CONFIRMED_total"] = int(population_total)
        result["all_confirmed_have_terminal"] = result["all_population_has_terminal"]
    return result
