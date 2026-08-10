"""Canonical models: public process graph, contact observations, dossier."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from scripts.confenge_process_enrichment.states import InvestigationState, TerminalState


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def content_hash(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EpistemicClass(StrEnum):
    COMPANY_DECLARED = "COMPANY_DECLARED"
    ADMIN_RECORDED_COMPANY_REP = "ADMIN_RECORDED_COMPANY_REP"
    COMPANY_DOMAIN_OBSERVED = "COMPANY_DOMAIN_OBSERVED"
    THIRD_PARTY_REFERENCE = "THIRD_PARTY_REFERENCE"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    OTHER_BIDDER = "OTHER_BIDDER"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"


# Classes allowed to feed commercial contact export / Warmbly
COMMERCIAL_EPISTEMIC = frozenset(
    {
        EpistemicClass.COMPANY_DECLARED,
        EpistemicClass.ADMIN_RECORDED_COMPANY_REP,
        EpistemicClass.COMPANY_DOMAIN_OBSERVED,
    }
)

# Never export as lead contacts
BLOCKED_EPISTEMIC = frozenset(
    {
        EpistemicClass.PUBLIC_OFFICIAL,
        EpistemicClass.OTHER_BIDDER,
        EpistemicClass.UNKNOWN_ENTITY,
        EpistemicClass.THIRD_PARTY_REFERENCE,
    }
)


@dataclass
class ProvenanceEdge:
    source: str
    source_url: str | None = None
    source_identifier: str | None = None
    observed_at: str = field(default_factory=_now_iso)
    last_verified_at: str | None = None
    confidence: float = 1.0
    content_hash: str | None = None
    notes: str | None = None
    join_method: str | None = None  # e.g. numeroControlePNCP, process_number, probabilistic

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessDocumentRef:
    document_id: str
    title: str | None = None
    url: str | None = None
    category: str | None = None
    yield_score: float = 0.0
    sha256: str | None = None
    fetched: bool = False
    parsed: bool = False
    company_authored_likely: bool = False
    size_bytes: int | None = None
    mime: str | None = None
    provenance: ProvenanceEdge | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.provenance:
            d["provenance"] = self.provenance.to_dict()
        return d


@dataclass
class ContractNode:
    contract_id: str
    supplier_cnpj: str
    contracting_authority_cnpj: str | None = None
    contracting_authority_name: str | None = None
    pncp_control_number: str | None = None  # numeroControlePNCP / compra
    contract_number: str | None = None
    administrative_process_number: str | None = None
    year: int | None = None
    sequential: int | None = None
    uf: str | None = None
    municipality: str | None = None
    object_summary: str | None = None
    signed_at: str | None = None
    vigency_end: str | None = None
    value_global: float | None = None
    originating_procurement_id: str | None = None
    documents: list[ProcessDocumentRef] = field(default_factory=list)
    amendments: list[dict[str, Any]] = field(default_factory=list)
    external_process_sources: list[dict[str, Any]] = field(default_factory=list)
    edges: list[ProvenanceEdge] = field(default_factory=list)
    raw_keys: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "supplier_cnpj": self.supplier_cnpj,
            "contracting_authority_cnpj": self.contracting_authority_cnpj,
            "contracting_authority_name": self.contracting_authority_name,
            "pncp_control_number": self.pncp_control_number,
            "contract_number": self.contract_number,
            "administrative_process_number": self.administrative_process_number,
            "year": self.year,
            "sequential": self.sequential,
            "uf": self.uf,
            "municipality": self.municipality,
            "object_summary": self.object_summary,
            "signed_at": self.signed_at,
            "vigency_end": self.vigency_end,
            "value_global": self.value_global,
            "originating_procurement_id": self.originating_procurement_id,
            "documents": [d.to_dict() for d in self.documents],
            "amendments": self.amendments,
            "external_process_sources": self.external_process_sources,
            "edges": [e.to_dict() for e in self.edges],
            "raw_keys": self.raw_keys,
        }


@dataclass
class PublicProcessGraph:
    """confenge.public_process_graph.v1"""

    schema_id: str = "confenge.public_process_graph.v1"
    schema_version: str = "1.0.0"
    account_cnpj: str = ""
    razao_social: str | None = None
    contracts: list[ContractNode] = field(default_factory=list)
    built_at: str = field(default_factory=_now_iso)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "account_cnpj": self.account_cnpj,
            "razao_social": self.razao_social,
            "contracts": [c.to_dict() for c in self.contracts],
            "built_at": self.built_at,
            "limitations": self.limitations,
            "contract_count": len(self.contracts),
            "process_numbers": sorted(
                {c.administrative_process_number for c in self.contracts if c.administrative_process_number}
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ContactObservation:
    """Single provenanced observation of a commercial channel/person."""

    email: str | None = None
    phone: str | None = None
    person_name: str | None = None
    role_observed: str | None = None
    company_cnpj: str | None = None
    source_document_id: str | None = None
    source_url: str | None = None
    page: int | None = None
    evidence_text_hash: str | None = None
    observation_date: str | None = None
    epistemic_class: EpistemicClass = EpistemicClass.UNKNOWN_ENTITY
    document_type: str | None = None
    contract_id: str | None = None
    pattern_guessed: bool = False
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["epistemic_class"] = self.epistemic_class.value
        return d

    def is_commercially_usable(self) -> bool:
        if self.pattern_guessed:
            return False
        if self.epistemic_class in BLOCKED_EPISTEMIC:
            return False
        if not self.email and not self.phone:
            return False
        return self.epistemic_class in COMMERCIAL_EPISTEMIC


@dataclass
class PersonNode:
    person_key: str
    name: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    observations: list[ContactObservation] = field(default_factory=list)
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    observation_count: int = 0
    source_count: int = 0
    newest_source_date: str | None = None
    role_freshness: float = 0.0
    confidence: float = 0.0
    epistemic_best: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_key": self.person_key,
            "name": self.name,
            "emails": self.emails,
            "phones": self.phones,
            "roles": self.roles,
            "observations": [o.to_dict() for o in self.observations],
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "observation_count": self.observation_count,
            "source_count": self.source_count,
            "newest_source_date": self.newest_source_date,
            "role_freshness": self.role_freshness,
            "confidence": self.confidence,
            "epistemic_best": self.epistemic_best,
        }


@dataclass
class AccountContactGraph:
    """confenge.account_contact_graph.v1"""

    schema_id: str = "confenge.account_contact_graph.v1"
    schema_version: str = "1.0.0"
    account_cnpj: str = ""
    people: list[PersonNode] = field(default_factory=list)
    functional_mailboxes: list[ContactObservation] = field(default_factory=list)
    rejected: list[ContactObservation] = field(default_factory=list)
    built_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "account_cnpj": self.account_cnpj,
            "people": [p.to_dict() for p in self.people],
            "functional_mailboxes": [m.to_dict() for m in self.functional_mailboxes],
            "rejected": [r.to_dict() for r in self.rejected],
            "built_at": self.built_at,
            "people_count": len(self.people),
            "usable_email_count": sum(1 for p in self.people for e in p.emails if e),
        }


@dataclass
class AccountEnrichmentResult:
    account_cnpj: str
    razao_social: str | None = None
    investigation_state: InvestigationState = InvestigationState.NOT_STARTED
    terminal_state: TerminalState = TerminalState.PROCESS_NOT_TRACED
    process_graph: PublicProcessGraph | None = None
    contact_graph: AccountContactGraph | None = None
    best_contacts_by_service: dict[str, dict[str, Any]] = field(default_factory=dict)
    referral_routes: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    funnel_flags: dict[str, bool] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    research_gaps: list[str] = field(default_factory=list)
    dossier: dict[str, Any] = field(default_factory=dict)
    outreach_contacts: list[dict[str, Any]] = field(default_factory=list)
    completed_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "confenge.process_first_enrichment_result.v1",
            "schema_version": "1.0.0",
            "account_cnpj": self.account_cnpj,
            "razao_social": self.razao_social,
            "investigation_state": self.investigation_state.value,
            "terminal_state": self.terminal_state.value,
            "process_graph": self.process_graph.to_dict() if self.process_graph else None,
            "contact_graph": self.contact_graph.to_dict() if self.contact_graph else None,
            "best_contacts_by_service": self.best_contacts_by_service,
            "referral_routes": self.referral_routes,
            "blockers": self.blockers,
            "funnel_flags": self.funnel_flags,
            "limitations": self.limitations,
            "research_gaps": self.research_gaps,
            "dossier": self.dossier,
            "outreach_contacts": self.outreach_contacts,
            "completed_at": self.completed_at,
        }


# Re-export for convenience
__all__ = [
    "AccountContactGraph",
    "AccountEnrichmentResult",
    "BLOCKED_EPISTEMIC",
    "COMMERCIAL_EPISTEMIC",
    "ContactObservation",
    "ContractNode",
    "EpistemicClass",
    "InvestigationState",
    "PersonNode",
    "ProcessDocumentRef",
    "ProvenanceEdge",
    "PublicProcessGraph",
    "TerminalState",
    "content_hash",
]
