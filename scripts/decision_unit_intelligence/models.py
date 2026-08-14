"""Domain model: Decision-Unit candidates and Reachability routes.

Decision-Unit (who we want to reach) and Reachability (how we can get there)
are separate. A candidate is never a route. A route never invents a title.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum
from typing import Any

POLICY_VERSION = "dui.policy.v1"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: str) -> str:
    raw = "|".join(p.strip().lower() for p in parts if p is not None)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def fold_text(value: str | None) -> str:
    if not value:
        return ""
    import unicodedata

    s = unicodedata.normalize("NFKD", value)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def normalize_cnpj(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits.zfill(14) if digits else ""


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    e = value.strip().lower().rstrip(".,;:)>")
    return e if "@" in e and "." in e.split("@", 1)[-1] else None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    d = re.sub(r"\D", "", value)
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    return d if len(d) >= 8 else None


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    n = re.sub(r"\s+", " ", value.strip())
    return n if len(n) >= 3 else None


class EpistemicClass(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    CORROBORATED = "CORROBORATED"
    TECHNICALLY_VALIDATED = "TECHNICALLY_VALIDATED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


class DecisionRoleClass(str, Enum):
    SOCIO_ADMINISTRADOR = "socio_administrador"
    PROPRIETARIO = "proprietario"
    PRESIDENTE = "presidente"
    DIRETOR = "diretor"
    DIRETOR_COMERCIAL = "diretor_comercial"
    DIRETOR_ENGENHARIA = "diretor_engenharia"
    DIRETOR_OPERACOES = "diretor_operacoes"
    GERENTE_CONTRATOS = "gerente_contratos"
    GERENTE_LICITACOES = "gerente_licitacoes"
    LICITACOES = "licitacoes"
    CONTRATOS = "contratos"
    COMERCIAL = "comercial"
    FINANCEIRO = "financeiro"
    ADMINISTRATIVO = "administrativo"
    ENGENHARIA = "engenharia"
    ORCAMENTO = "orcamento"
    OPERACOES = "operacoes"
    RESPONSAVEL_TECNICO = "responsavel_tecnico"
    REPRESENTANTE_LEGAL = "representante_legal"
    PROCURADOR = "procurador"
    PREPOSTO = "preposto"
    SIGNATARIO = "signatario"
    SOCIO = "socio"
    TERCEIRO = "terceiro"
    SERVIDOR_PUBLICO = "servidor_publico"
    UNKNOWN = "unknown"


class ChannelType(str, Enum):
    DIRECT_EMAIL = "DIRECT_EMAIL"
    INFERRED_DIRECT_EMAIL = "INFERRED_DIRECT_EMAIL"
    DIRECT_PHONE = "DIRECT_PHONE"
    PROFESSIONAL_WHATSAPP = "PROFESSIONAL_WHATSAPP"
    PROFESSIONAL_PROFILE = "PROFESSIONAL_PROFILE"
    COMPANY_SWITCHBOARD = "COMPANY_SWITCHBOARD"
    ROLE_MAILBOX = "ROLE_MAILBOX"
    CONTACT_FORM = "CONTACT_FORM"
    GENERIC_CORPORATE_EMAIL = "GENERIC_CORPORATE_EMAIL"
    OTHER_PUBLIC_BUSINESS_ROUTE = "OTHER_PUBLIC_BUSINESS_ROUTE"


class RouteRelation(str, Enum):
    PERSON_OWNS_CHANNEL = "PERSON_OWNS_CHANNEL"
    ROUTES_TO_NAMED_PERSON = "ROUTES_TO_NAMED_PERSON"
    ROUTES_TO_ROLE = "ROUTES_TO_ROLE"
    ACCOUNT_LEVEL_ONLY = "ACCOUNT_LEVEL_ONLY"
    INFERRED_ASSOCIATION = "INFERRED_ASSOCIATION"
    CONTRADICTED = "CONTRADICTED"


class ReachabilityClass(str, Enum):
    R1_DIRECT = "R1_DIRECT"
    R2_HIGH_CONFIDENCE_DIRECT = "R2_HIGH_CONFIDENCE_DIRECT"
    R3_ROUTED_TO_NAMED_PERSON = "R3_ROUTED_TO_NAMED_PERSON"
    R4_ROLE_ROUTE = "R4_ROLE_ROUTE"
    R5_CORPORATE_ONLY = "R5_CORPORATE_ONLY"
    R0_NO_ACTIONABLE_ROUTE = "R0_NO_ACTIONABLE_ROUTE"
    BLOCKED = "BLOCKED"


class ActionMode(str, Enum):
    HUMAN_REVIEW_EMAIL = "HUMAN_REVIEW_EMAIL"
    MANUAL_CALL = "MANUAL_CALL"
    MANUAL_WHATSAPP = "MANUAL_WHATSAPP"
    MANUAL_PROFESSIONAL_SOCIAL = "MANUAL_PROFESSIONAL_SOCIAL"
    MANUAL_ROUTED_CALL = "MANUAL_ROUTED_CALL"
    ROLE_EMAIL = "ROLE_EMAIL"
    CONTACT_FORM = "CONTACT_FORM"
    GENERIC_EMAIL_LAST_RESORT = "GENERIC_EMAIL_LAST_RESORT"
    NEEDS_ENRICHMENT = "NEEDS_ENRICHMENT"
    BLOCKED = "BLOCKED"
    NO_ACTIONABLE_ROUTE = "NO_ACTIONABLE_ROUTE"


class AccountTerminal(str, Enum):
    ACTIONABLE_ROUTE = "ACTIONABLE_ROUTE"
    DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED = (
        "DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED"
    )
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"
    NEEDS_ENRICHMENT = "NEEDS_ENRICHMENT"


class PersonRelation(str, Enum):
    COMPANY_MEMBER = "COMPANY_MEMBER"
    THIRD_PARTY = "THIRD_PARTY"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    OTHER_BIDDER = "OTHER_BIDDER"
    UNKNOWN = "UNKNOWN"


class OwnershipStatus(str, Enum):
    COMPANY_OWNED = "COMPANY_OWNED"
    PERSON_PROFESSIONAL = "PERSON_PROFESSIONAL"
    THIRD_PARTY = "THIRD_PARTY"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


class SuppressionState(str, Enum):
    NONE = "NONE"
    DNC = "DNC"
    OPT_OUT = "OPT_OUT"
    HARD_BOUNCE = "HARD_BOUNCE"
    BLOCKED = "BLOCKED"


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class StopReason(str, Enum):
    POSITIVE_ROUTE = "POSITIVE_ROUTE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    POLICY_SKIP = "POLICY_SKIP"
    YIELD_FAIL_FAST = "YIELD_FAIL_FAST"
    DRY_RUN = "DRY_RUN"


FORBIDDEN_ACTION_MODES = frozenset({"AUTO_SEND", "AUTO_DISPATCH", "SEND"})


@dataclass
class FieldAspect:
    """One epistemic aspect of a field (person, role, email, domain, …)."""

    field: str
    epistemic_class: EpistemicClass
    method: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "epistemic_class": self.epistemic_class.value,
            "method": self.method,
            "note": self.note,
        }


@dataclass
class FieldEvidence:
    evidence_id: str
    field: str
    value: str | None
    epistemic_class: EpistemicClass
    source_type: str
    source_url: str | None = None
    source_id: str | None = None
    document_id: str | None = None
    document_sha256: str | None = None
    page: int | None = None
    section: str | None = None
    evidence_snippet: str | None = None
    observed_at: str | None = None
    published_at: str | None = None
    extraction_method: str | None = None
    extractor_version: str | None = None
    contract_id: str | None = None
    process_id: str | None = None
    aspects: list[FieldAspect] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["epistemic_class"] = self.epistemic_class.value
        d["aspects"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.aspects]
        return d


@dataclass
class PersonObservation:
    """A provenanced observation of a person/role. Never invents cargo."""

    observation_id: str
    company_entity_id: str
    person_name: str | None
    observed_role: str | None
    normalized_role_class: DecisionRoleClass = DecisionRoleClass.UNKNOWN
    relation: PersonRelation = PersonRelation.UNKNOWN
    source_type: str = "unknown"
    source_url: str | None = None
    document_id: str | None = None
    document_type: str | None = None
    page: int | None = None
    snippet: str | None = None
    observed_at: str | None = None
    signature_context: str | None = None
    process_role: str | None = None
    epistemic_class: EpistemicClass = EpistemicClass.OBSERVED
    evidence_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["normalized_role_class"] = self.normalized_role_class.value
        d["relation"] = self.relation.value
        d["epistemic_class"] = self.epistemic_class.value
        return d


@dataclass
class ChannelObservation:
    observation_id: str
    company_entity_id: str
    channel_type: ChannelType
    channel_value: str | None
    person_name: str | None = None
    target_role: str | None = None
    source_type: str = "unknown"
    source_url: str | None = None
    document_id: str | None = None
    page: int | None = None
    snippet: str | None = None
    observed_at: str | None = None
    epistemic_class: EpistemicClass = EpistemicClass.OBSERVED
    ownership: OwnershipStatus = OwnershipStatus.UNKNOWN
    evidence_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["channel_type"] = self.channel_type.value
        d["epistemic_class"] = self.epistemic_class.value
        d["ownership"] = self.ownership.value
        return d


@dataclass
class SearchAttempt:
    attempt_id: str
    company_entity_id: str
    tier: int
    provider_id: str
    source: str
    status: str
    reason: str | None = None
    documents_checked: int = 0
    queries: list[str] = field(default_factory=list)
    bytes_touched: int = 0
    duration_ms: int = 0
    cost_brl: float = 0.0
    blocked: bool = False
    stop_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostObservation:
    cost_brl: float = 0.0
    duration_ms: int = 0
    bytes_touched: int = 0
    provider_calls: int = 0

    def add(self, other: CostObservation) -> None:
        self.cost_brl += other.cost_brl
        self.duration_ms += other.duration_ms
        self.bytes_touched += other.bytes_touched
        self.provider_calls += other.provider_calls

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictRecord:
    conflict_id: str
    topic: str
    left: str
    right: str
    resolution: str
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionUnitCandidate:
    candidate_id: str
    company_entity_id: str
    person_id: str
    person_name: str | None
    observed_roles: list[str] = field(default_factory=list)
    decision_role_class: DecisionRoleClass = DecisionRoleClass.UNKNOWN
    decision_relevance: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    authority_signal: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    operational_relevance: ConfidenceLevel = ConfidenceLevel.NONE
    service_context: str = "generic"
    why_now_context: str | None = None
    identity_confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    role_confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    suitability: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    service_fit: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_quality: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_ids: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    relation: PersonRelation = PersonRelation.COMPANY_MEMBER
    representation_signal: ConfidenceLevel = ConfidenceLevel.NONE
    inferred_decision_relevance: str | None = None
    observation_count: int = 0
    signature_count: int = 0
    source_count: int = 0
    aspects: list[FieldAspect] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision_role_class"] = self.decision_role_class.value
        d["decision_relevance"] = self.decision_relevance.value
        d["authority_signal"] = self.authority_signal.value
        d["operational_relevance"] = self.operational_relevance.value
        d["identity_confidence"] = self.identity_confidence.value
        d["role_confidence"] = self.role_confidence.value
        d["suitability"] = self.suitability.value
        d["service_fit"] = self.service_fit.value
        d["evidence_quality"] = self.evidence_quality.value
        d["relation"] = self.relation.value
        d["representation_signal"] = self.representation_signal.value
        d["aspects"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.aspects]
        return d


@dataclass
class ReachabilityRoute:
    route_id: str
    company_entity_id: str
    channel_type: ChannelType
    reachability_class: ReachabilityClass
    action_mode: ActionMode
    decision_unit_candidate_id: str | None = None
    target_role: str | None = None
    channel_value: str | None = None
    route_relation: RouteRelation = RouteRelation.ACCOUNT_LEVEL_ONLY
    epistemic_class: EpistemicClass = EpistemicClass.UNKNOWN
    source_type: str | None = None
    source_url: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    route_confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    freshness: FreshnessState = FreshnessState.UNKNOWN
    ownership: OwnershipStatus = OwnershipStatus.UNKNOWN
    suppression: SuppressionState = SuppressionState.NONE
    reason_codes: list[str] = field(default_factory=list)
    next_action: str | None = None
    aspects: list[FieldAspect] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["channel_type"] = self.channel_type.value
        d["reachability_class"] = self.reachability_class.value
        d["action_mode"] = self.action_mode.value
        d["route_relation"] = self.route_relation.value
        d["epistemic_class"] = self.epistemic_class.value
        d["route_confidence"] = self.route_confidence.value
        d["freshness"] = self.freshness.value
        d["ownership"] = self.ownership.value
        d["suppression"] = self.suppression.value
        d["aspects"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.aspects]
        return d


@dataclass
class Recommendation:
    primary_target_id: str | None
    primary_route_id: str | None
    secondary_target_ids: list[str] = field(default_factory=list)
    alternative_route_ids: list[str] = field(default_factory=list)
    why_this_person: list[str] = field(default_factory=list)
    why_this_route: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    next_action: str | None = None
    action_mode: ActionMode = ActionMode.NEEDS_ENRICHMENT
    reachability_class: ReachabilityClass | None = None
    policy_version: str = POLICY_VERSION
    warnings: list[str] = field(default_factory=list)
    dimensions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action_mode"] = self.action_mode.value
        d["reachability_class"] = (
            self.reachability_class.value if self.reachability_class else None
        )
        return d


@dataclass
class SearchLedger:
    known_evidence_checked: int = 0
    contracts_checked: int = 0
    processes_checked: int = 0
    documents_checked: int = 0
    company_site_checked: bool = False
    search_queries: list[str] = field(default_factory=list)
    provider_attempts: int = 0
    blocked_sources: list[str] = field(default_factory=list)
    tiers_completed: list[int] = field(default_factory=list)
    duration_ms: int = 0
    cost_brl: float = 0.0
    bytes_touched: int = 0
    stop_reason: str | None = None
    next_action: str | None = None
    attempts: list[SearchAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["attempts"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.attempts]
        return d


@dataclass
class AccountInvestigation:
    company_entity_id: str
    cnpj: str
    legal_name: str | None
    service_context: str
    why_now: str | None
    candidates: list[DecisionUnitCandidate] = field(default_factory=list)
    routes: list[ReachabilityRoute] = field(default_factory=list)
    recommendation: Recommendation | None = None
    ledger: SearchLedger = field(default_factory=SearchLedger)
    terminal: AccountTerminal = AccountTerminal.NEEDS_ENRICHMENT
    evidence: list[FieldEvidence] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    policy_version: str = POLICY_VERSION
    provider_version: str = "dui.providers.v1"
    built_at: str = field(default_factory=now_iso)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "confenge.decision_unit_account.v1",
            "company_entity_id": self.company_entity_id,
            "cnpj": self.cnpj,
            "legal_name": self.legal_name,
            "service_context": self.service_context,
            "why_now": self.why_now,
            "candidates": [c.to_dict() for c in self.candidates],
            "routes": [r.to_dict() for r in self.routes],
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
            "ledger": self.ledger.to_dict(),
            "terminal": self.terminal.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "reason_codes": self.reason_codes,
            "warnings": self.warnings,
            "policy_version": self.policy_version,
            "provider_version": self.provider_version,
            "built_at": self.built_at,
            "extra": self.extra,
        }


def level_rank(level: ConfidenceLevel | str | None) -> int:
    mapping = {
        ConfidenceLevel.HIGH: 3,
        ConfidenceLevel.MEDIUM: 2,
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.UNKNOWN: 0,
        ConfidenceLevel.NONE: 0,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "UNKNOWN": 0,
        "NONE": 0,
    }
    return mapping.get(level, 0)  # type: ignore[arg-type]


def dataclass_from_dict(cls: type[Any], payload: dict[str, Any]) -> Any:
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in payload.items() if k in names})


def dumps_stable(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
