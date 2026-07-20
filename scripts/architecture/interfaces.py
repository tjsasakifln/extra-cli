"""Narrow Protocols for Branch-by-Abstraction (ARCH-RESET §15 interfaces).

These seams allow future engines (quality, coverage, delivery) to swap without
a second orchestrator. Implementations live in adapters.py wrapping current code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FreshnessGate(Protocol):
    """Classify freshness for a source/opportunity observation."""

    def classify(
        self,
        *,
        status: str,
        age_hours: float | None,
        sla_hours: float,
        scope_complete: bool = True,
    ) -> str:
        """Return freshness label (e.g. fresh, stale, incomplete)."""
        ...


@runtime_checkable
class CoverageContract(Protocol):
    """Operational coverage metric surface (never invents 95%)."""

    def compute_operational_ratio(
        self,
        *,
        covered: int,
        universe: int,
        capability: str,
    ) -> dict[str, Any]:
        """Return ratio payload; must fail closed on invalid universe."""
        ...


@runtime_checkable
class PackDelivery(Protocol):
    """Weekly/decision pack artifact paths sharing a run_id."""

    def collect_artifacts(self, pack_dir: Path) -> dict[str, Any]:
        """Map product keys → paths present under pack_dir; include run_id if known."""
        ...


@runtime_checkable
class DecisionRules(Protocol):
    """Hard blockers / recommendation surface (no juridical claims)."""

    def is_expired_blocker(self, *, deadline_passed: bool, status_open: bool) -> bool:
        """True when participation must be blocked due to expired deadline."""
        ...
