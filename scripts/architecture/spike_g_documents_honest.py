"""Honest document-parser spike status.

Synthetic ReportLab PDFs alone are insufficient for KEEP_CURRENT adoption claims.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

REQUIRED_STRATA = {
    "digital_simple": 5,
    "multicolumn": 5,
    "tables": 5,
    "scanned": 5,
}


def evaluate_document_parser_spike(*, corpus_counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = corpus_counts or {k: 0 for k in REQUIRED_STRATA}
    gaps = {k: max(0, n - int(counts.get(k, 0))) for k, n in REQUIRED_STRATA.items()}
    complete = all(v == 0 for v in gaps.values())
    return {
        "spike": "G",
        "component": "document_parsers",
        "decision": "DEFERRED_NO_CORPUS" if not complete else "READY_FOR_ENGINE_COMPARISON",
        "honest": True,
        "required_strata": REQUIRED_STRATA,
        "corpus_counts": counts,
        "gaps": gaps,
        "reason": (
            "KEEP_CURRENT_STACK cannot be justified from 3 synthetic digital PDFs alone. "
            "Need versionable corpus ≥5 per stratum (simple/multicolumn/table/scanned) "
            "before parser adoption/rejection with Camelot/layout metrics."
        ),
        "pymupdf_license_gate": "AGPL_OR_COMMERCIAL",
        "production_dep_added": False,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
