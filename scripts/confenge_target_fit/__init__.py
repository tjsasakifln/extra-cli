"""CONFENGE target-fit continuous refresh — live materialization of the datalake.

Principle:
  TARGET_FIT = derived state of the datalake
  (not a spreadsheet/snapshot periodically forgotten)

The datalake ETL path never depends on this package. Failures here leave the
datalake committed and mark target-fit STALE / RETRY_PENDING.
"""

from __future__ import annotations

STORE_SCHEMA_VERSION = "confenge-tf-store-v1"
MODULE_VERSION = "confenge-target-fit-continuous-refresh-v1"

# Re-export classifier contract (shared with PR #211 pilot integrity)
from scripts.confenge_universe.target_fit import (  # noqa: E402
    TARGET_CONFIRMED,
    TARGET_FIT_VERSION,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
    TargetFitDecision,
    classify_target_fit,
)

# Operational classes (materialization layer, not ICP classes)
REFRESH_FAILED = "REFRESH_FAILED"
RECOMPUTE_REQUIRED = "RECOMPUTE_REQUIRED"

# Async modes
MODE_SHADOW = "SHADOW"
MODE_ACTIVE = "ACTIVE"
MODE_CANARY = "CANARY"
MODE_AUTO_PAUSE = "AUTO_PAUSE"

# Dirty queue statuses
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_RETRY = "retry"
STATUS_DEAD = "dead"
STATUS_SKIPPED = "skipped_same_fingerprint"
STATUS_REFRESH_FAILED = "refresh_failed"

# Transition event types
EVT_CONFIRMED = "TARGET_FIT_CONFIRMED"
EVT_LOST = "TARGET_FIT_LOST"
EVT_RESEARCH_REQUIRED = "TARGET_FIT_RESEARCH_REQUIRED"
EVT_EVIDENCE_CHANGED = "TARGET_FIT_EVIDENCE_CHANGED"
EVT_VERSION_RECOMPUTED = "TARGET_FIT_VERSION_RECOMPUTED"
EVT_DOWNGRADE = "TARGET_FIT_DOWNGRADE"
EVT_UPGRADE = "TARGET_FIT_UPGRADE"
EVT_UNCHANGED = "TARGET_FIT_UNCHANGED"
EVT_FAILED = "TARGET_FIT_REFRESH_FAILED"

# Health statuses
HEALTH_HEALTHY = "HEALTHY"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_STALE = "STALE"
HEALTH_FAILED = "FAILED"

# Rank for upgrade/downgrade detection (higher = better commercial fit)
CLASS_RANK: dict[str, int] = {
    TARGET_OUT_OF_SCOPE: 0,
    TARGET_PROBABLE_RESEARCH: 1,
    TARGET_CONFIRMED: 2,
    RECOMPUTE_REQUIRED: -1,
    REFRESH_FAILED: -2,
}

__all__ = [
    "CLASS_RANK",
    "EVT_CONFIRMED",
    "EVT_DOWNGRADE",
    "EVT_EVIDENCE_CHANGED",
    "EVT_FAILED",
    "EVT_LOST",
    "EVT_RESEARCH_REQUIRED",
    "EVT_UNCHANGED",
    "EVT_UPGRADE",
    "EVT_VERSION_RECOMPUTED",
    "HEALTH_DEGRADED",
    "HEALTH_FAILED",
    "HEALTH_HEALTHY",
    "HEALTH_STALE",
    "MODE_ACTIVE",
    "MODE_AUTO_PAUSE",
    "MODE_CANARY",
    "MODE_SHADOW",
    "MODULE_VERSION",
    "RECOMPUTE_REQUIRED",
    "REFRESH_FAILED",
    "STATUS_DEAD",
    "STATUS_DONE",
    "STATUS_PENDING",
    "STATUS_PROCESSING",
    "STATUS_REFRESH_FAILED",
    "STATUS_RETRY",
    "STATUS_SKIPPED",
    "STORE_SCHEMA_VERSION",
    "TARGET_CONFIRMED",
    "TARGET_FIT_VERSION",
    "TARGET_OUT_OF_SCOPE",
    "TARGET_PROBABLE_RESEARCH",
    "TargetFitDecision",
    "classify_target_fit",
]
