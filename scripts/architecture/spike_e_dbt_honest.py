"""Honest dbt spike status — no fake experiment.

Reclassifies spike E as REJECTED_WITHOUT_EXPERIMENT unless a real isolated
dbt project + ≥200 opportunity temporal corpus is provided (not in this PR).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def evaluate_dbt_spike() -> dict[str, Any]:
    return {
        "spike": "E",
        "component": "dbt-core snapshots",
        "decision": "REJECTED_WITHOUT_EXPERIMENT",
        "honest": True,
        "experiment_run": False,
        "dbt_installed": False,
        "corpus_opportunities": 0,
        "min_corpus_required": 200,
        "reason": (
            "No isolated dbt project was executed against a 200+ opportunity temporal "
            "corpus in this campaign. Prior synthetic-5-dict 'benchmark' is invalid as "
            "evaluation evidence. Re-open only with: isolated schema, real/sanitized "
            "dataset ≥200, status transitions gold set, and measured concordance."
        ),
        "production_dep_added": False,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
