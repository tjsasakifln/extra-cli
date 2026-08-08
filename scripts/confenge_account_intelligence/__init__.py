"""CONFENGE account-intelligence service router (isolated module).

Transforms company/universe records into ``confenge-account-intelligence-v1``
dossiers: which CONFENGE service to offer now and how to approach the account.

This package does not import unmerged parallel-front modules. Core and tests
run fully offline. Optional external enrich is interface-only.
"""

from __future__ import annotations

from scripts.confenge_account_intelligence.pipeline import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    build_dossier,
    process_batch,
    process_record,
)

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "build_dossier",
    "process_batch",
    "process_record",
]

__version__ = "1.0.0"
