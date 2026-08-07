"""Canonical CONFENGE outreach pipeline.

Chains:
  universe → diverse downstream sample → account intelligence
  → contact resolution → confenge.outreach.v1 Warmbly feed

No manual JSON handoff between stages. --limit-downstream bounds only the
expensive stages; universe discovery can still cover the full datalake.
"""

from __future__ import annotations

MODULE_VERSION = "1.0.0"
PIPELINE_ID = "confenge-outreach-pipeline-v1"
