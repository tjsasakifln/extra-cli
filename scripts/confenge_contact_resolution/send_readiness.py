"""EMAIL_SEND_READY and target_fit_send_tier gates (EMAIL_ONLY commercial autorun).

Separates:
  - contact_ownership_status (who owns the channel)
  - channel_send_eligibility (mailbox purpose + verification + DNC/bounce)
  - recipient_commercial_suitability (target fit + service + evidence)
  - email_send_ready (all of the above for EMAIL channel)

Phone-only never sets EMAIL_SEND_READY. Contact enrichment alone never promotes
OUT_OF_SCOPE / RESEARCH_ONLY into send-ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.confenge_contact_resolution.mailbox_purpose import (
    BLOCKED_PURPOSES,
    classify_mailbox_purpose,
)
from scripts.confenge_contact_resolution.models import (
    ENROLLABLE_OWNERSHIP,
    OwnershipStatus,
    VerificationStatus,
)

# target_fit_send_tier values
TIER_A_AUTOMATIC = "A_AUTOMATIC"
TIER_B_EVIDENCE_SUPPORTED = "B_EVIDENCE_SUPPORTED"
TIER_RESEARCH_ONLY = "RESEARCH_ONLY"
TIER_OUT_OF_SCOPE = "OUT_OF_SCOPE"

SEND_TIERS = frozenset({TIER_A_AUTOMATIC, TIER_B_EVIDENCE_SUPPORTED})

# Construction / engineering sector fit labels from universe builder
_STRONG_FIT = frozenset(
    {
        "CONFIRMED_ENGINEERING",
        "STRONG_ENGINEERING_FIT",
        "CONFIRMED_CONSTRUCTION",
        "STRONG_CONSTRUCTION_FIT",
        "CONSTRUCTION_CONFIRMED",
        "ENGINEERING_CONFIRMED",
    }
)
_POSSIBLE_FIT = frozenset(
    {
        "POSSIBLE_ENGINEERING_FIT",
        "POSSIBLE_CONSTRUCTION_FIT",
        "LIKELY_CONSTRUCTION",
        "POSSIBLE_CONSTRUCTION",
        "MIXED_PORTFOLIO",
    }
)
_OUT_OF_SCOPE_MARKERS = frozenset(
    {
        "NOT_CONSTRUCTION",
        "OUT_OF_SCOPE",
        "COMMERCE",
        "MATERIALS",
        "MINING",
        "TECHNOLOGY",
        "TOURISM",
        "BANK",
        "BANKS",
        "PHARMACY",
        "INCOMPATIBLE",
        "EXCLUDED_BANK",
        "EXCLUDED_NON_CONSTRUCTION",
    }
)

# Verification statuses acceptable for email send (not pattern-guess).
_OK_VERIFICATION = frozenset(
    {
        VerificationStatus.OBSERVED.value,
        VerificationStatus.VERIFIED.value,
        "OFFICIAL_SOURCE",
        "INSTITUTIONAL_GENERIC",
        "PUBLIC_POSSIBLY_STALE",
        "HUMAN_CONFIRMED",
    }
)
_BAD_VERIFICATION = frozenset(
    {
        VerificationStatus.CANDIDATE_UNVERIFIED.value,
        VerificationStatus.PATTERN_GUESS.value,
        VerificationStatus.SYNTAX_INVALID.value,
        VerificationStatus.NOT_AVAILABLE.value,
        "INVALID",
        "NOT_FOUND",
    }
)

# Commercial suitability
SUITABLE = "SUITABLE"
SUITABLE_GENERIC = "SUITABLE_GENERIC"
UNSUITABLE_MAILBOX = "UNSUITABLE_MAILBOX"
UNSUITABLE_OWNERSHIP = "UNSUITABLE_OWNERSHIP"
UNSUITABLE_VERIFICATION = "UNSUITABLE_VERIFICATION"
UNSUITABLE_TARGET = "UNSUITABLE_TARGET"
UNSUITABLE_NO_EMAIL = "UNSUITABLE_NO_EMAIL"
UNSUITABLE_DNC = "UNSUITABLE_DNC"
UNSUITABLE_BOUNCE = "UNSUITABLE_BOUNCE"
UNSUITABLE_BLOCKED = "UNSUITABLE_BLOCKED"
UNSUITABLE_NO_SERVICE = "UNSUITABLE_NO_SERVICE"
UNSUITABLE_NO_EVIDENCE = "UNSUITABLE_NO_EVIDENCE"
UNSUITABLE_STALE = "UNSUITABLE_STALE"


@dataclass(frozen=True)
class TargetFitResult:
    tier: str
    reasons: list[str] = field(default_factory=list)
    sector_fit: str = ""
    canonical_universe_member: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_fit_send_tier": self.tier,
            "reasons": list(self.reasons),
            "sector_fit": self.sector_fit,
            "canonical_universe_member": self.canonical_universe_member,
        }


@dataclass(frozen=True)
class EmailSendReadyResult:
    email_send_ready: bool
    target_fit_send_tier: str
    mailbox_purpose: str
    ownership_status: str
    verification_status: str
    recipient_commercial_suitability: str
    channel_send_eligibility: bool
    reasons: list[str] = field(default_factory=list)
    email: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "email_send_ready": self.email_send_ready,
            "target_fit_send_tier": self.target_fit_send_tier,
            "mailbox_purpose": self.mailbox_purpose,
            "ownership_status": self.ownership_status,
            "verification_status": self.verification_status,
            "recipient_commercial_suitability": self.recipient_commercial_suitability,
            "channel_send_eligibility": self.channel_send_eligibility,
            "reasons": list(self.reasons),
            "email": self.email,
        }


def _sector_fit_from_row(company: dict[str, Any] | None) -> str:
    if not company:
        return ""
    ce = company.get("construction_evidence") if isinstance(company.get("construction_evidence"), dict) else {}
    for key in (
        "sector_fit",
        "construction_sector_fit",
        "engineering_fit",
        "fit_class",
        "classification",
    ):
        v = company.get(key) or ce.get(key)
        if v:
            return str(v).strip().upper()
    elig = str(company.get("outreach_eligibility") or "").strip().upper()
    if elig:
        return elig
    return ""


def _pass_contract_count(company: dict[str, Any] | None) -> int:
    if not company:
        return 0
    port = company.get("portfolio") if isinstance(company.get("portfolio"), dict) else {}
    for key in ("pass_contract_count", "relevant_pass_contracts", "construction_contract_count"):
        v = company.get(key) or port.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    # Fallback: total recent contracts as weak evidence count
    for key in ("contract_count_recent", "active_contract_count", "contract_count_total"):
        v = port.get(key) if port else company.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return 0


def classify_target_fit_send_tier(
    company: dict[str, Any] | None,
    *,
    canonical_universe_member: bool | None = None,
) -> TargetFitResult:
    """Map universe/intelligence fit into send authorization tier.

    Universe membership is broader than send tier. RESEARCH_ONLY stays in the
    reservoir but is never EMAIL_SEND_READY.
    """
    reasons: list[str] = []
    if company is None:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=["missing_company"],
            canonical_universe_member=False,
        )

    if canonical_universe_member is None:
        # Explicit flags from universe builder / pipeline.
        if company.get("canonical_universe_member") is False:
            member = False
        elif company.get("in_canonical_universe") is False:
            member = False
        else:
            # Presence in confenge universe export implies membership unless marked out.
            member = True
    else:
        member = bool(canonical_universe_member)

    elig = str(company.get("outreach_eligibility") or "").strip().upper()
    if elig in {"NOT_CONSTRUCTION", "EXCLUDED", "OUT_OF_SCOPE", "BANK", "DNC"}:
        if elig == "DNC":
            return TargetFitResult(
                tier=TIER_OUT_OF_SCOPE,
                reasons=["outreach_eligibility_dnc"],
                sector_fit=elig,
                canonical_universe_member=member,
            )
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=[f"outreach_eligibility:{elig}"],
            sector_fit=elig,
            canonical_universe_member=member,
        )

    sector = _sector_fit_from_row(company)
    if sector in _OUT_OF_SCOPE_MARKERS or any(m in sector for m in ("BANK", "NOT_CONSTRUCTION", "OUT_OF_SCOPE")):
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=[f"sector_fit:{sector or 'out'}"],
            sector_fit=sector,
            canonical_universe_member=member,
        )

    if not member:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=["not_canonical_universe_member"],
            sector_fit=sector,
            canonical_universe_member=False,
        )

    pass_n = _pass_contract_count(company)
    offer = company.get("offer") if isinstance(company.get("offer"), dict) else {}
    has_service = bool(
        company.get("service_code")
        or company.get("primary_service")
        or offer.get("service_code")
    )
    has_trigger = bool(company.get("primary_trigger") or company.get("activation_triggers"))
    has_evidence = bool(
        company.get("evidence_ids")
        or company.get("factual_hook")
        or (isinstance(company.get("evidence"), list) and company.get("evidence"))
        or pass_n > 0
    )

    if sector in _STRONG_FIT or sector.startswith("CONFIRMED") or sector.startswith("STRONG"):
        # Conflicting material evidence would demote; none modeled as explicit flag yet.
        if company.get("conflicting_evidence"):
            reasons.append("conflicting_evidence")
            return TargetFitResult(
                tier=TIER_RESEARCH_ONLY,
                reasons=reasons,
                sector_fit=sector,
                canonical_universe_member=member,
            )
        reasons.append("strong_or_confirmed_engineering_fit")
        return TargetFitResult(
            tier=TIER_A_AUTOMATIC,
            reasons=reasons,
            sector_fit=sector,
            canonical_universe_member=member,
        )

    if sector in _POSSIBLE_FIT or "POSSIBLE" in sector:
        # B only with enough contractual / service / trigger support.
        strong_enough = pass_n >= 2 or (pass_n >= 1 and (has_service or has_trigger) and has_evidence)
        if strong_enough:
            reasons.append(f"possible_fit_with_evidence pass_contracts={pass_n}")
            return TargetFitResult(
                tier=TIER_B_EVIDENCE_SUPPORTED,
                reasons=reasons,
                sector_fit=sector,
                canonical_universe_member=member,
            )
        reasons.append(f"possible_fit_insufficient_evidence pass_contracts={pass_n}")
        return TargetFitResult(
            tier=TIER_RESEARCH_ONLY,
            reasons=reasons,
            sector_fit=sector,
            canonical_universe_member=member,
        )

    # Default: if universe ELIGIBLE without strong labels, treat as research unless
    # multiple PASS contracts + service.
    if elig in {"ELIGIBLE", ""} and pass_n >= 2 and has_service:
        reasons.append("eligible_multi_pass_with_service")
        return TargetFitResult(
            tier=TIER_B_EVIDENCE_SUPPORTED,
            reasons=reasons,
            sector_fit=sector or elig or "ELIGIBLE",
            canonical_universe_member=member,
        )
    if elig in {"ELIGIBLE", ""} and (pass_n >= 1 or has_evidence):
        reasons.append("eligible_needs_research_or_weak_evidence")
        return TargetFitResult(
            tier=TIER_RESEARCH_ONLY,
            reasons=reasons,
            sector_fit=sector or elig or "ELIGIBLE",
            canonical_universe_member=member,
        )

    reasons.append("default_research_or_out")
    if elig and elig not in {"ELIGIBLE", "RESEARCH"}:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=reasons + [f"elig:{elig}"],
            sector_fit=sector,
            canonical_universe_member=member,
        )
    return TargetFitResult(
        tier=TIER_RESEARCH_ONLY,
        reasons=reasons,
        sector_fit=sector,
        canonical_universe_member=member,
    )


def evaluate_email_send_ready(
    *,
    company: dict[str, Any] | None,
    email: str | None,
    ownership_status: str | None = None,
    verification_status: str | None = None,
    dnc: bool = False,
    bounce: bool = False,
    account_blocked: bool = False,
    contact_fresh: bool = True,
    service_code: str | None = None,
    factual_evidence: bool = False,
    evidence_ids: list[str] | None = None,
    canonical_universe_member: bool | None = None,
    target_fit: TargetFitResult | None = None,
) -> EmailSendReadyResult:
    """EMAIL_SEND_READY requires email channel + target fit A/B + all gates."""
    reasons: list[str] = []
    email_norm = (email or "").strip() or None
    own = (ownership_status or "").strip().upper()
    ver = (verification_status or "").strip().upper()

    fit = target_fit or classify_target_fit_send_tier(
        company, canonical_universe_member=canonical_universe_member
    )
    mp = classify_mailbox_purpose(email_norm)
    suitability = SUITABLE
    channel_ok = True

    if not email_norm or "@" not in email_norm:
        reasons.append("no_email")
        suitability = UNSUITABLE_NO_EMAIL
        channel_ok = False
    if dnc:
        reasons.append("dnc")
        suitability = UNSUITABLE_DNC
        channel_ok = False
    if bounce:
        reasons.append("bounce")
        suitability = UNSUITABLE_BOUNCE
        channel_ok = False
    if account_blocked:
        reasons.append("account_blocked")
        suitability = UNSUITABLE_BLOCKED
        channel_ok = False
    if not contact_fresh:
        reasons.append("contact_stale")
        suitability = UNSUITABLE_STALE
        channel_ok = False
    if mp.send_blocked or mp.purpose in BLOCKED_PURPOSES:
        reasons.append(mp.block_reason or f"mailbox_purpose:{mp.purpose}")
        suitability = UNSUITABLE_MAILBOX
        channel_ok = False
    if own and own not in ENROLLABLE_OWNERSHIP and own != OwnershipStatus.HUMAN_CONFIRMED.value:
        # Only COMPANY_OWNED / HUMAN_CONFIRMED
        if own not in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}:
            reasons.append(f"ownership:{own or 'missing'}")
            suitability = UNSUITABLE_OWNERSHIP
            channel_ok = False
    elif not own:
        reasons.append("ownership_missing")
        suitability = UNSUITABLE_OWNERSHIP
        channel_ok = False
    if ver in _BAD_VERIFICATION or (ver and ver not in _OK_VERIFICATION and ver not in {"", "OBSERVED", "VERIFIED"}):
        if ver in _BAD_VERIFICATION or ver in {
            VerificationStatus.PATTERN_GUESS.value,
            VerificationStatus.CANDIDATE_UNVERIFIED.value,
        }:
            reasons.append(f"verification:{ver}")
            suitability = UNSUITABLE_VERIFICATION
            channel_ok = False
    if not ver and email_norm:
        reasons.append("verification_missing")
        suitability = UNSUITABLE_VERIFICATION
        channel_ok = False

    if fit.tier not in SEND_TIERS:
        reasons.append(f"target_fit:{fit.tier}")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_TARGET
    if not fit.canonical_universe_member:
        reasons.append("not_universe_member")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_TARGET

    svc = (service_code or "").strip()
    if company and not svc:
        svc = str(
            company.get("service_code")
            or company.get("primary_service")
            or ((company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}).get("service_code")
            or ""
        ).strip()
    if not svc:
        reasons.append("no_service_code")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_SERVICE

    has_ev = factual_evidence or bool(evidence_ids)
    if company and not has_ev:
        has_ev = bool(
            company.get("factual_hook")
            or company.get("evidence_ids")
            or (isinstance(company.get("evidence"), list) and company.get("evidence"))
            or _pass_contract_count(company) > 0
        )
    if not has_ev:
        reasons.append("no_factual_evidence")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_EVIDENCE

    if suitability == SUITABLE and mp.purpose == "GENERIC_CONTACT":
        suitability = SUITABLE_GENERIC

    email_ready = (
        channel_ok
        and fit.tier in SEND_TIERS
        and fit.canonical_universe_member
        and bool(svc)
        and has_ev
        and bool(email_norm)
        and own in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}
        and not dnc
        and not bounce
        and not account_blocked
        and contact_fresh
        and not mp.send_blocked
    )
    if email_ready and not reasons:
        reasons.append("all_gates_pass")

    return EmailSendReadyResult(
        email_send_ready=email_ready,
        target_fit_send_tier=fit.tier,
        mailbox_purpose=mp.purpose,
        ownership_status=own,
        verification_status=ver,
        recipient_commercial_suitability=suitability,
        channel_send_eligibility=channel_ok and not mp.send_blocked and bool(email_norm),
        reasons=reasons,
        email=email_norm,
    )


def ready_supply_target(
    *,
    max_send_rate: int = 20,
    send_window_hours: int = 9,
    ready_supply_target_days: int = 2,
) -> int:
    """Companies EMAIL_SEND_READY to keep ahead of the queue."""
    return max(1, int(max_send_rate) * int(send_window_hours) * int(ready_supply_target_days))
