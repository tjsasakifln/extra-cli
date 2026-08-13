"""EMAIL_SEND_READY and target_fit_send_tier gates (EMAIL_ONLY commercial autorun).

Semantic EMAIL_SEND_READY requires ALL of:
  REAL_TARGET (TARGET_CONFIRMED / tier A|B with confirmed construction)
  AND REAL_SERVICE_FIT
  AND REAL_CONTACT
  AND REAL_COPY_CONTEXT
  AND NOT_BLOCKED
  AND FRESH
  AND PROVENANCE_CHAIN_VALID

Missing any dimension → fail closed (never send-ready).

Stored labels alone (VERIFIED, COMPANY_OWNED, HUMAN_CONFIRMED, prior
EMAIL_SEND_READY) never grant send-ready when provenance roots in
TEST_FIXTURE / DEMO / SYNTHETIC / UNKNOWN or has transitive taint.

Sticky COMPANY_OWNED / VERIFIED also never grant REAL_CONTACT when the email
domain fails residual-safe alignment with razao_social (wrong-company domains
such as qualidademineracao / emkoelektronik / lcmprojetos for unrelated CNPJs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from scripts.confenge_contact_resolution.email_policy import domain_of, is_freemail
from scripts.confenge_contact_resolution.mailbox_purpose import (
    BLOCKED_PURPOSES,
    classify_mailbox_purpose,
)
from scripts.confenge_contact_resolution.models import (
    ENROLLABLE_OWNERSHIP,
    OwnershipStatus,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.provenance_trust import (
    ProvenanceTrustResult,
    evaluate_contact_provenance,
    evaluate_provenance_trust,
    provenance_blocks_send,
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
UNSUITABLE_PROVENANCE = "UNSUITABLE_PROVENANCE"
UNSUITABLE_HUMAN_EVIDENCE = "UNSUITABLE_HUMAN_EVIDENCE"


def company_identity_label(company: dict[str, Any] | None) -> str:
    """Best available legal/trade name for domain↔company identity checks."""
    if not company:
        return ""
    for key in (
        "razao_social",
        "legal_name",
        "company_name",
        "company_legal_name",
        "name",
    ):
        v = company.get(key)
        if v and str(v).strip():
            return str(v).strip()
    for key in ("nome_fantasia", "trade_name", "fantasia"):
        v = company.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def email_matches_company_identity(
    email: str | None,
    company: dict[str, Any] | None,
    *,
    ownership_status: str | None = None,
) -> tuple[bool, str]:
    """Re-validate domain↔company identity; sticky COMPANY_OWNED cannot wash mismatch.

    Returns (ok, reason_code). Fail-closed when a non-freemail domain does not
    residual-safely align with the company label. HUMAN_CONFIRMED may pass without
    domain alignment (explicit human gate). Missing company label skips the check
    (caller still needs ownership/provenance).
    """
    email_norm = (email or "").strip() or None
    if not email_norm or "@" not in email_norm:
        return True, "no_email_for_identity"
    own = (ownership_status or "").strip().upper()
    if own == OwnershipStatus.HUMAN_CONFIRMED.value:
        return True, "human_confirmed_identity_exempt"
    if is_freemail(email_norm):
        return True, "freemail_identity_via_ownership_only"
    label = company_identity_label(company)
    if not label:
        return True, "company_label_absent"
    domain = domain_of(email_norm)
    if not domain:
        return False, "ownership_identity_domain_missing"
    official = None
    if company:
        official = company.get("official_domain") or company.get("company_domain") or company.get("website_domain")
        if official:
            official = str(official).strip() or None
    # Lazy import keeps send_readiness free of circular import at module load
    # when discovery.official_domain pulls ownership helpers.
    from scripts.confenge_contact_resolution.discovery.official_domain import (
        email_domain_aligned_with_company,
    )

    if email_domain_aligned_with_company(
        domain,
        label,
        official_domain=official,
    ):
        return True, "domain_aligned_with_company"
    return False, "ownership_identity_domain_mismatch"


# Prefixes/phrases that alone (or with only a company name) are hollow copy context.
_GENERIC_WHY_MARKERS: tuple[str, ...] = (
    "empresa com momento comercial público",
    "portfólio público de contratos de engenharia",
    "portfólio público de contratos",
    "empresa com portfólio público observável",
    "portfólio público observável",
    "observamos contratos públicos",
    "momento comercial indicado pelo extra-cli",
    "portfólio público observado com",
    "contrato(s) no input",
    "ufs observadas nos contratos",
    "fato contratual público utilizável",
    "sem dor especializada dominante",
    "sem dor concreta dominante",
    "sem dor contratual concreta",
    "sem dor concreta",
    "momento comercial público",
    "execução pública observável",
    "empresa com execução pública observável",
    "portfólio multi-contrato ativo",
    # Cohort-level template phrases (skeptic: identical why_you/why_now across all ESR)
    "executora com contratos públicos recentes de engenharia e momento de reajuste",
    "executora com contratos públicos recentes de engenharia",
    "executora com contratos públicos recentes",
    "aditivo ou medição recente no contrato principal de obra pública",
    "aditivo ou medição recente no contrato principal",
    "momento de reajuste/aditivo observável",
    "contrato público de engenharia com execução observável no pncp",
    "contrato público de engenharia observável",
    "why_now_strength=weak",
    "why_now_strength=moderate",
    "target_fit",
    "email_send_ready",
    "copy_context_ready",
    "service_fit_supported",
)

# Legal form / sector words that never count as company brand in copy.
_COPY_STOPWORDS = frozenset(
    {
        "ltda",
        "eireli",
        "sa",
        "s/a",
        "me",
        "epp",
        "engenharia",
        "construtora",
        "construcoes",
        "construções",
        "construcao",
        "construção",
        "servicos",
        "serviços",
        "obras",
        "pavimentacao",
        "pavimentação",
        "infraestrutura",
        "empreendimentos",
        "incorporadora",
        "industria",
        "indústria",
        "comercio",
        "comércio",
        "recuperacao",
        "recuperação",
        "judicial",
        "de",
        "da",
        "do",
        "dos",
        "das",
        "e",
        "em",
        "para",
        "com",
        "ltda.",
    }
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
    provenance_chain_valid: bool = False
    provenance_trust: str = ""
    root_source_type: str = ""
    derived_from_fixture: bool = False
    human_recipient_evidence_valid: bool = False

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
            "provenance_chain_valid": self.provenance_chain_valid,
            "provenance_trust": self.provenance_trust,
            "root_source_type": self.root_source_type,
            "derived_from_fixture": self.derived_from_fixture,
            "human_recipient_evidence_valid": self.human_recipient_evidence_valid,
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

    if (
        tfc == TARGET_OUT_OF_SCOPE
        or sector in _OUT_OF_SCOPE_MARKERS
        or any(m in sector for m in ("BANK", "NOT_CONSTRUCTION", "OUT_OF_SCOPE"))
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
    if tfc == TARGET_PROBABLE_RESEARCH or sector in _POSSIBLE_FIT or "POSSIBLE" in sector:
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


def _company_brand_tokens(company: dict[str, Any] | None) -> set[str]:
    """Distinctive brand tokens from razao_social / fantasia / official domain SLD."""
    if not company:
        return set()
    labels: list[str] = []
    for key in ("razao_social", "company_name", "nome_fantasia", "name"):
        v = company.get(key)
        if v:
            labels.append(str(v))
    text = " ".join(labels).lower()
    raw = re.findall(r"[a-z0-9]{3,}", text)
    brands = {t for t in raw if t not in _COPY_STOPWORDS and not t.isdigit()}
    # Domain SLD (empresa-target.com.br → empresatarget / empresa-target tokens)
    for dkey in ("official_domain", "company_domain", "website_domain"):
        dom = str(company.get(dkey) or "").lower().removeprefix("www.")
        if not dom:
            continue
        for suf in (".com.br", ".eng.br", ".net.br", ".org.br", ".com", ".net", ".org", ".br"):
            if dom.endswith(suf):
                dom = dom[: -len(suf)]
                break
        sld = dom.split(".")[-1] if dom else ""
        if sld and len(sld) >= 3 and sld not in _COPY_STOPWORDS:
            brands.add(sld.replace("-", ""))
            if "-" in sld:
                brands.update(p for p in sld.split("-") if len(p) >= 3)
    return brands


def _has_specific_contract_hook(text: str) -> bool:
    """True when text names a concrete objeto/órgão (not generic obra/contrato)."""
    t = text.strip().lower()
    if len(t) < 50:
        return False
    # Must include objeto: or a specific works type + a named organ/municipality marker
    specific_work = (
        "paviment",
        "cbuq",
        "terraplan",
        "saneamento",
        "drenagem",
        "ponte",
        "viaduto",
        "edific",
        "reforma",
        "recuperação",
        "recuperacao",
        "sinaliz",
        "ilumina",
    )
    organ = (
        "prefeitura",
        "secretaria",
        "departamento",
        "dnit",
        "dersa",
        "der-",
        "órgão:",
        "orgao:",
        "município",
        "municipio",
        "pref.",
        "objeto:",
    )
    if "objeto:" in t and any(o in t for o in organ):
        return True
    if any(w in t for w in specific_work) and any(o in t for o in organ):
        return True
    return False


def _is_generic_why(text: str, company: dict[str, Any] | None = None) -> bool:
    """Hollow/generic why_you|why_now — templates without company-specific fact fail.

    Skeptic: identical why_you/why_now across 50 ESR rows must never pass as copy-ready.
    Rescue requires either company brand token in the text OR a specific contract hook.
    Generic words (contrato/obra/engenharia/aditivo) alone no longer rescue long templates.
    """
    t = text.strip().lower()
    if not t:
        return True
    # Prefer shared hollow detector (portfolio-count, UFs-only, meta).
    hollow = False
    try:
        from scripts.confenge_account_intelligence.message_spine import is_hollow_fact

        hollow = bool(is_hollow_fact(text))
    except ImportError:
        hollow = False
    if hollow:
        if "portfólio público observado com" in t or "contrato(s) no input" in t:
            return True
        if "ufs observadas" in t:
            return True
    # Exact / substring template markers always hollow unless brand + specific hook.
    marked = any(m in t for m in _GENERIC_WHY_MARKERS)
    if "portfólio público observado com" in t or "contrato(s) no input" in t:
        return True
    brands = _company_brand_tokens(company)
    has_brand = bool(brands) and any(b in t.replace("-", "") or b in t for b in brands)
    # also allow hyphenated brand match
    if brands and not has_brand:
        t_norm = t.replace("-", "").replace(" ", "")
        has_brand = any(b.replace("-", "") in t_norm for b in brands)
    specific = _has_specific_contract_hook(t)

    if marked:
        # Template only rescued by brand AND specific contractual hook together.
        if has_brand and specific and len(t) > 80:
            return False
        return True
    # Hollow: shorter than a real hook.
    if len(t) < 40:
        return True
    # Without company brand (when company known) and without specific hook → generic.
    if company is not None and brands and not has_brand and not specific:
        return True
    if company is not None and brands and not has_brand and specific:
        # Specific hook without brand is weak but allowed if clearly contrato-specific
        return False
    if not specific and not has_brand and len(t) < 100:
        # Short generic engineering boilerplate
        boilerplate = (
            "contratos públicos recentes",
            "execução pública",
            "obra pública",
            "momento de reajuste",
        )
        if any(b in t for b in boilerplate):
            return True
    return False


def _is_hollow_observed_fact(text: str, company: dict[str, Any] | None = None) -> bool:
    """observed_fact / fact_to_mention must be a concrete contractual hook."""
    try:
        from scripts.confenge_account_intelligence.message_spine import is_hollow_fact

        if is_hollow_fact(text):
            return True
    except ImportError:
        return _is_generic_why(text, company=company)
    except Exception:
        return _is_generic_why(text, company=company)
    return _is_generic_why(text, company=company)


def _gestao_signals_sufficient(signals: list[Any], evidence: list[Any], company: dict[str, Any]) -> bool:
    """Gestão/monitoramento is not a generic fallback for 'has a public contract'.

    Requires multi-contract / multi-organ / robust structure or diverse events —
    bare multi_contract alone with <3 contracts is GESTAO_GENERIC_FALLBACK.
    """
    sigs = {str(s).lower() for s in (signals or []) if s}
    # Explicit generic fallback markers never support gestão.
    if "fallback" in sigs or "generic_fallback" in sigs:
        return False
    n_contracts = 0
    for key in ("contracts", "contract_count", "n_contracts"):
        val = company.get(key)
        if isinstance(val, list):
            n_contracts = max(n_contracts, len(val))
        elif isinstance(val, int):
            n_contracts = max(n_contracts, val)
    strong = {
        "structure_robust",
        "multi_orgao",
        "multi_uf",
        "diverse_events",
        "complex_contract",
        "recurring_portfolio",
    }
    # multi_contract alone is not enough ("tem contrato público" / thin book).
    if sigs & strong:
        return True
    if "multi_contract" in sigs and n_contracts >= 5:
        return True
    # 3–4 contracts only with evidence AND explicit multi-organ/UF signal elsewhere
    orgaos = set()
    ufs = set()
    for c in company.get("contracts") or []:
        if isinstance(c, dict):
            o = str(c.get("orgao") or c.get("agency") or "").strip()
            u = str(c.get("uf") or "").strip().upper()
            if o:
                orgaos.add(o)
            if u:
                ufs.add(u)
    if "multi_contract" in sigs and n_contracts >= 3 and (len(orgaos) >= 2 or len(ufs) >= 2):
        return True
    return False


def _service_fit_supported(company: dict[str, Any] | None, svc: str) -> bool:
    """SERVICE_FIT_SUPPORTED requires service code PLUS candidate evidence/signals.

    A bare non-empty service_code is not enough (prevents silent monoculture labels).
    Gestão/monitoramento additionally requires defendable portfolio evidence.
    """
    if not svc or not company:
        return False
    svc_l = svc.lower()
    is_gestao = "gestao_monitoramento" in svc_l or "monitoramento_contratual" in svc_l

    def _ok(signals: list[Any], evidence: list[Any]) -> bool:
        if not ((isinstance(signals, list) and len(signals) > 0) or (isinstance(evidence, list) and len(evidence) > 0)):
            return False
        if is_gestao:
            return _gestao_signals_sufficient(list(signals or []), list(evidence or []), company)
        # Fallback-only discovery is not specialty fit.
        if signals == ["fallback"] or set(str(s) for s in (signals or [])) == {"fallback"}:
            return False
        return True

    # Explicit router candidates with supporting signals or evidence ids.
    for c in company.get("service_candidates") or []:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("service_id") or c.get("service_code") or "").strip()
        if not sid:
            continue
        if sid != svc and svc not in sid and sid not in svc:
            if sid.upper() != svc.upper():
                continue
        signals = c.get("supporting_signal_ids") or c.get("supporting_signals") or []
        evidence = c.get("evidence_ids") or []
        if _ok(list(signals or []), list(evidence or [])):
            return True
    ps = company.get("primary_service")
    if isinstance(ps, dict):
        signals = ps.get("supporting_signal_ids") or ps.get("supporting_signals") or []
        evidence = ps.get("evidence_ids") or []
        if _ok(list(signals or []), list(evidence or [])):
            return True
    # Bridge/feed may flatten signals at company root
    root_signals = company.get("supporting_signal_ids") or company.get("service_supporting_signal_ids")
    root_ev = company.get("service_evidence_ids") or company.get("fact_evidence_ids")
    if _ok(list(root_signals or []), list(root_ev or [])):
        return True
    return False


def evaluate_copy_context_ready(
    company: dict[str, Any] | None, *, service_code: str | None = None
) -> CopyContextResult:
    """COPY_CONTEXT_READY: why you/now, fact, service, micro-offer, evidence, CTA."""
    missing: list[str] = []
    reasons: list[str] = []
    if not company:
        return CopyContextResult(False, reasons=["missing_company"], missing_fields=["company"])

    # Prefer sealed message_spine (complete copy package) over dossier-level
    # why_now dicts (trigger metadata) that stringify as generic/hollow.
    spine = company.get("message_spine") if isinstance(company.get("message_spine"), dict) else {}
    messaging = company.get("messaging") if isinstance(company.get("messaging"), dict) else {}

    why_you = _field_nonempty(
        spine.get("why_this_account")
        or company.get("why_this_account")
        or company.get("why_you")
        or messaging.get("why_this_account")
    )

    why_now_raw = company.get("why_now")
    why_now_from_dict = ""
    if isinstance(why_now_raw, dict):
        why_now_from_dict = _field_nonempty(
            why_now_raw.get("temporal_fact") or why_now_raw.get("summary") or why_now_raw.get("code")
        )
    why_now = _field_nonempty(
        spine.get("why_now")
        or (why_now_raw if isinstance(why_now_raw, str) else None)
        or why_now_from_dict
        or ((company.get("moment") or {}) if isinstance(company.get("moment"), dict) else {}).get("summary")
        or messaging.get("why_now")
    )

    observed = _field_nonempty(
        spine.get("observed_fact")
        or company.get("observed_fact")
        or company.get("factual_hook")
        or company.get("fact_to_mention")
        or messaging.get("fact_to_mention")
        or messaging.get("observed_fact")
    )
    svc = _field_nonempty(
        service_code
        or spine.get("service_id")
        or company.get("service_code")
        or company.get("canonical_service_code")
        or ((company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}).get("service_code")
        or (
            (company.get("primary_service") or {})
            if isinstance(company.get("primary_service"), dict)
            else company.get("primary_service")
        )
    )
    if isinstance(company.get("primary_service"), dict) and not svc:
        svc = _field_nonempty(
            company["primary_service"].get("service_id") or company["primary_service"].get("service_code")
        )

    micro = _field_nonempty(
        spine.get("micro_offer_code")
        or company.get("micro_offer_code")
        or company.get("micro_offer")
        or ((company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}).get("entry_offer")
        or ((company.get("offer") or {}) if isinstance(company.get("offer"), dict) else {}).get("micro_offer_code")
    )
    evidence = spine.get("fact_evidence_ids") or company.get("fact_evidence_ids") or company.get("evidence_ids")
    if not evidence and isinstance(company.get("evidence"), list):
        evidence = [str(e.get("id") if isinstance(e, dict) else e) for e in company["evidence"] if e]
    if not evidence and isinstance(company.get("moment"), dict):
        evidence = company["moment"].get("evidence_ids")
    has_evidence = bool(evidence) and (
        isinstance(evidence, list) and len(evidence) > 0 or isinstance(evidence, str) and evidence.strip()
    )
    cta = _field_nonempty(company.get("cta") or messaging.get("cta") or company.get("question_to_ask"))
    # Spine complete flag is authoritative when present
    if spine.get("complete") is True and company.get("message_spine_complete") is None:
        company = dict(company)
        company["message_spine_complete"] = True
    if spine.get("complete") is False:
        company = dict(company)
        company["message_spine_complete"] = False

    if not why_you or _is_generic_why(why_you, company=company):
        missing.append("why_this_account")
    if not why_now or _is_generic_why(why_now, company=company) or _is_hollow_observed_fact(why_now, company=company):
        missing.append("why_now")
    # Explicit weak temporal strength cannot be COPY_CONTEXT_READY.
    why_now_strength = str(company.get("why_now_strength") or "").upper()
    if "why_now_strength=weak" in (why_now or "").lower() or why_now_strength == "WEAK":
        missing.append("why_now")
        reasons.append("why_now_strength_weak")
    if not observed or _is_hollow_observed_fact(observed, company=company):
        missing.append("observed_fact")
    if not svc:
        missing.append("service_code")
    if not micro:
        missing.append("micro_offer_code")
    if not has_evidence:
        missing.append("evidence_ids")
    if not cta:
        missing.append("cta")
    # Message spine incomplete flag (if present)
    if company.get("message_spine_complete") is False:
        missing.append("message_spine_incomplete")

    ready = len(missing) == 0
    if ready:
        reasons.append("copy_context_complete")
    else:
        reasons.append("copy_context_incomplete")
        reasons.extend(f"missing:{m}" for m in missing)
    return CopyContextResult(copy_context_ready=ready, reasons=reasons, missing_fields=missing)


def _published_target_fit_from_company(
    company: dict[str, Any] | None,
    *,
    conn: Any | None = None,
    published_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Extract published materialization fields when present on the company row.

    Prefer confenge_company_target_fit_current projection over local re-scoring.
    """
    if not company:
        return None
    try:
        from scripts.confenge_target_fit.published import published_from_row_or_db

        return published_from_row_or_db(company, conn=conn, published_index=published_index)
    except Exception:  # noqa: BLE001 — soft import for envs without continuous-refresh
        # When live path is open, never fall back to sticky embeds.
        if conn is not None or published_index is not None:
            return None
        if company.get("target_fit_class"):
            return {
                "target_fit_class": company.get("target_fit_class"),
                "target_fit_confidence": company.get("target_fit_confidence"),
                "target_fit_version": company.get("target_fit_version"),
                "source_watermark": company.get("target_fit_source_watermark"),
                "computed_at": company.get("target_fit_computed_at"),
                "operational_status": company.get("target_fit_operational_status") or "ok",
                "target_fit_evidence": company.get("target_fit_evidence") or [],
                "company_key": company.get("company_key"),
            }
        return None


