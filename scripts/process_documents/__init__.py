"""Canonical procurement process public documents capability.

Capability id: ``procurement_process_documents``

Discovers, collects, preserves, classifies and audits public documents of
administrative procurement processes for the 1.093-entity Extra/CONFENGE
universe. Reuses entity source registry, universe loader and fail-closed
run semantics — does not introduce a second registry or crawl framework.
"""

from __future__ import annotations

__all__ = [
    "CAPABILITY_ID",
    "CAPABILITY_DECOMPOSITION",
    "ADAPTER_VERSION",
]

CAPABILITY_ID = "procurement_process_documents"
CAPABILITY_DECOMPOSITION: tuple[str, ...] = (
    "notice_documents",
    "planning_documents",
    "bidder_submission_documents",
    "session_and_judgment_documents",
    "appeal_documents",
    "contract_execution_documents",
    "administrative_process_documents",
)
ADAPTER_VERSION = "process_documents/1.1.0"
