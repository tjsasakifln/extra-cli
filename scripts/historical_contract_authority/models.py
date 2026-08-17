"""Immutable records for a historical contract authority dossier."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from scripts.historical_contract_authority.schema import (
    ClaimClass,
    ComparabilityState,
    DossierState,
    content_hash,
)


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(child) for key, child in value.items()}
    return value


@dataclass(frozen=True)
class Locator:
    page: str | None = None
    section: str | None = None
    table: str | None = None
    span: str | None = None

    def as_text(self) -> str:
        parts = [self.page, self.section, self.table, self.span]
        return "|".join(part for part in parts if part) or "UNSPECIFIED"

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value}


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    klass: str
    family: str
    url: str
    locator: Locator
    published_at: str | None
    effective_at: str | None
    binary_sha256: str
    text_sha256: str
    mime: str
    bytes_len: int
    extract_status: str
    relation: str
    ocr_used: bool = False
    ocr_tool: str | None = None
    ocr_confidence: float | None = None
    ocr_pages: tuple[str, ...] = ()
    superseded_by: str | None = None
    http_status: int | None = None
    redirect_chain: tuple[str, ...] = ()
    text: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["class"] = payload.pop("klass")
        payload["locator"] = self.locator.as_dict()
        payload.pop("text", None)
        return jsonable(payload)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    klass: ClaimClass
    text: str
    source_refs: tuple[str, ...]
    locators: tuple[str, ...]
    confidence: float
    publication_fit: str
    conflict: str | None = None
    superseded_by: str | None = None
    formula: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)
    unit: str | None = None
    result: str | None = None
    rounding: str | None = None
    replay_hash: str | None = None
    limitations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["class"] = payload.pop("klass")
        return jsonable(payload)


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    kind: str
    at: str | None
    summary: str
    source_refs: tuple[str, ...]
    locators: tuple[str, ...]
    delta_value: str | None = None
    delta_days: int | None = None
    superseded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Calculation:
    calc_id: str
    formula: str
    inputs: dict[str, str]
    unit: str
    result: str
    rounding: str
    replay_hash: str
    limitations: tuple[str, ...]
    computable: bool

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    description: str
    sources: tuple[str, ...]
    alternatives: tuple[str, ...]
    weakens: tuple[str, ...]
    pending: tuple[str, ...]
    decision: str

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class EditorialBrief:
    central_question: str
    theses: tuple[str, ...]
    why_singular: str
    transferable_utility: str
    possible_implications: tuple[str, ...]
    reputational_risks: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    cannot_assert: tuple[str, ...]
    plausible_intent: str
    article_text: None = None

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Maintenance:
    owner: str
    refresh_triggers: tuple[str, ...]
    invalidation_keys: tuple[str, ...]
    expires_at: str
    withdrawal_rule: str
    estimated_cost: str

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class ScoreBreakdown:
    dimensions: dict[str, int]
    weights: dict[str, int]
    weighted_total_x100: int
    score: float
    hard_gates: dict[str, bool]
    below_floor: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Comparability:
    status: ComparabilityState
    reason_codes: tuple[str, ...]
    engine: str
    schema: str
    usable_n: int
    outlier_flag: bool
    limitations: tuple[str, ...]
    content_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Dossier:
    schema: str
    dossier_id: str
    state: DossierState
    reason_codes: tuple[str, ...]
    identity: dict[str, Any]
    documents: tuple[DocumentRecord, ...]
    claims: tuple[Claim, ...]
    chronology: tuple[TimelineEvent, ...]
    calculations: tuple[Calculation, ...]
    comparability: Comparability
    contradictions: tuple[Contradiction, ...]
    editorial: EditorialBrief
    maintenance: Maintenance
    score: ScoreBreakdown
    as_of: str
    freshness: dict[str, Any]
    source_snapshot_hash: str
    producer_sha: str
    catalog_mode: str
    limitations: tuple[str, ...]
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "dossier_id": self.dossier_id,
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "identity": self.identity,
            "documents": [item.as_dict() for item in self.documents],
            "claims": [item.as_dict() for item in self.claims],
            "chronology": [item.as_dict() for item in self.chronology],
            "calculations": [item.as_dict() for item in self.calculations],
            "comparability": self.comparability.as_dict(),
            "contradictions": [item.as_dict() for item in self.contradictions],
            "editorial": self.editorial.as_dict(),
            "maintenance": self.maintenance.as_dict(),
            "score": self.score.as_dict(),
            "as_of": self.as_of,
            "freshness": self.freshness,
            "source_snapshot_hash": self.source_snapshot_hash,
            "producer_sha": self.producer_sha,
            "catalog_mode": self.catalog_mode,
            "limitations": list(self.limitations),
        }
        payload["content_hash"] = content_hash(payload)
        return jsonable(payload)


def dossier_payload_hash(dossier: Dossier) -> str:
    return dossier.as_dict()["content_hash"]