def _gate_from_published(
    company: dict[str, Any] | None,
    *,
    target_fit: TargetFitResult | None,
    canonical_universe_member: bool | None,
    conn: Any | None = None,
    published_index: dict[str, dict[str, Any]] | None = None,
) -> tuple[TargetFitResult, list[str], bool]:
    """Return (fit, extra_block_reasons, published_blocks_send).

    When published TARGET_* materialization is present, it is authoritative:
    non-CONFIRMED / stale / REFRESH_FAILED / TARGET_FIT_DOWNGRADE block send.

    When live path is open (``conn`` or ``published_index``) and no published
    row is found, fail closed — never re-score sticky embeds to send-ready.
    """
    extra: list[str] = []
    live_open = conn is not None or published_index is not None
    published = _published_target_fit_from_company(company, conn=conn, published_index=published_index)
    suppressed = False
    if company:
        suppressed = bool(
            company.get("target_fit_suppressed")
            or company.get("target_fit_downgrade")
            or company.get("target_fit_send_suppressed")
            or "TARGET_FIT_DOWNGRADE" in (company.get("suppression_reasons") or [])
        )

    if published is None:
        if live_open:
            # Store miss while live path open: never authorize from embeds.
            extra.append("TARGET_FIT_MISSING")
            extra.append("live_store_miss")
            fit = TargetFitResult(
                tier=TIER_OUT_OF_SCOPE,
                reasons=["TARGET_FIT_MISSING", "live_store_miss"],
                sector_fit="",
                canonical_universe_member=False,
                target_fit_class=TARGET_OUT_OF_SCOPE,
            )
            return fit, extra, True
        fit = target_fit or classify_target_fit_send_tier(company, canonical_universe_member=canonical_universe_member)
        return fit, extra, False

    try:
        from scripts.confenge_target_fit.published import (
            evaluate_published_send_gate,
            map_class_to_send_tier,
        )

        dl_wm = ""
        if company:
            dl_wm = str(company.get("datalake_watermark") or company.get("target_fit_datalake_watermark") or "")
        blocks, pub_reasons, _fresh = evaluate_published_send_gate(
            published=published,
            datalake_watermark=dl_wm,
            suppressed=suppressed,
        )
        tier = map_class_to_send_tier(str(published.get("target_fit_class") or ""))
        reasons = list(pub_reasons)
        reasons.append("published_target_fit")
        member = canonical_universe_member
        if member is None and target_fit is not None:
            member = target_fit.canonical_universe_member
        if member is None and company is not None:
            member = company.get(
                "construction_universe_member",
                company.get("canonical_universe_member"),
            )
        fit = TargetFitResult(
            tier=tier,
            reasons=reasons,
            sector_fit=str(published.get("sector_fit") or (company or {}).get("sector_fit") or ""),
            # Sector membership is independent from the mutable target-fit class.
            # An absent membership decision must not be promoted to true.
            canonical_universe_member=member is True,
        )
        if blocks:
            extra.extend(pub_reasons)
        return fit, extra, blocks
    except Exception:  # noqa: BLE001
        fit = target_fit or classify_target_fit_send_tier(company, canonical_universe_member=canonical_universe_member)
        return fit, extra, False


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
    contact: dict[str, Any] | None = None,
    provenance: ProvenanceTrustResult | dict[str, Any] | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    fixtures_dir_used: bool = False,
    synthetic_flag: bool = False,
    demo_flag: bool = False,
    provenance_chain: list[dict[str, Any]] | None = None,
    parent_provenance: dict[str, Any] | None = None,
    conn: Any | None = None,
    published_index: dict[str, dict[str, Any]] | None = None,
) -> EmailSendReadyResult:
    """EMAIL_SEND_READY requires target+service+contact+copy+not_blocked+fresh+provenance.

    When published target-fit materialization fields are present on ``company``
    (from confenge_company_target_fit_current / continuous refresh), they are
    authoritative: stale, REFRESH_FAILED, TARGET_FIT_DOWNGRADE, or non-CONFIRMED
    fail-closed. Warmbly must not re-score past this gate. Provenance taint
    (demo/fixture/synthetic) also fail-closed even if labels say VERIFIED.
    """
    reasons: list[str] = []
    email_norm = (email or "").strip() or None
    own = (ownership_status or "").strip().upper()
    ver = (verification_status or "").strip().upper()

    fit, published_blocks, published_blocks_send = _gate_from_published(
        company,
        target_fit=target_fit,
        canonical_universe_member=canonical_universe_member,
        conn=conn,
        published_index=published_index,
    )
    reasons.extend(published_blocks)
    mp = classify_mailbox_purpose(email_norm)
    suitability = SUITABLE
    channel_ok = True

    # ── PROVENANCE_CHAIN_VALID (recomputed; sticky VERIFIED never washes taint)
    prov_res: ProvenanceTrustResult
    if isinstance(provenance, ProvenanceTrustResult):
        prov_res = provenance
    elif isinstance(provenance, dict) and provenance.get("provenance_trust"):
        # Re-evaluate from dict fields so stale embeds cannot override.
        prov_res = evaluate_provenance_trust(
            email=email_norm or provenance.get("email"),
            source_type=source_type or provenance.get("source_type") or provenance.get("root_source_type"),
            source_url=source_url or provenance.get("source_url") or provenance.get("root_source_url"),
            observed_at=provenance.get("observed_at"),
            notes=provenance.get("notes"),
            official_domain=(company or {}).get("official_domain") if company else None,
            verification_status=ver or provenance.get("verification_status"),
            ownership_status=own or provenance.get("ownership_status"),
            fixtures_dir_used=fixtures_dir_used or bool(provenance.get("derived_from_fixture")),
            synthetic_flag=synthetic_flag or bool(provenance.get("derived_from_synthetic")),
            demo_flag=demo_flag or bool(provenance.get("derived_from_demo")),
            provenance_chain=provenance_chain or provenance.get("provenance_chain"),
            derived_from_fixture=provenance.get("derived_from_fixture"),
            parent_provenance=parent_provenance or provenance.get("parent_provenance"),
            verification_method=provenance.get("verification_method"),
        )
    elif contact is not None:
        c_for_prov = dict(contact)
        if email_norm and not c_for_prov.get("email"):
            c_for_prov["email"] = email_norm
        if own and not c_for_prov.get("ownership_status"):
            c_for_prov["ownership_status"] = own
        if ver and not c_for_prov.get("verification_status"):
            c_for_prov["verification_status"] = ver
        if company and company.get("official_domain") and not c_for_prov.get("official_domain"):
            c_for_prov["official_domain"] = company.get("official_domain")
        if fixtures_dir_used:
            c_for_prov["fixtures_dir_used"] = True
        if synthetic_flag:
            c_for_prov["synthetic"] = True
        if demo_flag:
            c_for_prov["demo"] = True
        if provenance_chain:
            c_for_prov["provenance_chain"] = provenance_chain
        if parent_provenance:
            c_for_prov["parent_provenance"] = parent_provenance
        if source_type and not (isinstance(c_for_prov.get("source"), dict) and c_for_prov["source"].get("source_type")):
            c_for_prov.setdefault("source", {})
            if isinstance(c_for_prov["source"], dict):
                c_for_prov["source"]["source_type"] = source_type
                if source_url:
                    c_for_prov["source"]["source_url"] = source_url
        prov_res = evaluate_contact_provenance(c_for_prov)
    else:
        prov_res = evaluate_provenance_trust(
            email=email_norm,
            source_type=source_type,
            source_url=source_url,
            official_domain=(company or {}).get("official_domain") if company else None,
            verification_status=ver,
            ownership_status=own,
            fixtures_dir_used=fixtures_dir_used,
            synthetic_flag=synthetic_flag,
            demo_flag=demo_flag,
            provenance_chain=provenance_chain,
            parent_provenance=parent_provenance,
        )

    prov_ok = not provenance_blocks_send(prov_res)
    if not prov_ok:
        reasons.append("provenance_chain_invalid")
        reasons.append(f"root_source_type:{prov_res.root_source_type}")
        for tr in prov_res.taint_reasons[:6]:
            reasons.append(f"taint:{tr}")
        suitability = UNSUITABLE_PROVENANCE
        channel_ok = False

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
        if suitability == SUITABLE:
            suitability = UNSUITABLE_MAILBOX
        channel_ok = False

    # Literal recipient contract: a mailbox is not a person. A final recipient
    # needs explicit, auditable person+role+email evidence and semantic dates.
    c = contact if isinstance(contact, dict) else {}
    c_source = c.get("source") if isinstance(c.get("source"), dict) else {}
    c_prov = c.get("provenance") if isinstance(c.get("provenance"), dict) else {}
    evidence_source = c_source or c_prov
    recipient_name = str(c.get("name") or "").strip()
    recipient_role = str(c.get("cargo") or c.get("role") or "").strip()
    evidence_refs = c.get("identity_evidence_urls")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    if evidence_source.get("source_url"):
        evidence_refs = [*evidence_refs, str(evidence_source["source_url"])]
    if evidence_source.get("source_document"):
        evidence_refs = [*evidence_refs, str(evidence_source["source_document"])]
    evidence_hash = str(c.get("evidence_sha256") or evidence_source.get("evidence_sha256") or "")
    valid_evidence_refs = bool(evidence_refs) and all(
        isinstance(ref, str) and bool(ref.strip()) for ref in evidence_refs
    )
    raw_evidence_date = (
        evidence_source.get("source_published_at")
        or evidence_source.get("observed_at")
        or evidence_source.get("verified_at")
    )
    try:
        semantic_date = (
            bool(raw_evidence_date)
            and datetime.fromisoformat(str(raw_evidence_date).replace("Z", "+00:00")) is not None
        )
    except (TypeError, ValueError):
        semantic_date = False
    human_evidence_ok = bool(
        recipient_name
        and recipient_role
        and c.get("email_explicitly_published") is True
        and c.get("name_explicitly_published") is True
        and c.get("role_explicitly_published") is True
        and c.get("human_identity_evidence_valid") is True
        and valid_evidence_refs
        and re.fullmatch(r"[0-9a-fA-F]{64}", evidence_hash)
        and semantic_date
        and mp.purpose == "UNKNOWN"
    )
    if human_evidence_ok:
        reasons.append("human_recipient_evidence_valid")
    else:
        reasons.append("human_recipient_evidence_incomplete")
        if not recipient_name:
            reasons.append("recipient_name_missing")
        if not recipient_role:
            reasons.append("recipient_role_missing")
        if c.get("email_explicitly_published") is not True:
            reasons.append("email_not_explicitly_published")
        if c.get("name_explicitly_published") is not True:
            reasons.append("recipient_name_not_explicitly_published")
        if c.get("role_explicitly_published") is not True:
            reasons.append("recipient_role_not_explicitly_published")
        if not valid_evidence_refs:
            reasons.append("recipient_evidence_reference_missing")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", evidence_hash):
            reasons.append("recipient_evidence_hash_missing_or_invalid")
        if not semantic_date:
            reasons.append("recipient_evidence_date_semantics_missing")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_HUMAN_EVIDENCE
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

    # REAL_CONTACT identity: domain must match company — sticky COMPANY_OWNED insufficient.
    # Skeptic cases: contato@qualidademineracao for QUALIDADE CONSTRUÇÕES, info@emkoelektronik
    # for EMKO CONSTRUTORA, comercial@lcmprojetos for LS ENGENHARIA must never be send-ready.
    identity_ok, identity_reason = email_matches_company_identity(
        email_norm,
        company,
        ownership_status=own,
    )
    if not identity_ok:
        reasons.append(identity_reason)
        reasons.append("sticky_ownership_insufficient_for_identity")
        # Do not overwrite a more specific prior unsuited state (e.g. provenance taint).
        if suitability == SUITABLE:
            suitability = UNSUITABLE_OWNERSHIP
        channel_ok = False
    elif identity_reason == "domain_aligned_with_company":
        reasons.append("domain_aligned_with_company")

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
        if f"target_fit:{fit.tier}" not in reasons:
            reasons.append(f"target_fit:{fit.tier}")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_TARGET
    if published_blocks_send:
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
                company["primary_service"].get("service_id") or company["primary_service"].get("service_code") or svc
            ).strip()
    service_fit_supported = _service_fit_supported(company, svc) if company else False
    if not svc:
        reasons.append("no_service_code")
        service_fit_supported = False
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_SERVICE
    elif not service_fit_supported:
        reasons.append("service_fit_unsupported")
        reasons.append(f"service_code:{svc}")
        if suitability == SUITABLE:
            suitability = UNSUITABLE_NO_SERVICE
    else:
        reasons.append(f"service_code:{svc}")
        reasons.append("service_fit_supported")

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

    contact_send_ready = (
        channel_ok
        and bool(email_norm)
        and own in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}
        and not dnc
        and not bounce
        and not account_blocked
        and contact_fresh
        and not mp.send_blocked
        and not published_blocks_send
        and prov_ok
        and human_evidence_ok
    )

    target_ok = (
        fit.tier in SEND_TIERS
        and fit.canonical_universe_member
        and fit.target_fit_class not in {TARGET_OUT_OF_SCOPE, TARGET_PROBABLE_RESEARCH}
        and not published_blocks_send
    )

    email_ready = (
        contact_send_ready
        and target_ok
        and service_fit_supported
        and has_ev
        and copy_ok
        and not published_blocks_send
        and prov_ok
    )
    # De-dupe reasons while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    reasons = deduped
    if email_ready and "all_gates_pass" not in reasons:
        reasons.append("all_gates_pass")
        reasons.append(f"provenance_trust:{prov_res.provenance_trust}")

    return EmailSendReadyResult(
        email_send_ready=email_ready,
        target_fit_send_tier=fit.tier,
        mailbox_purpose=mp.purpose,
        ownership_status=own,
        verification_status=ver,
        recipient_commercial_suitability=suitability,
        channel_send_eligibility=channel_ok and not mp.send_blocked and bool(email_norm) and prov_ok,
        reasons=reasons,
        email=email_norm,
        target_fit_class=fit.target_fit_class,
        copy_context_ready=copy_res.copy_context_ready,
        service_fit_supported=service_fit_supported,
        contact_send_ready=contact_send_ready,
        provenance_chain_valid=prov_ok,
        provenance_trust=prov_res.provenance_trust,
        root_source_type=prov_res.root_source_type,
        derived_from_fixture=prov_res.derived_from_fixture,
        human_recipient_evidence_valid=human_evidence_ok,
    )


def ready_supply_target(
    *,
    max_send_rate: int = 20,
    send_window_hours: int = 9,
    ready_supply_target_days: int = 2,
) -> int:
    """Companies EMAIL_SEND_READY to keep ahead of the queue."""
    return max(1, int(max_send_rate) * int(send_window_hours) * int(ready_supply_target_days))
