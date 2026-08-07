"""Priority score for ORDERING only — never for universe membership.

Invariants:
- Large national firms remain in the universe regardless of score.
- Small firms are not promoted solely by a single large contract value.
- Annual volume / isolated value alone is not sold as "pain".
- Score is an INFERENCE with provenance, not a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from scripts.confenge_universe.construction import ConstructionEvidence


@dataclass(frozen=True)
class PriorityScore:
    score: float
    reason: str
    components: dict[str, float]
    epistemic_class: str = "INFERENCE"
    provenance: str = "confenge-universe-priority-v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "priority_score": round(self.score, 4),
            "priority_reason": self.reason,
            "priority_components": {k: round(v, 4) for k, v in self.components.items()},
            "epistemic_class": self.epistemic_class,
            "provenance": self.provenance,
        }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_priority_score(
    *,
    construction: ConstructionEvidence,
    contract_count: int,
    contract_count_recent: int,
    value_total: float,
    value_recent: float,
    n_ufs: int,
    n_orgaos: int,
    last_contract_date: date | None,
    as_of: date,
    active_count: int,
) -> PriorityScore:
    """Order-only score. Contract value is log-damped so one mega-contract
    cannot dominate a small firm over a diversified construction portfolio.
    """
    components: dict[str, float] = {}

    # Evidence strength (not size)
    fit = construction.sector_fit
    if fit == "CONFIRMED_ENGINEERING":
        components["sector_fit"] = 30.0
    elif fit == "STRONG_ENGINEERING_FIT":
        components["sector_fit"] = 24.0
    elif fit == "POSSIBLE_ENGINEERING_FIT":
        components["sector_fit"] = 12.0
    else:
        components["sector_fit"] = 4.0

    # Portfolio breadth — multi-agency / multi-UF beat raw value
    components["relevant_contracts"] = _clamp(
        float(construction.relevant_contract_count) * 2.0, 0.0, 20.0
    )
    components["agency_diversity"] = _clamp(float(n_orgaos) * 1.5, 0.0, 15.0)
    components["uf_diversity"] = _clamp(float(n_ufs) * 2.0, 0.0, 12.0)

    # Recency of activity (temporal approach signal) — not "pain"
    if last_contract_date:
        days = (as_of - last_contract_date).days
        if days <= 180:
            components["recency"] = 10.0
        elif days <= 365:
            components["recency"] = 7.0
        elif days <= 730:
            components["recency"] = 4.0
        else:
            components["recency"] = 1.0
    else:
        components["recency"] = 0.0

    components["recent_volume_count"] = _clamp(float(contract_count_recent) * 1.2, 0.0, 10.0)
    components["active_contracts"] = _clamp(float(active_count) * 1.0, 0.0, 8.0)

    # Log-damped value: diminishing returns, cap so mega-contract ≠ auto top
    import math

    # Use recent value primarily; total as weak secondary
    v = max(value_recent, 0.0)
    if v > 0:
        # log10(1 + v/1e5) capped — R$ 100k → ~1, R$ 10M → ~3, R$ 1B → ~5
        components["value_log_damped"] = _clamp(math.log10(1.0 + v / 100_000.0) * 3.0, 0.0, 12.0)
    else:
        vt = max(value_total, 0.0)
        components["value_log_damped"] = _clamp(
            math.log10(1.0 + vt / 100_000.0) * 1.5, 0.0, 6.0
        )

    # Concentration penalty: single-contract portfolios get a soft ceiling
    if construction.relevant_contract_count <= 1 and contract_count <= 1:
        components["single_contract_cap"] = -8.0
    else:
        components["single_contract_cap"] = 0.0

    # Confidence from classifier
    components["classifier_confidence"] = _clamp(construction.confidence * 8.0, 0.0, 8.0)

    total = sum(components.values())
    total = _clamp(total, 0.0, 100.0)

    # Human-readable reason (ordering context only)
    parts: list[str] = []
    if fit in {"CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT"}:
        parts.append(f"fit={fit}")
    parts.append(f"relevant={construction.relevant_contract_count}")
    parts.append(f"orgaos={n_orgaos}")
    parts.append(f"ufs={n_ufs}")
    if last_contract_date:
        parts.append(f"last={last_contract_date.isoformat()}")
    if components.get("single_contract_cap", 0) < 0:
        parts.append("single_contract_not_promoted")
    reason = "order:" + ",".join(parts)

    return PriorityScore(score=total, reason=reason, components=components)
