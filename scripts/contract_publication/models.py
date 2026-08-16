"""Immutable records for the publication-candidate engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from scripts.contract_publication.schema import CandidateState, DetectorStatus, FieldStatus, FreshnessStatus


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class DetectorResult:
    detector_id: str
    detector_version: str
    fired: bool
    status: DetectorStatus
    strength: float | None
    result: Any
    reason_code: str
    evidence_refs: tuple[str, ...]
    epistemic_class: str
    method: dict[str, str]
    limitations: tuple[str, ...]
    freshness: dict[str, Any]
    missing_fields: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    analysis_angles: tuple[str, ...] = ()
    peer_dimensions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    status: FieldStatus
    value: float | None
    weight: float
    reason_code: str | None
    evidence_refs: tuple[str, ...]
    contributing_detectors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class AggregateScore:
    formula_version: str
    value: float | None
    status: FieldStatus
    known_weight_fraction: float
    unknown_components: tuple[str, ...]
    reason_code: str | None
    weights: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


@dataclass(frozen=True)
class Candidate:
    schema: str
    contract_version: str
    score_formula_version: str
    analysis_candidate_id: str
    canonical_contract_id: str | None
    source_id: str | None
    source_record_id: str | None
    as_of: str
    observed_at: str | None
    freshness_hours: float | None
    freshness_status: FreshnessStatus
    candidate_state: CandidateState
    publication_value_score: AggregateScore
    components: tuple[ScoreComponent, ...]
    detectors: tuple[DetectorResult, ...]
    reason_codes: tuple[str, ...]
    missing: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    event_ids: tuple[str, ...]
    suggested_analysis_angles: tuple[str, ...]
    suggested_peer_dimensions: tuple[str, ...]
    sensitivity_flags: tuple[str, ...]
    material_fingerprint: str
    catalog_mode: str
    authorizes_publication: bool
    authorizes_indexation: bool

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "contract_version": self.contract_version,
            "score_formula_version": self.score_formula_version,
            "analysis_candidate_id": self.analysis_candidate_id,
            "canonical_contract_id": self.canonical_contract_id,
            "canonical_contract_ids": [self.canonical_contract_id] if self.canonical_contract_id else [],
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "as_of": self.as_of,
            "observed_at": self.observed_at,
            "freshness_hours": self.freshness_hours,
            "freshness_status": self.freshness_status,
            "candidate_state": self.candidate_state,
            "publication_value_score": self.publication_value_score.as_dict(),
            "components": {item.name: item.as_dict() for item in self.components},
            "detectors": [item.as_dict() for item in self.detectors],
            "reason_codes": list(self.reason_codes),
            "missing": list(self.missing),
            "evidence_refs": list(self.evidence_refs),
            "event_ids": list(self.event_ids),
            "suggested_analysis_angles": list(self.suggested_analysis_angles),
            "suggested_peer_dimensions": list(self.suggested_peer_dimensions),
            "sensitivity_flags": list(self.sensitivity_flags),
            "material_fingerprint": self.material_fingerprint,
            "catalog_mode": self.catalog_mode,
            "authorizes_publication": self.authorizes_publication,
            "authorizes_indexation": self.authorizes_indexation,
        }
        return jsonable(payload)
