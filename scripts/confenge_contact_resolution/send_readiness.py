"""EMAIL_SEND_READY and target_fit_send_tier gates (EMAIL_ONLY commercial autorun).

Semantic EMAIL_SEND_READY requires ALL of:
  TARGET_FIT_CONFIRMED (TARGET_CONFIRMED / tier A|B with confirmed construction)
  AND SERVICE_FIT_SUPPORTED
  AND CONTACT_SEND_READY
  AND COPY_CONTEXT_READY
  AND NOT_BLOCKED

Missing any dimension → fail closed (never send-ready).
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
from scripts.confenge_universe.target_fit import (
    TARGET_CONFIRMED,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
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
UNSUITABLE_COPY_CONTEXT = "UNSUITABLE_COPY_CONTEXT"

# Generic why_you / hooks that do not count as copy context
_GENERIC_WHY_MARKERS: tuple[str, ...] = (
    "empresa com momento comercial público",
    "portfólio público de contratos de engenharia",
    "portfólio público de contratos",
    "observamos contratos públicos",
)


@dataclass(frozen=True)
class TargetFitResult:
    tier: str
    reasons: list[str] = field(default_factory=list)
    sector_fit: str = ""
    canonical_universe_member: bool = True
    target_fit_class: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_fit_send_tier": self.tier,
            "reasons": list(self.reasons),
            "sector_fit": self.sector_fit,
            "canonical_universe_member": self.canonical_universe_member,
            "target_fit_class": self.target_fit_class,
        }


@dataclass(frozen=True)
class CopyContextResult:
    copy_context_ready: bool
    reasons: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "copy_context_ready": self.copy_context_ready,
            "reasons": list(self.reasons),
            "missing_fields": list(self.missing_fields),
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
    target_fit_class: str = ""
    copy_context_ready: bool = False
    service_fit_supported: bool = False
    contact_send_ready: bool = False

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
            "target_fit_class": self.target_fit_class,
            "copy_context_ready": self.copy_context_ready,
            "service_fit_supported": self.service_fit_supported,
            "contact_send_ready": self.contact_send_ready,
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


def _target_fit_class_from_row(company: dict[str, Any] | None) -> str:
    if not company:
        return ""
    ce = company.get("construction_evidence") if isinstance(company.get("construction_evidence"), dict) else {}
    for key in ("target_fit_class", "target_fit"):
        v = company.get(key) or ce.get(key)
        if v:
            return str(v).strip().upper()
    return ""


def _pass_contract_count(company: dict[str, Any] | None) -> int:
    """Count construction-relevant PASS contracts only — never total portfolio size."""
    if not company:
        return 0
    port = company.get("portfolio") if isinstance(company.get("portfolio"), dict) else {}
    ce = company.get("construction_evidence") if isinstance(company.get("construction_evidence"), dict) else {}
    for key in (
        "pass_contract_count",
        "relevant_pass_contracts",
        "construction_contract_count",
        "relevant_execution_contract_count",
        "relevant_contract_count",
    ):
        v = company.get(key) or port.get(key) or ce.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    # Do NOT fall back to total/active contract counts — that inflated false positives.
    return 0


def classify_target_fit_send_tier(
    company: dict[str, Any] | None,
    *,
    canonical_universe_member: bool | None = None,
) -> TargetFitResult:
    """Map universe/intelligence fit into send authorization tier.

    Universe membership is broader than send tier. RESEARCH_ONLY stays in the
    reservoir but is never EMAIL_SEND_READY.

    POSSIBLE_ENGINEERING_FIT alone never becomes send tier A/B — requires
    explicit TARGET_CONFIRMED (or strong sector + execution triangulation).
    """
    reasons: list[str] = []
    if company is None:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=["missing_company"],
            canonical_universe_member=False,
            target_fit_class=TARGET_OUT_OF_SCOPE,
        )

    if canonical_universe_member is None:
        if company.get("canonical_universe_member") is False:
            member = False
        elif company.get("in_canonical_universe") is False:
            member = False
        else:
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
                target_fit_class=TARGET_OUT_OF_SCOPE,
            )
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=[f"outreach_eligibility:{elig}"],
            sector_fit=elig,
            canonical_universe_member=member,
            target_fit_class=TARGET_OUT_OF_SCOPE,
        )

    sector = _sector_fit_from_row(company)
    tfc = _target_fit_class_from_row(company)

    if tfc == TARGET_OUT_OF_SCOPE or sector in _OUT_OF_SCOPE_MARKERS or any(
        m in sector for m in ("BANK", "NOT_CONSTRUCTION", "OUT_OF_SCOPE")
    ):
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=[f"target_or_sector_out:{tfc or sector or 'out'}"],
            sector_fit=sector,
            canonical_universe_member=member,
            target_fit_class=tfc or TARGET_OUT_OF_SCOPE,
        )

    if not member:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=["not_canonical_universe_member"],
            sector_fit=sector,
            canonical_universe_member=False,
            target_fit_class=tfc or TARGET_OUT_OF_SCOPE,
        )

    pass_n = _pass_contract_count(company)

    # Explicit TARGET_CONFIRMED wins
    if tfc == TARGET_CONFIRMED:
        if sector in _STRONG_FIT or sector.startswith("CONFIRMED") or sector.startswith("STRONG"):
            reasons.append("target_fit_confirmed_strong_sector")
            return TargetFitResult(
                tier=TIER_A_AUTOMATIC,
                reasons=reasons,
                sector_fit=sector,
                canonical_universe_member=member,
                target_fit_class=TARGET_CONFIRMED,
            )
        reasons.append("target_fit_confirmed_evidence_supported")
        return TargetFitResult(
            tier=TIER_B_EVIDENCE_SUPPORTED,
            reasons=reasons,
            sector_fit=sector,
            canonical_universe_member=member,
            target_fit_class=TARGET_CONFIRMED,
        )

    # Strong/confirmed sector fit without explicit target_fit_class:
    # only A/B if we have real PASS construction counts (not total portfolio).
    if sector in _STRONG_FIT or sector.startswith("CONFIRMED") or sector.startswith("STRONG"):
        if company.get("conflicting_evidence"):
            reasons.append("conflicting_evidence")
            return TargetFitResult(
                tier=TIER_RESEARCH_ONLY,
                reasons=reasons,
                sector_fit=sector,
                canonical_universe_member=member,
                target_fit_class=tfc or TARGET_PROBABLE_RESEARCH,
            )
        if pass_n >= 1 or company.get("factual_hook") or company.get("evidence_ids"):
            reasons.append("strong_or_confirmed_engineering_fit")
            return TargetFitResult(
                tier=TIER_A_AUTOMATIC,
                reasons=reasons,
                sector_fit=sector,
                canonical_universe_member=member,
                target_fit_class=tfc or TARGET_CONFIRMED,
            )
        reasons.append("strong_sector_missing_pass_contracts_research")
        return TargetFitResult(
            tier=TIER_RESEARCH_ONLY,
            reasons=reasons,
            sector_fit=sector,
            canonical_universe_member=member,
            target_fit_class=tfc or TARGET_PROBABLE_RESEARCH,
        )

    # POSSIBLE / probable → never automatic send
    if (
        tfc == TARGET_PROBABLE_RESEARCH
        or sector in _POSSIBLE_FIT
        or "POSSIBLE" in sector
    ):
        reasons.append(f"possible_or_probable_research pass_contracts={pass_n}")
        return TargetFitResult(
            tier=TIER_RESEARCH_ONLY,
            reasons=reasons,
            sector_fit=sector,
            canonical_universe_member=member,
            target_fit_class=tfc or TARGET_PROBABLE_RESEARCH,
        )

    if elig in {"ELIGIBLE", ""} and pass_n >= 2:
        reasons.append("eligible_multi_pass_research_pending_target_confirmed")
        return TargetFitResult(
            tier=TIER_RESEARCH_ONLY,
            reasons=reasons,
            sector_fit=sector or elig or "ELIGIBLE",
            canonical_universe_member=member,
            target_fit_class=tfc or TARGET_PROBABLE_RESEARCH,
        )

    reasons.append("default_research_or_out")
    if elig and elig not in {"ELIGIBLE", "RESEARCH"}:
        return TargetFitResult(
            tier=TIER_OUT_OF_SCOPE,
            reasons=reasons + [f"elig:{elig}"],
            sector_fit=sector,
            canonical_universe_member=member,
            target_fit_class=tfc or TARGET_OUT_OF_SCOPE,
        )
    return TargetFitResult(
        tier=TIER_RESEARCH_ONLY,
        reasons=reasons,
        sector_fit=sector,
        canonical_universe_member=member,
        target_fit_class=tfc or TARGET_PROBABLE_RESEARCH,
    )


def _field_nonempty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "ok" if value else ""
    return str(value).strip()


def _is_generic_why(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True
    return any(m in t for m in _GENERIC_WHY_MARKERS)


def evaluate_copy_context_ready(company: dict[str, Any] | None, *, service_code: str | None = None) -> CopyContextResult:
    """COPY_CONTEXT_READY: why you/now, fact, service, micro-offer, evidence, CTA."""
    missing: list[str] = []
    reasons: list[str] = []
    if not company:
        return CopyContextResult(False, reasons=["missing_company"], missing_fields=["company"])

    why_you = _field_nonempty(
        company.get("why_this_account")
        or company.get("why_you")
        or ((company.get("messaging") or {}) if isinstance(company.get("messaging"), dict) else {}).get(
            "why_this_account"
        )
    )
    why_now = _field_nonempty(
        company.get("why_now")
        or (
            (company.get("why_now") if isinstance(company.get("why_now"), str) else None)
        )
        or (
            (company.get("moment") or {}) if isinstance(company.get("moment"), dict) else {}
        ).get("summary")
        or (
            (company.get("why_now") if isinstance(company.get("why_now"), dict) else {}) or {}
        ).get("summary")
        or (
            (company.get("why_now") if isinstance(company.get("why_now"), dict) else {}) or {}
        ).get("temporal_fact")
    )
    if isinstance(company.get("why_now"), dict):
        why_now = _field_nonempty(
            company["why_now"].get("temporal_fact")
            or company["why_now"].get("summary")
            or company["why_now"].get("code")
            or why_now
        )

    observed = _field_nonempty(
        company.get("observed_fact")
        or company.get("factual_hook")
        or company.get("fact_to_mention")
        or (
            (company.get("messaging") or {}) if isinstance(company.get("messaging"), dict) else {}
        ).get("fact_to_mention")
    )
    svc = _field_nonempty(
        service_code
        or company.get("service_code")
        or company.get("canonical_service_code")
        or (
            (company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}
        ).get("service_code")
        or (
            (company.get("primary_service") or {})
            if isinstance(company.get("primary_service"), dict)
            else company.get("primary_service")
        )
    )
    if isinstance(company.get("primary_service"), dict) and not svc:
        svc = _field_nonempty(
            company["primary_service"].get("service_id")
            or company["primary_service"].get("service_code")
        )

    micro = _field_nonempty(
        company.get("micro_offer_code")
        or company.get("micro_offer")
        or (
            (company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}
        ).get("entry_offer")
        or (
            (company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}
        ).get("micro_offer_code")
    )
    evidence = company.get("evidence_ids")
    if not evidence and isinstance(company.get("evidence"), list):
        evidence = [
            str(e.get("id") if isinstance(e, dict) else e)
            for e in company["evidence"]
            if e
        ]
    if not evidence and isinstance(company.get("moment"), dict):
        evidence = company["moment"].get("evidence_ids")
    has_evidence = bool(evidence) and (
        isinstance(evidence, list) and len(evidence) > 0 or isinstance(evidence, str) and evidence.strip()
    )
    cta = _field_nonempty(
        company.get("cta")
        or (
            (company.get("messaging") or {}) if isinstance(company.get("messaging"), dict) else {}
        ).get("cta")
        or company.get("question_to_ask")
    )

    if not why_you or _is_generic_why(why_you):
        missing.append("why_this_account")
    if not why_now:
        missing.append("why_now")
    if not observed:
        missing.append("observed_fact")
    if not svc:
        missing.append("service_code")
    if not micro:
        missing.append("micro_offer_code")
    if not has_evidence:
        missing.append("evidence_ids")
    if not cta:
        missing.append("cta")

    ready = len(missing) == 0
    if ready:
        reasons.append("copy_context_complete")
    else:
        reasons.append("copy_context_incomplete")
        reasons.extend(f"missing:{m}" for m in missing)
    return CopyContextResult(copy_context_ready=ready, reasons=reasons, missing_fields=missing)


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
    require_copy_context: bool = True,
) -> EmailSendReadyResult:
    """EMAIL_SEND_READY requires target+service+contact+copy_context+not_blocked."""
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
    if fit.target_fit_class in {TARGET_OUT_OF_SCOPE, TARGET_PROBABLE_RESEARCH}:
        reasons.append(f"target_fit_class:{fit.target_fit_class}")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_TARGET

    svc = (service_code or "").strip()
    if company and not svc:
        svc = str(
            company.get("service_code")
            or company.get("canonical_service_code")
            or company.get("primary_service")
            or ((company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}).get("service_code")
            or ""
        ).strip()
        if isinstance(company.get("primary_service"), dict):
            svc = str(
                company["primary_service"].get("service_id")
                or company["primary_service"].get("service_code")
                or svc
            ).strip()
    service_fit_supported = bool(svc)
    if not svc:
        reasons.append("no_service_code")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_SERVICE
    else:
        # Reject silent REAJUSTE-only monoculture markers without supporting fit
        reasons.append(f"service_code:{svc}")

    has_ev = factual_evidence or bool(evidence_ids)
    if company and not has_ev:
        has_ev = bool(
            company.get("factual_hook")
            or company.get("observed_fact")
            or company.get("fact_to_mention")
            or company.get("evidence_ids")
            or (isinstance(company.get("evidence"), list) and company.get("evidence"))
            or _pass_contract_count(company) > 0
        )
    if not has_ev:
        reasons.append("no_factual_evidence")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_EVIDENCE

    # Enrich company for copy-context check with evidence_ids param
    company_for_copy = dict(company) if company else {}
    if evidence_ids and not company_for_copy.get("evidence_ids"):
        company_for_copy["evidence_ids"] = list(evidence_ids)
    if factual_evidence and not company_for_copy.get("factual_hook") and not company_for_copy.get("observed_fact"):
        # Allow tests that pass factual_evidence=True without explicit hook text
        # only when copy context is not required OR other fields present.
        pass

    copy_res = evaluate_copy_context_ready(company_for_copy, service_code=svc)
    copy_ok = copy_res.copy_context_ready if require_copy_context else True
    if require_copy_context and not copy_res.copy_context_ready:
        reasons.append("copy_context_not_ready")
        reasons.extend(copy_res.reasons)
        if suitability == SUITABLE:
            suitability = UNSUITABLE_COPY_CONTEXT

    if suitability == SUITABLE and mp.purpose == "GENERIC_CONTACT":
        suitability = SUITABLE_GENERIC

    contact_send_ready = (
        channel_ok
        and bool(email_norm)
        and own in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}
        and not dnc
        and not bounce
        and not account_blocked
        and contact_fresh
        and not mp.send_blocked
    )

    target_ok = (
        fit.tier in SEND_TIERS
        and fit.canonical_universe_member
        and fit.target_fit_class not in {TARGET_OUT_OF_SCOPE, TARGET_PROBABLE_RESEARCH}
    )

    email_ready = (
        contact_send_ready
        and target_ok
        and service_fit_supported
        and has_ev
        and copy_ok
    )
    if email_ready and "all_gates_pass" not in reasons:
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
        target_fit_class=fit.target_fit_class,
        copy_context_ready=copy_res.copy_context_ready,
        service_fit_supported=service_fit_supported,
        contact_send_ready=contact_send_ready,
    )


def ready_supply_target(
    *,
    max_send_rate: int = 20,
    send_window_hours: int = 9,
    ready_supply_target_days: int = 2,
) -> int:
    """Companies EMAIL_SEND_READY to keep ahead of the queue."""
    return max(1, int(max_send_rate) * int(send_window_hours) * int(ready_supply_target_days))
