"""In-memory capability registry with dynamic availability."""

from __future__ import annotations

from typing import Any

from scripts.command_center.capabilities.base import Availability, Capability
from scripts.command_center.capabilities.definitions import all_capabilities


class CapabilityRegistry:
    def __init__(self, caps: list[Capability] | None = None) -> None:
        self._caps = {c.id: c for c in (caps if caps is not None else all_capabilities())}

    def get(self, capability_id: str) -> Capability | None:
        return self._caps.get(capability_id)

    def list(self) -> list[Capability]:
        return list(self._caps.values())

    def public_list(self) -> list[dict[str, Any]]:
        return [c.public_dict() for c in self._caps.values()]

    def available_ids(self) -> list[str]:
        out = []
        for c in self._caps.values():
            avail, _ = c.detect_availability()
            if avail == Availability.AVAILABLE:
                out.append(c.id)
        return out

    def categories_summary(self) -> dict[str, dict[str, int]]:
        summary: dict[str, dict[str, int]] = {}
        for c in self._caps.values():
            bucket = summary.setdefault(c.category, {"total": 0, "available": 0, "unavailable": 0})
            bucket["total"] += 1
            avail, _ = c.detect_availability()
            if avail == Availability.AVAILABLE:
                bucket["available"] += 1
            else:
                bucket["unavailable"] += 1
        return summary


_REGISTRY: CapabilityRegistry | None = None


def get_registry() -> CapabilityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
    return _REGISTRY


def reset_registry(caps: list[Capability] | None = None) -> CapabilityRegistry:
    global _REGISTRY
    _REGISTRY = CapabilityRegistry(caps)
    return _REGISTRY
