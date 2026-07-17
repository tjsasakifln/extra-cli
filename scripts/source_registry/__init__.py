"""Canonical entity source registry — one record per target-universe entity.

Maps each of the 1093 entities in ``config/target_entities_200km.csv`` to
known/potential data sources, portals, blockers, and next actions.

Public API::

    from scripts.source_registry.builder import build_registry_from_csv, load_registry
    from scripts.source_registry.models import EntitySourceRecord
"""

from __future__ import annotations

from scripts.source_registry.models import (
    ACCESS_STATUSES,
    BLOCKER_CATEGORIES,
    INTEGRATION_TYPES,
    DiscoveryResult,
    EntitySourceRecord,
)

__all__ = [
    "ACCESS_STATUSES",
    "BLOCKER_CATEGORIES",
    "INTEGRATION_TYPES",
    "DiscoveryResult",
    "EntitySourceRecord",
]
