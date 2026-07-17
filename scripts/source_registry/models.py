"""Dataclass models for the entity source registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    "none",
)

# Statuses considered operationally covered (gap report excludes these).
OPERATIONAL_STATUSES: frozenset[str] = frozenset({"accessible", "collected"})


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
        """True when the entity is operationally covered."""
        return self.access_status in OPERATIONAL_STATUSES


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
