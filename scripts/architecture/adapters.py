"""Adapters binding Protocols to existing production modules (no behavior rewrite)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.architecture.interfaces import (
    CoverageContract,
    DecisionRules,
    FreshnessGate,
    PackDelivery,
)
from scripts.ops.weekly_cycle import classify_opportunity_freshness


class WeeklyFreshnessAdapter:
    """Adapter over weekly_cycle.classify_opportunity_freshness."""

    def classify(
        self,
        *,
        status: str,
        age_hours: float | None,
        sla_hours: float,
        scope_complete: bool = True,
    ) -> str:
        age = 0.0 if age_hours is None else float(age_hours)
        return classify_opportunity_freshness(
            status=status,
            age_hours=age,
            sla_hours=sla_hours,
            scope_complete=scope_complete,
        )


class RatioCoverageAdapter:
    """Minimal coverage contract: ratio only, never claims 95% readiness."""

    def compute_operational_ratio(
        self,
        *,
        covered: int,
        universe: int,
        capability: str,
    ) -> dict[str, Any]:
        if universe <= 0:
            return {
                "ok": False,
                "capability": capability,
                "covered": covered,
                "universe": universe,
                "ratio": None,
                "error": "invalid_universe",
                "claim_95_forbidden": True,
            }
        ratio = covered / universe
        return {
            "ok": True,
            "capability": capability,
            "covered": covered,
            "universe": universe,
            "ratio": ratio,
            "claim_95_forbidden": True,
            "meets_95": ratio >= 0.95,  # observational only — not a seal
        }


class DirectoryPackDeliveryAdapter:
    """Inspect a weekly pack directory for expected product files + shared run_id."""

    PRODUCT_KEYS = (
        "manifest.json",
        "executive_summary.md",
        "extra_weekly_pack.xlsx",
        "opportunities.csv",
        "checksums.json",
    )

    def collect_artifacts(self, pack_dir: Path) -> dict[str, Any]:
        pack_dir = Path(pack_dir)
        artifacts: dict[str, str | None] = {}
        for name in self.PRODUCT_KEYS:
            p = pack_dir / name
            artifacts[name] = str(p) if p.is_file() else None
        run_id = None
        manifest_path = pack_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                run_id = (
                    data.get("cycle_id")
                    or data.get("run_id")
                    or (data.get("cycle") or {}).get("cycle_id")
                )
            except (json.JSONDecodeError, OSError):
                run_id = None
        return {
            "pack_dir": str(pack_dir),
            "run_id": run_id,
            "artifacts": artifacts,
            "n_present": sum(1 for v in artifacts.values() if v),
        }


class DeadlineDecisionAdapter:
    """Fail-closed: expired deadline always blocks participation even if status open."""

    def is_expired_blocker(self, *, deadline_passed: bool, status_open: bool) -> bool:
        return bool(deadline_passed)


def default_freshness_gate() -> FreshnessGate:
    return WeeklyFreshnessAdapter()


def default_coverage_contract() -> CoverageContract:
    return RatioCoverageAdapter()


def default_pack_delivery() -> PackDelivery:
    return DirectoryPackDeliveryAdapter()


def default_decision_rules() -> DecisionRules:
    return DeadlineDecisionAdapter()
