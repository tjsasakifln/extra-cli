"""Decision & Outcome Memory v1 — client-scoped canonical operational memory.

PostgreSQL is the authoritative store. JSON/JSONL artifacts are projections or
import inputs, never the sole source of truth when persistence is enabled.
"""

from __future__ import annotations

SCHEMA_VERSION = "decision-memory/1.0"
CAMPAIGN_ID = "EXTRA-DECISION-OUTCOME-MEMORY-01"

__all__ = ["SCHEMA_VERSION", "CAMPAIGN_ID"]
