"""Canonical CONFENGE outreach pipeline.

Production (activation-driven):
  universe → activation planner → hot set → account intelligence
  → contact resolution → confenge.outreach.v1 Warmbly feed

Smoke / diagnostic (diverse sample):
  universe → diverse sample (--limit-downstream) → expensive stages

No manual JSON handoff between stages. Production selection is capacity-aware
via the activation planner; --limit-downstream is not a commercial strategy.
"""

from __future__ import annotations

MODULE_VERSION = "1.1.0"
PIPELINE_ID = "confenge-outreach-pipeline-v1"
