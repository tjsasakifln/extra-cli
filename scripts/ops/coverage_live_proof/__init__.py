"""Hermetic real-PostgreSQL live proof of #350 dual-coverage identity."""

from __future__ import annotations

EVIDENCE_SCHEMA_VERSION = "coverage-live-proof/1.0"
EPHEMERAL_DB_PREFIX = "coverage_live_proof_"
SEED_RUN_ID = "coverage-live-proof-seed"
SEED_COMPLETED_AT = "2026-08-01T00:00:00+00:00"

__all__ = [
    "EPHEMERAL_DB_PREFIX",
    "EVIDENCE_SCHEMA_VERSION",
    "SEED_COMPLETED_AT",
    "SEED_RUN_ID",
]
