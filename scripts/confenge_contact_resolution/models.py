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
    GENERIC = "generic"


class VerificationStatus(StrEnum):
    """How the contact address was obtained / checked (not outreach result)."""

    OBSERVED = "OBSERVED"  # exact value published by a source
    CANDIDATE_UNVERIFIED = "CANDIDATE_UNVERIFIED"  # pattern-guessed; never enrollable
    SYNTAX_INVALID = "SYNTAX_INVALID"
    NOT_AVAILABLE = "NOT_AVAILABLE"


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


ROLE_CLASS_VALUES = frozenset(r.value for r in RoleClass)
VERIFICATION_STATUS_VALUES = frozenset(v.value for v in VerificationStatus)
PHONE_TYPE_VALUES = frozenset(p.value for p in PhoneType)
WHATSAPP_CONSENT_VALUES = frozenset(w.value for w in WhatsAppConsent)


@dataclass
class SourceProvenance:
    source_type: str  # registry | site | public_docs | contact_page | web_search | human_outcome
    source_url: str | None = None
    source_document: str | None = None
    source_date: str | None = None  # ISO date when known
    observed_at: str | None = None  # ISO datetime of observation run
    notes: str | None = None

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
    dnc: bool = False
    bounce: bool = False
    dnc_reason: str | None = None
    whatsapp: WhatsAppBlock = field(default_factory=WhatsAppBlock)
    rank_score: float = 0.0
    rank_explain: list[str] = field(default_factory=list)
    enrollable: bool = False  # never true for CANDIDATE_UNVERIFIED
    epistemic_class: str = "OBSERVED_PUBLIC"  # OBSERVED_PUBLIC | INFERRED | HUMAN_OUTCOME
    limitations: list[str] = field(default_factory=list)

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
    service_context: str = ServiceContext.GENERIC.value
    small_firm: bool = False
    candidates: list[ContactCandidate] = field(default_factory=list)
    recommended_candidate_id: str | None = None
    absence_reason: str | None = None  # set when no candidates
    adapters_used: list[str] = field(default_factory=list)
    adapters_skipped: list[str] = field(default_factory=list)
    cache_hit: bool = False
    resolved_at: str | None = None
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "cnpj14": self.cnpj14,
            "account_key": self.account_key,
            "razao_social": self.razao_social,
            "service_context": self.service_context,
            "small_firm": self.small_firm,
            "candidates": [c.as_dict() for c in self.candidates],
            "recommended_candidate_id": self.recommended_candidate_id,
            "absence_reason": self.absence_reason,
            "adapters_used": list(self.adapters_used),
            "adapters_skipped": list(self.adapters_skipped),
            "cache_hit": self.cache_hit,
            "resolved_at": self.resolved_at,
            "limitations": list(self.limitations),
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
            "No private social scraping; optional web search is interface-only.",
            "MX/domain checks never send mail.",
        ],
        "checksum_sha256": None,
        "ok": False,
    }
