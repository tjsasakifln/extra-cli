"""Dataclass models for the entity source registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

INTEGRATION_TYPES: tuple[str, ...] = (
    "api_json",
    "html",
    "pdf",
    "js",
    "ckan",
    "rss",
    "shared_portal",
    "unknown",
)

ACCESS_STATUSES: tuple[str, ...] = (
    "mapped",
    "accessible",
    "collected",
    "verified",
    "operational",
    "failed",
    "blocked",
    "unknown",
    "source_not_identified",
)

BLOCKER_CATEGORIES: tuple[str, ...] = (
    "rate_limited",
    "no_api",
    "legacy_portal",
    "pdf",
    "javascript",
    "captcha",
    "fragmented",
    "credential",
    "not_applicable",
    "pending_collection",
    "pending_live_verification",
    "awaiting_reconciliation",
    "dry_run_index_only",
    "none",
)

# Operationally covered ONLY after collect+normalize+reconcile+verify evidence.
# `accessible` alone (e.g. offline index hit / HEAD 200) is NOT operational coverage.
OPERATIONAL_STATUSES: frozenset[str] = frozenset({"verified", "operational"})
REQUIRED_OPERATIONAL_STAGES: frozenset[str] = frozenset(
    {"mapped", "accessible", "collected", "normalized", "reconciled", "verified_within_sla"}
)


# ---------------------------------------------------------------------------
# EntitySourceRecord
# ---------------------------------------------------------------------------


@dataclass
class EntitySourceRecord:
    """Canonical per-entity source mapping for the 200 km target universe.

    Every entity in ``config/target_entities_200km.csv`` MUST produce one
    record, even when no source has been identified yet.
    """

    canonical_id: str
    razao_social: str
    cnpj: str  # 14 digits preferred; partial (8) accepted as available
    natureza_juridica: str  # entity_type from seed CSV
    municipio: str
    uf: str = "SC"
    nome_fantasia: str | None = None
    ibge_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    distance_km: float | None = None
    portal_institucional: str | None = None
    portal_transparencia: str | None = None
    portal_licitacoes: str | None = None
    diario_oficial: str | None = None
    plataformas: list[str] = field(default_factory=list)
    external_ids: dict[str, Any] = field(default_factory=dict)
    url_patterns: dict[str, str] = field(default_factory=dict)
    integration_type: str = "unknown"
    access_status: str = "unknown"
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    sla_hours: int | None = None
    collection_strategy: str = "pending_review"
    current_blocker: str | None = None
    next_action: str = "review_source_applicability"
    priority: int = 5  # 1 = highest
    mapping_confidence: float = 0.0
    evidences: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (JSONL-safe)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntitySourceRecord:
        """Rehydrate from a dict (e.g. JSONL line)."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @property
    def is_operational(self) -> bool:
        """Compatibility property; strict reports use ``is_strict_operational``."""
        return is_strict_operational(self)


def is_strict_operational(record: EntitySourceRecord, *, as_of: datetime | None = None) -> bool:
    """Verify status, seven stages, provenance and per-record SLA."""
    if record.access_status not in OPERATIONAL_STATUSES or not record.last_success_at:
        return False
    try:
        last_success = datetime.fromisoformat(record.last_success_at.replace("Z", "+00:00"))
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return False
    now = as_of or datetime.now(UTC)
    if last_success < now - timedelta(hours=int(record.sla_hours or 24)):
        return False
    for evidence in record.evidences or []:
        if not isinstance(evidence, dict) or evidence.get("dry_run") is not False:
            continue
        stages = evidence.get("stages") or {}
        if not all(stages.get(stage) is True for stage in REQUIRED_OPERATIONAL_STAGES):
            continue
        if not all(
            evidence.get(key)
            for key in ("raw_uri", "raw_sha256", "normalized_record_ids", "reconciliation_id")
        ):
            continue
        if not (evidence.get("pipeline_run_id") or evidence.get("run_id")):
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# DiscoveryResult
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryResult:
    """Outcome of semi-automatic source discovery for one entity."""

    canonical_id: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    probed: list[dict[str, Any]] = field(default_factory=list)
    best_candidate: dict[str, Any] | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
