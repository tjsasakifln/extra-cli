#!/usr/bin/env python3
"""Build a simple dependency graph for DoD/gates (worker)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any


def build_default_graph(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Domain-informed default graph for Extra Consultoria current stage.

    Conservative: does not claim completion; models known gates and blockers.
    """
    nodes = [
        {"id": "truth-no-false-green", "kind": "gate", "label": "No false green / truth seals honest"},
        {"id": "local-resilience-mechanics", "kind": "capability", "label": "Local resilience mechanics (offline)"},
        {"id": "pre-vps-offline-gate", "kind": "gate", "label": "pre-vps-final-gate-offline + CI resilience-gate"},
        {"id": "live-canary-pg", "kind": "gate", "label": "Live canary + real PostgreSQL evidence"},
        {"id": "pre-vps-final-ready", "kind": "seal", "label": "PRE_VPS_FINAL_READY"},
        {"id": "vps-provision", "kind": "infra", "label": "VPS provision + timers"},
        {"id": "vps-soak-24h", "kind": "gate", "label": "VPS soak 24h"},
        {"id": "vps-operational", "kind": "seal", "label": "VPS_OPERATIONAL"},
        {"id": "source-registry-1093", "kind": "capability", "label": "Source registry 1093 entities"},
        {"id": "operational-coverage-pipeline", "kind": "capability", "label": "Operational coverage stages + provenance"},
        {"id": "coverage-95", "kind": "gate", "label": "Operational coverage >=95% (1039/1093)"},
        {"id": "freshness-sla", "kind": "gate", "label": "Freshness per entity within SLAs"},
        {"id": "recall-95", "kind": "gate", "label": "Independent stratified recall >=95%"},
        {"id": "qa-po-e3-stories", "kind": "process", "label": "QA/PO close E3.S1/S2"},
        {"id": "commercial-signal-not-coverage", "kind": "constraint", "label": "Commercial signal must not be sold as coverage"},
        {"id": "workspace-daily-cli", "kind": "capability", "label": "Daily workspace CLI commands"},
        {"id": "project-done", "kind": "seal", "label": "PROJECT_DONE"},
    ]
    edges = [
        ("local-resilience-mechanics", "pre-vps-offline-gate"),
        ("pre-vps-offline-gate", "live-canary-pg"),
        ("live-canary-pg", "pre-vps-final-ready"),
        ("truth-no-false-green", "pre-vps-final-ready"),
        ("pre-vps-final-ready", "vps-provision"),
        ("vps-provision", "vps-soak-24h"),
        ("vps-soak-24h", "vps-operational"),
        ("source-registry-1093", "operational-coverage-pipeline"),
        ("operational-coverage-pipeline", "coverage-95"),
        ("operational-coverage-pipeline", "freshness-sla"),
        ("coverage-95", "project-done"),
        ("freshness-sla", "project-done"),
        ("recall-95", "project-done"),
        ("vps-operational", "project-done"),
        ("qa-po-e3-stories", "pre-vps-final-ready"),
        ("commercial-signal-not-coverage", "coverage-95"),
        ("truth-no-false-green", "coverage-95"),
    ]
    edge_objs = [{"from": a, "to": b, "type": "hard"} for a, b in edges]

    # critical path approximation toward PRE_VPS then coverage
    critical_path = [
        "truth-no-false-green",
        "local-resilience-mechanics",
        "pre-vps-offline-gate",
        "live-canary-pg",
        "qa-po-e3-stories",
        "pre-vps-final-ready",
        "operational-coverage-pipeline",
        "coverage-95",
        "project-done",
    ]

    return {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nodes": nodes,
        "edges": edge_objs,
        "critical_path": critical_path,
        "context_notes": (context or {}).get("notes", []),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args(argv)
    graph = build_default_graph()
    text = json.dumps(graph, indent=2, ensure_ascii=False)
    if args.output:
        Path = __import__("pathlib").Path
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
