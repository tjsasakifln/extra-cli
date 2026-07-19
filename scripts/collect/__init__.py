"""Collect layer — uniform execution contract for source runs.

Boundaries (Kingfisher-inspired, adapted):
- collect: fetch official data, register run, store raw location/hashes
- process / quality / intelligence / delivery live outside this package
"""

from scripts.collect.run_contract import (
    TERMINAL_STATUSES,
    CollectionRun,
    TerminalStatus,
    classify_terminal_status,
    new_collection_id,
    persist_pipeline_run,
)

__all__ = [
    "TERMINAL_STATUSES",
    "CollectionRun",
    "TerminalStatus",
    "classify_terminal_status",
    "new_collection_id",
    "persist_pipeline_run",
]
