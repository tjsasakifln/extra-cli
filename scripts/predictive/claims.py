"""Canonical predictive claim registry with gated state transitions.

Only PRODUCTION_AVAILABLE authorizes external "available" language for a claim.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.predictive import CLAIM_IDS, CLAIM_STATES

# Market claims required for FULLY_PROVEN
_MARKET_TRIO = (
    "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
    "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
    "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
)

# Allowed transitions (from -> set of to). Fail-closed otherwise.
_ALLOWED: dict[str, frozenset[str]] = {
    "NOT_IMPLEMENTED": frozenset(
        {"IMPLEMENTED", "DATA_BLOCKED", "NOT_IMPLEMENTED"}
    ),
    "IMPLEMENTED": frozenset(
        {
            "DATA_BLOCKED",
            "BACKTEST_FAILED",
            "HISTORICAL_BACKTEST_PROVEN",
            "IMPLEMENTED",
        }
    ),
    "DATA_BLOCKED": frozenset(
        {"IMPLEMENTED", "DATA_BLOCKED", "HISTORICAL_BACKTEST_PROVEN"}
    ),
    "BACKTEST_FAILED": frozenset(
        {"IMPLEMENTED", "DATA_BLOCKED", "BACKTEST_FAILED", "HISTORICAL_BACKTEST_PROVEN"}
    ),
    "HISTORICAL_BACKTEST_PROVEN": frozenset(
        {
            "SHADOW_OPERATIONAL",
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "HISTORICAL_BACKTEST_PROVEN",
            "BACKTEST_FAILED",
        }
    ),
    "SHADOW_OPERATIONAL": frozenset(
        {
            "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
            "PROSPECTIVE_CALIBRATED",
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "SHADOW_OPERATIONAL",
        }
    ),
    "PROSPECTIVE_EVIDENCE_INSUFFICIENT": frozenset(
        {
            "SHADOW_OPERATIONAL",
            "PROSPECTIVE_CALIBRATED",
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
        }
    ),
    "PROSPECTIVE_CALIBRATED": frozenset(
        {
            "PRODUCTION_AVAILABLE",
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "PROSPECTIVE_CALIBRATED",
            "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
        }
    ),
    "PRODUCTION_AVAILABLE": frozenset(
        {
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "PRODUCTION_AVAILABLE",
            "PROSPECTIVE_CALIBRATED",
        }
    ),
    "SUSPENDED_DRIFT": frozenset(
        {
            "SHADOW_OPERATIONAL",
            "PROSPECTIVE_CALIBRATED",
            "PRODUCTION_AVAILABLE",
            "SUSPENDED_DATA_QUALITY",
            "SUSPENDED_DRIFT",
            "BACKTEST_FAILED",
        }
    ),
    "SUSPENDED_DATA_QUALITY": frozenset(
        {
            "SHADOW_OPERATIONAL",
            "DATA_BLOCKED",
            "SUSPENDED_DRIFT",
            "SUSPENDED_DATA_QUALITY",
            "IMPLEMENTED",
        }
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "artifacts" / "predictive" / "claim_states.json"


@dataclass
class ClaimRecord:
    claim_id: str
    state: str
    updated_at: str
    evidence: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    model_id: str | None = None
    model_version: str | None = None

    def allows_external_availability(self) -> bool:
        return self.state == "PRODUCTION_AVAILABLE"

    def allows_probability_language(self) -> bool:
        return self.state in {
            "PRODUCTION_AVAILABLE",
            "PROSPECTIVE_CALIBRATED",
            "HISTORICAL_BACKTEST_PROVEN",
            "SHADOW_OPERATIONAL",
        } and self.claim_id not in {
            # Even with market models, Extra-specific claims need their own gate
        }


def _seed_records() -> dict[str, ClaimRecord]:
    now = _utc_now()
    seeds: dict[str, ClaimRecord] = {}
    for cid in CLAIM_IDS:
        seeds[cid] = ClaimRecord(
            claim_id=cid,
            state="NOT_IMPLEMENTED",
            updated_at=now,
            blockers=["Awaiting implementation and evidence"],
        )
    return seeds


class ClaimRegistry:
    """In-memory + JSON-backed claim registry (PG optional via persist layer)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()
        self._claims: dict[str, ClaimRecord] = _seed_records()
        if self.path.exists():
            self.load()

    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        claims = data.get("claims") or data
        for cid, raw in claims.items():
            if cid not in CLAIM_IDS:
                continue
            state = raw.get("state", "NOT_IMPLEMENTED")
            if state not in CLAIM_STATES:
                state = "NOT_IMPLEMENTED"
            self._claims[cid] = ClaimRecord(
                claim_id=cid,
                state=state,
                updated_at=raw.get("updated_at") or _utc_now(),
                evidence=dict(raw.get("evidence") or {}),
                blockers=list(raw.get("blockers") or []),
                limitations=list(raw.get("limitations") or []),
                model_id=raw.get("model_id"),
                model_version=raw.get("model_version"),
            )
        self._refresh_derived()

    def save(self) -> Path:
        self._refresh_derived()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "updated_at": _utc_now(),
            "claims": {cid: asdict(rec) for cid, rec in self._claims.items()},
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return self.path

    def get(self, claim_id: str) -> ClaimRecord:
        if claim_id not in self._claims:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        return self._claims[claim_id]

    def all(self) -> dict[str, ClaimRecord]:
        return dict(self._claims)

    def set_state(
        self,
        claim_id: str,
        state: str,
        *,
        evidence: dict[str, Any] | None = None,
        blockers: list[str] | None = None,
        limitations: list[str] | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        force: bool = False,
    ) -> ClaimRecord:
        if claim_id not in CLAIM_IDS:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        if state not in CLAIM_STATES:
            raise ValueError(f"Invalid state: {state}")
        cur = self._claims[claim_id]
        allowed = _ALLOWED.get(cur.state, frozenset())
        if not force and state not in allowed:
            raise ValueError(
                f"Illegal transition {cur.state} -> {state} for {claim_id}"
            )
        # Gate: PRODUCTION_AVAILABLE requires evidence keys
        if state == "PRODUCTION_AVAILABLE":
            ev = {**(cur.evidence), **(evidence or {})}
            if not ev.get("prospective_calibrated") and not force:
                raise ValueError(
                    f"{claim_id}: PRODUCTION_AVAILABLE requires prospective_calibrated evidence"
                )
        rec = ClaimRecord(
            claim_id=claim_id,
            state=state,
            updated_at=_utc_now(),
            evidence={**(cur.evidence), **(evidence or {})},
            blockers=list(blockers if blockers is not None else cur.blockers),
            limitations=list(
                limitations if limitations is not None else cur.limitations
            ),
            model_id=model_id if model_id is not None else cur.model_id,
            model_version=model_version
            if model_version is not None
            else cur.model_version,
        )
        self._claims[claim_id] = rec
        self._refresh_derived()
        return self._claims[claim_id]

    def _refresh_derived(self) -> None:
        """Update MARKET and FULLY_PROVEN derived claims."""
        now = _utc_now()
        demand = self._claims["PREDICTIVE_DEMAND_FORECAST_AVAILABLE"].state
        comp = self._claims["PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE"].state
        disc = self._claims["PREDICTIVE_WINNING_DISCOUNT_AVAILABLE"].state

        # Market intelligence = all three market claims at least HISTORICAL_BACKTEST_PROVEN
        market_states = {demand, comp, disc}
        if market_states == {"PRODUCTION_AVAILABLE"}:
            mstate = "PRODUCTION_AVAILABLE"
            mblock: list[str] = []
        elif all(
            s
            in {
                "PRODUCTION_AVAILABLE",
                "PROSPECTIVE_CALIBRATED",
                "SHADOW_OPERATIONAL",
                "HISTORICAL_BACKTEST_PROVEN",
            }
            for s in market_states
        ):
            # weakest of the three
            order = [
                "HISTORICAL_BACKTEST_PROVEN",
                "SHADOW_OPERATIONAL",
                "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
                "PROSPECTIVE_CALIBRATED",
                "PRODUCTION_AVAILABLE",
            ]
            rank = {s: i for i, s in enumerate(order)}
            mstate = min(market_states, key=lambda s: rank.get(s, -1))
            mblock = []
        elif "DATA_BLOCKED" in market_states:
            mstate = "DATA_BLOCKED"
            mblock = ["One or more market claims DATA_BLOCKED"]
        elif "BACKTEST_FAILED" in market_states:
            mstate = "BACKTEST_FAILED"
            mblock = ["One or more market claims BACKTEST_FAILED"]
        elif "IMPLEMENTED" in market_states or "NOT_IMPLEMENTED" in market_states:
            if all(s == "NOT_IMPLEMENTED" for s in market_states):
                mstate = "NOT_IMPLEMENTED"
            else:
                mstate = "IMPLEMENTED"
            mblock = ["Market trio not yet backtest-proven"]
        else:
            mstate = "IMPLEMENTED"
            mblock = []

        prev_m = self._claims["PREDICTIVE_MARKET_INTELLIGENCE_AVAILABLE"]
        self._claims["PREDICTIVE_MARKET_INTELLIGENCE_AVAILABLE"] = ClaimRecord(
            claim_id="PREDICTIVE_MARKET_INTELLIGENCE_AVAILABLE",
            state=mstate,
            updated_at=now,
            evidence={
                "demand": demand,
                "competitive": comp,
                "discount": disc,
            },
            blockers=mblock,
            limitations=list(prev_m.limitations),
        )

        # FULLY_PROVEN requires all three PRODUCTION_AVAILABLE
        if all(
            self._claims[c].state == "PRODUCTION_AVAILABLE" for c in _MARKET_TRIO
        ):
            fstate = "PRODUCTION_AVAILABLE"
            fblock: list[str] = []
        else:
            fstate = "NOT_IMPLEMENTED"
            fblock = [
                f"{c}={self._claims[c].state}"
                for c in _MARKET_TRIO
                if self._claims[c].state != "PRODUCTION_AVAILABLE"
            ]
            # Reflect highest achieved intermediate if any market is further along
            if any(
                self._claims[c].state
                in {
                    "HISTORICAL_BACKTEST_PROVEN",
                    "SHADOW_OPERATIONAL",
                    "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
                    "PROSPECTIVE_CALIBRATED",
                }
                for c in _MARKET_TRIO
            ):
                fstate = "PROSPECTIVE_EVIDENCE_INSUFFICIENT"

        self._claims["PREDICTIVE_INTELLIGENCE_FULLY_PROVEN"] = ClaimRecord(
            claim_id="PREDICTIVE_INTELLIGENCE_FULLY_PROVEN",
            state=fstate,
            updated_at=now,
            evidence={c: self._claims[c].state for c in _MARKET_TRIO},
            blockers=fblock,
            limitations=[
                "Requires demand + competitive + winning-discount all PRODUCTION_AVAILABLE",
                "Extra win-prob and optimal-bid are separate claims",
            ],
        )

    def prediction_allowed(self, claim_id: str) -> bool:
        """Whether probability/percentage language is authorized for this claim."""
        rec = self.get(claim_id)
        return rec.state == "PRODUCTION_AVAILABLE"

    def commercial_recommendation(self) -> str:
        """CLAIM_ALLOWED | PARTIAL_CLAIM_ALLOWED | CLAIM_FORBIDDEN."""
        fully = self.get("PREDICTIVE_INTELLIGENCE_FULLY_PROVEN").state
        if fully == "PRODUCTION_AVAILABLE":
            return "CLAIM_ALLOWED"
        any_prod = any(
            self.get(c).state == "PRODUCTION_AVAILABLE" for c in CLAIM_IDS
        )
        any_shadow = any(
            self.get(c).state
            in {
                "SHADOW_OPERATIONAL",
                "HISTORICAL_BACKTEST_PROVEN",
                "PROSPECTIVE_CALIBRATED",
                "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
            }
            for c in CLAIM_IDS
        )
        if any_prod or any_shadow:
            return "PARTIAL_CLAIM_ALLOWED"
        return "CLAIM_FORBIDDEN"

    def to_public_dict(self) -> dict[str, Any]:
        self._refresh_derived()
        return {
            "updated_at": _utc_now(),
            "commercial_recommendation": self.commercial_recommendation(),
            "claims": {
                cid: {
                    **asdict(rec),
                    "external_availability_allowed": rec.allows_external_availability(),
                }
                for cid, rec in self._claims.items()
            },
        }


def load_registry(path: Path | None = None) -> ClaimRegistry:
    return ClaimRegistry(path=path)


def vocabulary_label(
    *,
    claim_id: str,
    registry: ClaimRegistry,
    score: float | None = None,
    calibrated: bool = False,
) -> str:
    """Return honest vocabulary for a score/probability display."""
    if not registry.prediction_allowed(claim_id):
        if score is None:
            return "dados insuficientes"
        return "score não calibrado"
    if calibrated:
        return "probabilidade calibrada"
    return "score não calibrado"
