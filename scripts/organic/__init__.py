"""Organic Opportunity Engine — datalake facts → editorial/commercial opportunities.

Distinct from scripts.opportunity_intel (open tenders / commercial ranking).
This module turns public-contract aggregates into scored content opportunities
for the CONFENGE inbound system (web-cfg).

Public entry:
  python -m scripts.organic --pseo-dir PATH --out PATH
"""

from __future__ import annotations

from scripts.organic.engine import build_opportunities, load_pseo_snapshot, run_engine
from scripts.organic.gates import indexability_quality_gate
from scripts.organic.score import CONTENT_VALUE_WEIGHTS, compute_content_value_score

__all__ = [
    "CONTENT_VALUE_WEIGHTS",
    "build_opportunities",
    "compute_content_value_score",
    "indexability_quality_gate",
    "load_pseo_snapshot",
    "run_engine",
]
