"""Capability registry package."""

from __future__ import annotations

from scripts.command_center.capabilities.base import Capability
from scripts.command_center.capabilities.definitions import all_capabilities
from scripts.command_center.capabilities.registry import CapabilityRegistry, get_registry

__all__ = ["Capability", "CapabilityRegistry", "all_capabilities", "get_registry"]
