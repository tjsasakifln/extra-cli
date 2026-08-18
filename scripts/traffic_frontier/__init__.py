"""Factual traffic-opportunity frontier — producer-only pack for web-cfg.

Distinct from scripts.organic (Content Value Score) and scripts.opportunity_intel
(open-tender ranking). This module scores Market Answer / calculator /
comparative candidates with campaign weights and fail-closed hard gates.

Public entry:
  python3 -m scripts.traffic_frontier --out DIR
"""

from __future__ import annotations

from scripts.traffic_frontier.export import build_frontier_pack, write_frontier_pack
from scripts.traffic_frontier.gates import evaluate_hard_gates
from scripts.traffic_frontier.score import FRONTIER_WEIGHTS, compute_frontier_score

SCHEMA = "traffic-opportunity-frontier/1.0"
CONTRACT_VERSION = "v1.0.0"

__all__ = [
    "CONTRACT_VERSION",
    "FRONTIER_WEIGHTS",
    "SCHEMA",
    "build_frontier_pack",
    "compute_frontier_score",
    "evaluate_hard_gates",
    "write_frontier_pack",
]
