"""Load and validate versioned activation policy YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.confenge_activation import DEFAULT_POLICY_VERSION, POLICY_DEFAULT_NAME

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = _PROJECT_ROOT / "config" / "commercial" / POLICY_DEFAULT_NAME


@dataclass(frozen=True)
class ScoreWeights:
    trigger_strength: float
    freshness: float
    evidence_quality: float
    commercial_relevance: float

    def total(self) -> float:
        return (
            self.trigger_strength
            + self.freshness
            + self.evidence_quality
            + self.commercial_relevance
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "trigger_strength": self.trigger_strength,
            "freshness": self.freshness,
            "evidence_quality": self.evidence_quality,
            "commercial_relevance": self.commercial_relevance,
        }


@dataclass(frozen=True)
class CapacityConfig:
    sends_per_hour: int
    send_window_hours: int
    planning_horizon_days: int
    research_buffer: float
    max_hot_set: int
    min_hot_set: int

    def planned_capacity(self) -> int:
        """Theoretical hot-set budget from rate × window × horizon × buffer."""
        raw = (
            float(self.sends_per_hour)
            * float(self.send_window_hours)
            * float(self.planning_horizon_days)
            * float(self.research_buffer)
        )
        n = int(round(raw))
        n = max(self.min_hot_set, n)
        return min(self.max_hot_set, n)


@dataclass(frozen=True)
class TriggerDef:
    code: str
    enabled: bool
    strength: float
    language: str
    expires_days: int | None
    promotes_to: str
    next_best_action: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivationPolicy:
    policy_version: str
    capacity: CapacityConfig
    score_weights: ScoreWeights
    triggers: dict[str, TriggerDef]
    suppressed_states: frozenset[str]
    active_commercial_block: frozenset[str]
    reevaluation: dict[str, Any]
    materiality: dict[str, Any]
    freshness_bands: list[dict[str, Any]]
    evidence_quality: dict[str, Any]
    hot_set_min_score: float
    production: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)

    def trigger(self, code: str) -> TriggerDef | None:
        return self.triggers.get(code)


def _require_mapping(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a mapping")
    return data


def load_policy(path: Path | str | None = None) -> ActivationPolicy:
    """Load policy from YAML. Fail-closed on missing/invalid config."""
    p = Path(path) if path else DEFAULT_POLICY_PATH
    if not p.is_file():
        raise FileNotFoundError(f"activation policy not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data = _require_mapping(data, "policy root")

    version = str(data.get("policy_version") or DEFAULT_POLICY_VERSION).strip()
    cap_raw = _require_mapping(data.get("capacity") or {}, "capacity")
    capacity = CapacityConfig(
        sends_per_hour=int(cap_raw.get("sends_per_hour", 10)),
        send_window_hours=int(cap_raw.get("send_window_hours", 9)),
        planning_horizon_days=int(cap_raw.get("planning_horizon_days", 7)),
        research_buffer=float(cap_raw.get("research_buffer", 1.5)),
        max_hot_set=int(cap_raw.get("max_hot_set", 500)),
        min_hot_set=int(cap_raw.get("min_hot_set", 20)),
    )
    if capacity.sends_per_hour < 1:
        raise ValueError("capacity.sends_per_hour must be >= 1")
    if capacity.max_hot_set < capacity.min_hot_set:
        raise ValueError("capacity.max_hot_set must be >= min_hot_set")

    w_raw = _require_mapping(data.get("score_weights") or {}, "score_weights")
    weights = ScoreWeights(
        trigger_strength=float(w_raw.get("trigger_strength", 40)),
        freshness=float(w_raw.get("freshness", 25)),
        evidence_quality=float(w_raw.get("evidence_quality", 20)),
        commercial_relevance=float(w_raw.get("commercial_relevance", 15)),
    )
    total = weights.total()
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"score_weights must sum to 100, got {total}")

    triggers: dict[str, TriggerDef] = {}
    t_raw = _require_mapping(data.get("triggers") or {}, "triggers")
    for code, cfg in t_raw.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"trigger {code} must be a mapping")
        promotes = str(cfg.get("promotes_to") or "WATCH").upper()
        if promotes not in {
            "WATCH",
            "RESEARCH_REQUIRED",
            "ACTIONABLE_NOW",
            "SUPPRESSED",
        }:
            raise ValueError(f"trigger {code}: invalid promotes_to {promotes}")
        strength = float(cfg.get("strength", 0))
        if strength < 0 or strength > 100:
            raise ValueError(f"trigger {code}: strength must be 0–100")
        exp = cfg.get("expires_days")
        triggers[str(code).upper()] = TriggerDef(
            code=str(code).upper(),
            enabled=bool(cfg.get("enabled", True)),
            strength=strength,
            language=str(cfg.get("language") or "").strip(),
            expires_days=int(exp) if exp is not None else None,
            promotes_to=promotes,
            next_best_action=str(cfg.get("next_best_action") or "now"),
            raw=dict(cfg),
        )

    suppressed = frozenset(
        str(x).upper() for x in (data.get("suppressed_states") or [])
    )
    active_block = frozenset(
        str(x).upper() for x in (data.get("active_commercial_block") or [])
    )

    bands = data.get("freshness_bands") or []
    if not isinstance(bands, list) or not bands:
        raise ValueError("freshness_bands must be a non-empty list")

    return ActivationPolicy(
        policy_version=version,
        capacity=capacity,
        score_weights=weights,
        triggers=triggers,
        suppressed_states=suppressed,
        active_commercial_block=active_block,
        reevaluation=dict(data.get("reevaluation") or {}),
        materiality=dict(data.get("materiality") or {}),
        freshness_bands=list(bands),
        evidence_quality=dict(data.get("evidence_quality") or {}),
        hot_set_min_score=float(data.get("hot_set_min_score", 25)),
        production=dict(data.get("production") or {}),
        raw=data,
    )
