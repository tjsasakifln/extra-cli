"""Typed models for procurement process documents capability."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.process_documents.statuses import (
    ActivityStatus,
    DocumentCategory,
    DocumentRunStatus,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class DocumentRecord:
    """Preserved public document with provenance (raw bytes live outside Git)."""

    internal_id: str
    sha256: str
    size_bytes: int
    download_url: str
    source_id: str
    canonical_entity_id: str
    portal_family: str
    document_category: str = DocumentCategory.UNKNOWN.value
    official_id: str | None = None
    original_title: str | None = None
    original_filename: str | None = None
    administrative_process_id: str | None = None
    procurement_id: str | None = None
    notice_id: str | None = None
    contract_id: str | None = None
    related_bidder: str | None = None
    source_page_url: str | None = None
    published_at: str | None = None
    fetched_at: str = field(default_factory=_now_iso)
    declared_mime: str | None = None
    detected_mime: str | None = None
    extension: str | None = None
    version: int = 1
    run_id: str | None = None
    raw_uri: str | None = None
    public_access_status: str = "public"
    sanitization_status: str = "raw"
    error: str | None = None
    blocker: str | None = None
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentRunResult:
    """Fail-closed typed result of a document adapter run."""

    run_id: str
    canonical_entity_id: str
    source_id: str
    portal_family: str
    capabilities_requested: list[str]
    capabilities_proven: list[str]
    status: DocumentRunStatus
    started_at: str
    finished_at: str
    query_parameters: dict[str, Any] = field(default_factory=dict)
    pages_attempted: int = 0
    pages_completed: int = 0
    records_seen: int = 0
    processes_seen: int = 0
    documents_discovered: int = 0
    documents_downloaded: int = 0
    documents_unchanged: int = 0
    documents_failed: int = 0
    errors: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    retry_count: int = 0
    latency_ms: float = 0.0
    raw_manifest_uri: str | None = None
    checkpoint_uri: str | None = None
    evidence_uri: str | None = None
    documents: list[DocumentRecord] = field(default_factory=list)
    success_zero_justification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, DocumentRunStatus) else str(self.status)
        d["documents"] = [doc.to_dict() if isinstance(doc, DocumentRecord) else doc for doc in self.documents]
        return d

    @property
    def is_operational_success(self) -> bool:
        return self.status in (
            DocumentRunStatus.SUCCESS_NONZERO,
            DocumentRunStatus.SUCCESS_ZERO,
        )

    def validate_fail_closed(self) -> None:
        """Raise if status claims success but evidence contradicts."""
        if self.status == DocumentRunStatus.SUCCESS_NONZERO:
            if self.documents_downloaded + self.documents_unchanged <= 0:
                raise ValueError("SUCCESS_NONZERO requires documents_downloaded or documents_unchanged > 0")
            if self.pages_attempted > 0 and self.pages_completed < self.pages_attempted:
                raise ValueError("SUCCESS_NONZERO forbids incomplete pagination")
            if self.documents_failed > 0 and self.documents_downloaded == 0:
                raise ValueError("SUCCESS_NONZERO forbids all downloads failed")
        if self.status == DocumentRunStatus.SUCCESS_ZERO:
            if not self.success_zero_justification:
                raise ValueError("SUCCESS_ZERO requires success_zero_justification")
            if self.documents_downloaded > 0:
                raise ValueError("SUCCESS_ZERO cannot have downloads")
            if self.errors:
                raise ValueError("SUCCESS_ZERO cannot carry errors")
            if self.pages_attempted > 0 and self.pages_completed < self.pages_attempted:
                raise ValueError("SUCCESS_ZERO forbids incomplete pagination")


@dataclass
class EntityDocumentDiscovery:
    """Cadastral discovery record — one per canonical entity (denominator 1093)."""

    canonical_id: str
    razao_social: str
    cnpj: str
    municipio: str
    uf: str
    applicability: str  # applicable | not_applicable (never unknown at report time)
    applicability_reason: str
    institutional_site: str | None
    transparency_portal: str | None
    procurement_portal: str | None
    dispute_platform: str | None
    admin_process_system: str | None
    pncp_source: str
    portal_family: str
    capabilities: list[str]
    access_status: str  # DiscoveryStatus value — not unknown
    last_verified_at: str
    blocker: str | None
    collection_strategy: str
    fallback_strategy: str
    activity_status: str = ActivityStatus.UNKNOWN_PENDING_EVIDENCE.value
    activity_evidence: list[str] = field(default_factory=list)
    operational_status: str = DocumentRunStatus.PENDING.value
    last_operational_run_id: str | None = None
    last_operational_at: str | None = None
    platforms: list[str] = field(default_factory=list)
    mapping_confidence: float = 0.0
    evidences: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityDocumentDiscovery:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ProcessRef:
    """Reference to an administrative procurement process."""

    process_id: str
    canonical_entity_id: str
    source_id: str
    title: str | None = None
    modality: str | None = None
    status: str | None = None
    published_at: str | None = None
    estimated_value: float | None = None
    homologated_value: float | None = None
    awarded_value: float | None = None
    contracted_value: float | None = None
    financial_value_used: float | None = None
    financial_value_field: str | None = None
    is_engineering: bool = False
    uf: str | None = None
    municipio: str | None = None
    url: str | None = None
    external_ids: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Versioned financial value hierarchy (never sum incompatible fields).
FINANCIAL_VALUE_HIERARCHY: tuple[str, ...] = (
    "contracted_value",
    "homologated_value",
    "awarded_value",
    "estimated_value",
)


def resolve_financial_value(process: ProcessRef | dict[str, Any]) -> tuple[float | None, str | None]:
    """Pick one semantic value field using the versioned hierarchy."""
    get = process.get if isinstance(process, dict) else lambda k: getattr(process, k, None)
    for field_name in FINANCIAL_VALUE_HIERARCHY:
        val = get(field_name)
        if val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        if fval > 0:
            return fval, field_name
    return None, None


PORTAL_FAMILIES: dict[str, dict[str, Any]] = {
    "pncp": {
        "primary": True,
        "needs_js": False,
        "integration": "api_json",
        "capabilities": list(
            {
                "notice_documents",
                "planning_documents",
                "contract_execution_documents",
            }
        ),
    },
    "ciga_ckan": {
        "primary": False,
        "needs_js": False,
        "integration": "ckan",
        "capabilities": ["administrative_process_documents", "notice_documents"],
    },
    "ciga_dom": {
        "primary": False,
        "needs_js": False,
        "integration": "api_json",
        "capabilities": ["notice_documents", "session_and_judgment_documents"],
    },
    "dom_sc": {
        "primary": False,
        "needs_js": False,
        "integration": "html",
        "capabilities": ["notice_documents"],
    },
    "doe_sc": {
        "primary": False,
        "needs_js": False,
        "integration": "ckan",
        "capabilities": ["notice_documents", "contract_execution_documents"],
    },
    "sc_compras": {
        "primary": False,
        "needs_js": True,
        "integration": "html",
        "capabilities": ["notice_documents", "bidder_submission_documents"],
    },
    "compras_gov": {
        "primary": False,
        "needs_js": True,
        "integration": "html",
        "capabilities": ["notice_documents", "session_and_judgment_documents"],
    },
    "pcp": {
        "primary": False,
        "needs_js": False,
        "integration": "api_json",
        "capabilities": ["notice_documents"],
    },
    "transparencia": {
        "primary": False,
        "needs_js": False,
        "integration": "html",
        "capabilities": ["contract_execution_documents"],
    },
    "tce_sc": {
        "primary": False,
        "needs_js": False,
        "integration": "html",
        "capabilities": ["contract_execution_documents"],
    },
    "portal_institucional": {
        "primary": False,
        "needs_js": False,
        "integration": "html",
        "capabilities": ["notice_documents"],
    },
    "generic_public_html": {
        "primary": False,
        "needs_js": False,
        "integration": "html",
        "capabilities": ["notice_documents"],
    },
    "manual_only": {
        "primary": False,
        "needs_js": False,
        "integration": "manual",
        "capabilities": [],
    },
}


def classify_portal_family(platforms: list[str], *, has_institutional: bool = False) -> str:
    """Pick the highest-impact portal family for document collection priority."""
    priority = (
        "pncp",
        "ciga_ckan",
        "ciga_dom",
        "sc_compras",
        "compras_gov",
        "pcp",
        "doe_sc",
        "dom_sc",
        "transparencia",
        "tce_sc",
    )
    plats = {p.lower() for p in platforms or []}
    for fam in priority:
        if fam in plats:
            return fam
    if has_institutional:
        return "portal_institucional"
    return "generic_public_html"
