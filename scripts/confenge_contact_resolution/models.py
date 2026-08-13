"""Versioned contracts for CONFENGE business contact candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from scripts.confenge_contact_resolution import SCHEMA_ID, SCHEMA_VERSION


class RoleClass(StrEnum):
    OWNER = "owner"
    DIRETORIA = "diretoria"
    COMERCIAL = "comercial"
    CONTRATOS = "contratos"
    ENGENHARIA = "engenharia"
    LICITACOES = "licitações"
    FINANCEIRO = "financeiro"
    ADMIN = "admin"
    GENERAL = "general"
    ACCOUNTING_EXTERNAL = "accounting_external"
    LEGAL_EXTERNAL = "legal_external"
    CONSULTANT_EXTERNAL = "consultant_external"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    """How the contact address was obtained / checked (not outreach result)."""

    OBSERVED = "OBSERVED"  # exact value published by a source
    VERIFIED = "VERIFIED"  # multi-source / ownership-confirmed public channel
    CANDIDATE_UNVERIFIED = "CANDIDATE_UNVERIFIED"  # pattern-guessed; never enrollable
    PATTERN_GUESS = "PATTERN_GUESS"  # alias epistemic for guessed addresses
    SYNTAX_INVALID = "SYNTAX_INVALID"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class OwnershipStatus(StrEnum):
    """Whether the channel belongs to the target company (not a third party)."""

    COMPANY_OWNED = "COMPANY_OWNED"
    LIKELY_COMPANY_OWNED = "LIKELY_COMPANY_OWNED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    THIRD_PARTY_SERVICE_PROVIDER = "THIRD_PARTY_SERVICE_PROVIDER"
    SHARED_EXTERNAL_CONTACT = "SHARED_EXTERNAL_CONTACT"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class ThirdPartyType(StrEnum):
    ACCOUNTING = "ACCOUNTING"
    LEGAL = "LEGAL"
    CONSULTING = "CONSULTING"
    BPO = "BPO"
    VIRTUAL_OFFICE = "VIRTUAL_OFFICE"
    SOFTWARE = "SOFTWARE"
    MARKETPLACE = "MARKETPLACE"
    ASSOCIATION = "ASSOCIATION"
    OTHER = "OTHER"


class CompanyProcessingState(StrEnum):
    """Per-company enrichment pipeline state."""

    NOT_STARTED = "NOT_STARTED"
    LOCAL_SEARCH = "LOCAL_SEARCH"
    OFFICIAL_WEB_SEARCH = "OFFICIAL_WEB_SEARCH"
    PUBLIC_WEB_SEARCH = "PUBLIC_WEB_SEARCH"
    FOUND_VERIFIED = "FOUND_VERIFIED"
    FOUND_REVIEW_REQUIRED = "FOUND_REVIEW_REQUIRED"
    NO_CONTACT = "NO_CONTACT"
    RETRY_LATER = "RETRY_LATER"
    FAILED = "FAILED"


class CommercialContactState(StrEnum):
    """Commercial readiness after enrichment (does not discard the lead)."""

    NO_CONTACT_YET = "NO_CONTACT_YET"
    CONTACT_REVIEW_REQUIRED = "CONTACT_REVIEW_REQUIRED"
    CONTACT_READY = "CONTACT_READY"


class FreshnessClass(StrEnum):
    CURRENT = "CURRENT"
    RECENT = "RECENT"
    STALE = "STALE"
    UNKNOWN_DATE = "UNKNOWN_DATE"


class PhoneType(StrEnum):
    MOBILE = "mobile"
    LANDLINE = "landline"
    UNKNOWN = "unknown"


class WhatsAppConsent(StrEnum):
    """Public phone ≠ opt-in. Default UNKNOWN / NO_OPT_IN."""

    UNKNOWN = "UNKNOWN"
    NO_OPT_IN = "NO_OPT_IN"
    OPTED_IN = "OPTED_IN"


class ServiceContext(StrEnum):
    """Service context that shifts role priority for ranking."""

    CLAIMS_REAJUSTE = "claims_reajuste"
    LICITACOES = "licitações"
    ORCAMENTO_MEDICOES = "orcamento_medicoes"
    GENERIC = "generic"


# Only these ownership states may auto-enroll into supervised outreach queues.
ENROLLABLE_OWNERSHIP = frozenset(
    {
        OwnershipStatus.COMPANY_OWNED.value,
        OwnershipStatus.HUMAN_CONFIRMED.value,
    }
)

ROLE_CLASS_VALUES = frozenset(r.value for r in RoleClass)
VERIFICATION_STATUS_VALUES = frozenset(v.value for v in VerificationStatus)
OWNERSHIP_STATUS_VALUES = frozenset(o.value for o in OwnershipStatus)
THIRD_PARTY_TYPE_VALUES = frozenset(t.value for t in ThirdPartyType)
PHONE_TYPE_VALUES = frozenset(p.value for p in PhoneType)
WHATSAPP_CONSENT_VALUES = frozenset(w.value for w in WhatsAppConsent)


@dataclass
class SourceProvenance:
    source_type: str  # registry | site | public_docs | contact_page | web_search | human_outcome
    source_url: str | None = None
    source_document: str | None = None
    # ``source_date`` remains as a compatibility alias. New producers must use
    # the semantic fields below and must never copy observation time into it.
    source_date: str | None = None
    source_published_at: str | None = None  # date explicitly declared by source
    observed_at: str | None = None  # when the public source was actually read
    verified_at: str | None = None  # when an additional active check ran
    evidence_sha256: str | None = None  # stable hash; excludes observation time
    notes: str | None = None

    def __post_init__(self) -> None:
        # Legacy adapters used source_date for a genuine document/publication
        # date. Preserve that meaning while exposing it explicitly.
        if self.source_date and not self.source_published_at:
            self.source_published_at = self.source_date

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailVerificationLayers:
    """Independent layers — never send verification messages."""

    syntactic_ok: bool | None = None
    domain_ok: bool | None = None
    mx_ok: bool | None = None
    mx_checked: bool = False
    pattern_guessed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WhatsAppBlock:
    consent_status: str = WhatsAppConsent.UNKNOWN.value
    consent_provenance: str | None = None
    e164: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContactCandidate:
    """One business contact candidate for an account/CNPJ."""

    candidate_id: str
    cnpj14: str
    account_key: str
    name: str | None = None
    cargo: str | None = None
    role_class: str = RoleClass.GENERIC.value
    email: str | None = None
    email_display: str | None = None  # exact preserved string for UI
    phone_raw: str | None = None
    phone_e164: str | None = None
    phone_type: str = PhoneType.UNKNOWN.value
    site: str | None = None
    linkedin_public: str | None = None
    source: SourceProvenance = field(default_factory=lambda: SourceProvenance(source_type="unknown"))
    verification_status: str = VerificationStatus.NOT_AVAILABLE.value
    email_layers: EmailVerificationLayers = field(default_factory=EmailVerificationLayers)
    confidence: float = 0.0
    recommended: bool = False
    recommendation_reason: str | None = None
    freshness: float = 1.0  # 1.0 = fresh; decays with age
    freshness_days: int | None = None
    freshness_class: str = FreshnessClass.UNKNOWN_DATE.value
    dnc: bool = False
    bounce: bool = False
    dnc_reason: str | None = None
    whatsapp: WhatsAppBlock = field(default_factory=WhatsAppBlock)
    rank_score: float = 0.0
    rank_explain: list[str] = field(default_factory=list)
    enrollable: bool = False  # only COMPANY_OWNED / HUMAN_CONFIRMED
    epistemic_class: str = "OBSERVED_PUBLIC"  # OBSERVED_PUBLIC | INFERRED | HUMAN_OUTCOME
    ownership_status: str = OwnershipStatus.UNRESOLVED.value
    ownership_reason: str | None = None
    verification_reason: str | None = None
    third_party_type: str | None = None
    associated_company_count: int = 1
    independent_sources_count: int = 1
    domain_matches_company: bool | None = None
    found_on_official_source: bool = False
    found_on_company_document: bool = False
    source_urls: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    contact_type: str = "UNKNOWN"  # EMAIL | PHONE | BOTH
    limitations: list[str] = field(default_factory=list)
    email_explicitly_published: bool = False
    name_explicitly_published: bool = False
    role_explicitly_published: bool = False
    human_identity_evidence_valid: bool = False
    identity_evidence_urls: list[str] = field(default_factory=list)
    evidence_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AccountContactResolution:
    """Resolution record for one CNPJ/account — zero or more candidates."""

    schema_id: str = SCHEMA_ID
    schema_version: str = SCHEMA_VERSION
    cnpj14: str = ""
    account_key: str = ""
    razao_social: str | None = None
    nome_fantasia: str | None = None
    official_domain: str | None = None
    service_context: str = ServiceContext.GENERIC.value
    small_firm: bool = False
    candidates: list[ContactCandidate] = field(default_factory=list)
    rejected_contacts: list[dict[str, Any]] = field(default_factory=list)
    recommended_candidate_id: str | None = None
    absence_reason: str | None = None  # set when no candidates
    processing_state: str = CompanyProcessingState.NOT_STARTED.value
    commercial_contact_state: str = CommercialContactState.NO_CONTACT_YET.value
    next_contact_resolution_at: str | None = None
    adapters_used: list[str] = field(default_factory=list)
    adapters_skipped: list[str] = field(default_factory=list)
    cache_hit: bool = False
    resolved_at: str | None = None
    limitations: list[str] = field(default_factory=list)
    investigation_outcome: str | None = None  # CONTACT_FOUND | BUDGET_EXHAUSTED | ...
    economic_group_id: str | None = None
    domain_class: str | None = None
    discovery_stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "cnpj14": self.cnpj14,
            "account_key": self.account_key,
            "razao_social": self.razao_social,
            "nome_fantasia": self.nome_fantasia,
            "official_domain": self.official_domain,
            "service_context": self.service_context,
            "small_firm": self.small_firm,
            "candidates": [c.as_dict() for c in self.candidates],
            "rejected_contacts": list(self.rejected_contacts),
            "recommended_candidate_id": self.recommended_candidate_id,
            "absence_reason": self.absence_reason,
            "processing_state": self.processing_state,
            "commercial_contact_state": self.commercial_contact_state,
            "next_contact_resolution_at": self.next_contact_resolution_at,
            "adapters_used": list(self.adapters_used),
            "adapters_skipped": list(self.adapters_skipped),
            "cache_hit": self.cache_hit,
            "resolved_at": self.resolved_at,
            "limitations": list(self.limitations),
            "investigation_outcome": self.investigation_outcome,
            "economic_group_id": self.economic_group_id,
            "domain_class": self.domain_class,
            "discovery_stats": dict(self.discovery_stats or {}),
        }


@dataclass
class RawObservation:
    """Provenance-bearing raw observation from one adapter (pre-merge)."""

    adapter: str
    cnpj14: str
    name: str | None = None
    cargo: str | None = None
    email: str | None = None
    phone_raw: str | None = None
    site: str | None = None
    linkedin_public: str | None = None
    source: SourceProvenance = field(default_factory=lambda: SourceProvenance(source_type="unknown"))
    pattern_guessed_email: bool = False
    dnc: bool = False
    bounce: bool = False
    dnc_reason: str | None = None
    whatsapp_consent: str = WhatsAppConsent.UNKNOWN.value
    whatsapp_consent_provenance: str | None = None
    company_size: str | None = None
    razao_social: str | None = None
    nome_fantasia: str | None = None
    human_confirmed: bool = False
    art_crea_only: bool = False  # engineer from ART/CREA — not auto commercial
    context_text: str | None = None  # surrounding page/document text for third-party signals
    epistemic_class: str = "OBSERVED_PUBLIC"
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_manifest(
    *,
    run_id: str,
    mode: str,
    service_context: str,
    output_dir: str,
    input_count: int = 0,
) -> dict[str, Any]:
    return {
        "schema_id": "confenge-contact-resolution-manifest-v1",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,  # single | batch
        "service_context": service_context,
        "output_dir": output_dir,
        "candidates_artifact": "confenge-contact-candidates-v1.jsonl",
        "input_count": input_count,
        "resolved_count": 0,
        "with_candidates": 0,
        "with_recommended": 0,
        "absence_count": 0,
        "cache_hits": 0,
        "adapters": [],
        "started_at": None,
        "finished_at": None,
        "limitations": [
            "Public phone does not imply WhatsApp opt-in.",
            "Pattern-guessed emails are CANDIDATE_UNVERIFIED and never enrollable.",
            "Only COMPANY_OWNED and HUMAN_CONFIRMED contacts are enrollable.",
            "Absence of contact is preferred over attributing a third-party channel.",
            "No private social scraping; optional web search is interface-only.",
            "MX/domain checks never send mail.",
        ],
        "checksum_sha256": None,
        "ok": False,
    }
