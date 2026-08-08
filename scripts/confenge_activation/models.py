"""Activation projection models (recomputable, not CRM state)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


def _iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return dt.isoformat()


def stable_hash(payload: Any) -> str:
    """Deterministic SHA-256 of JSON-canonical payload."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FiredTrigger:
    code: str
    strength: float
    event_date: str | None
    language: str
    promotes_to: str
    expires_at: str | None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class ScoreComponents:
    trigger_strength: float = 0.0
    freshness: float = 0.0
    evidence_quality: float = 0.0
    commercial_relevance: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "trigger_strength": round(self.trigger_strength, 4),
            "freshness": round(self.freshness, 4),
            "evidence_quality": round(self.evidence_quality, 4),
            "commercial_relevance": round(self.commercial_relevance, 4),
        }

    def total(self) -> float:
        return (
            self.trigger_strength
            + self.freshness
            + self.evidence_quality
            + self.commercial_relevance
        )


@dataclass
class ActivationProjection:
    """Persistent recomputable projection for one CNPJ."""

    cnpj14: str
    activation_state: str
    activation_score: float
    reason_codes: list[str]
    evaluated_at: str
    next_best_action_at: str | None
    expires_at: str | None
    source_hash: str
    trigger_hash: str
    policy_version: str
    score_components: dict[str, float] = field(default_factory=dict)
    fired_triggers: list[dict[str, Any]] = field(default_factory=list)
    last_hot_set_at: str | None = None
    commercial_state: str = "NEW"
    notes: list[str] = field(default_factory=list)
    # Durable funnel / cursor fields (expensive path progress)
    downstream_status: str = "PENDING"
    last_downstream_at: str | None = None
    next_eligible_at: str | None = None
    processing_attempts: int = 0
    last_error: str | None = None
    last_outcome: str | None = None
    priority_band: str = "BAIXA_PRIORIDADE"
    priority_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "cnpj14": self.cnpj14,
            "activation_state": self.activation_state,
            "activation_score": round(float(self.activation_score), 4),
            "reason_codes": list(self.reason_codes),
            "evaluated_at": self.evaluated_at,
            "next_best_action_at": self.next_best_action_at,
            "expires_at": self.expires_at,
            "source_hash": self.source_hash,
            "trigger_hash": self.trigger_hash,
            "policy_version": self.policy_version,
            "score_components": dict(self.score_components),
            "fired_triggers": list(self.fired_triggers),
            "last_hot_set_at": self.last_hot_set_at,
            "commercial_state": self.commercial_state,
            "notes": list(self.notes),
            "downstream_status": self.downstream_status,
            "last_downstream_at": self.last_downstream_at,
            "next_eligible_at": self.next_eligible_at,
            "processing_attempts": int(self.processing_attempts),
            "last_error": self.last_error,
            "last_outcome": self.last_outcome,
            "priority_band": self.priority_band,
            "priority_score": round(float(self.priority_score), 4),
        }

    def activation_block(self) -> dict[str, Any]:
        """Additive confenge.outreach.v1 lead.activation block."""
        return {
            "state": self.activation_state,
            "score": round(float(self.activation_score), 4),
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
            "next_best_action_at": self.next_best_action_at,
            "expires_at": self.expires_at,
            "source_hash": self.source_hash,
            "score_components": dict(self.score_components),
        }

    def validate(self) -> None:
        if self.activation_state not in {
            "WATCH",
            "RESEARCH_REQUIRED",
            "ACTIONABLE_NOW",
            "SUPPRESSED",
        }:
            raise ValueError(f"invalid activation_state: {self.activation_state}")
        if not (0.0 <= float(self.activation_score) <= 100.0):
            raise ValueError(f"activation_score out of range: {self.activation_score}")
        if self.activation_state == "ACTIONABLE_NOW":
            if not self.reason_codes:
                raise ValueError("ACTIONABLE_NOW requires reason_codes")
            if not self.next_best_action_at:
                raise ValueError("ACTIONABLE_NOW requires next_best_action_at")


@dataclass
class ActivationCycleResult:
    policy_version: str
    evaluated_at: str
    as_of: str
    reservoir_count: int
    activation_counts: dict[str, int]
    hot_set_count: int
    projections: list[ActivationProjection]
    hot_set: list[ActivationProjection]
    deactivations: list[dict[str, Any]]
    promotions: list[dict[str, Any]]
    source_watermark: str
    trigger_counts: dict[str, int]
    rows_changed: int
    elapsed_seconds: float = 0.0
    peak_rss_mb: float | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at,
            "as_of": self.as_of,
            "reservoir_count": self.reservoir_count,
            "activation_counts": dict(self.activation_counts),
            "hot_set_count": self.hot_set_count,
            "deactivation_count": len(self.deactivations),
            "promotion_count": len(self.promotions),
            "source_watermark": self.source_watermark,
            "trigger_counts": dict(self.trigger_counts),
            "rows_changed": self.rows_changed,
            "elapsed_seconds": self.elapsed_seconds,
            "peak_rss_mb": self.peak_rss_mb,
            "full_scale_universe": self.reservoir_count > 1000,
        }
