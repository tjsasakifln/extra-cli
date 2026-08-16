"""Observability report for inbound comparables canary runs."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from scripts.contract_comparables.constants import STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT
from scripts.contract_comparables.corpus import CANARY_CASES, case_records, case_request
from scripts.contract_comparables.engine import build_peer_group


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    groups: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    latencies_ms: list[float] = []
    for case_id in CANARY_CASES:
        case_started = time.perf_counter()
        result, document = build_peer_group(case_records(corpus, case_id), case_request(corpus, case_id))
        elapsed_ms = (time.perf_counter() - case_started) * 1000.0
        latencies_ms.append(elapsed_ms)
        statuses[result.status] += 1
        for code in document["reason_codes"]:
            reasons[code] += 1
        metrics = document.get("metrics") or {}
        groups.append(
            {
                "case_id": case_id,
                "focal_id": document["contract_id"],
                "peer_group_id": document["peer_group_id"],
                "status": document["status"],
                "reason_codes": document["reason_codes"],
                "n": metrics.get("n"),
                "coverage": document["coverage"],
                "missingness": document["missingness"],
                "usable_n": document["usable_n"],
                "total_n": document["total_n"],
                "content_hash": document["content_hash"],
                "latency_ms": round(elapsed_ms, 3),
            }
        )
    evaluated = sum(statuses.values())
    rejected = statuses[STATUS_HOLD] + statuses[STATUS_NOT]
    recommendation = "manter"
    if statuses[STATUS_COMPARABLE] == 0:
        recommendation = "ajustar"
    if evaluated and statuses[STATUS_NOT] == evaluated:
        recommendation = "matar"
    elapsed_total_ms = (time.perf_counter() - started) * 1000.0
    return {
        "schema": "contract-comparables-observability/1.0",
        "as_of": corpus.get("as_of"),
        "catalog_mode": corpus.get("catalog_mode"),
        "source": corpus.get("source"),
        "groups_evaluated": evaluated,
        "groups": groups,
        "status_counts": {
            STATUS_COMPARABLE: statuses[STATUS_COMPARABLE],
            STATUS_HOLD: statuses[STATUS_HOLD],
            STATUS_NOT: statuses[STATUS_NOT],
        },
        "reason_codes": dict(sorted(reasons.items())),
        "rejection_rate": round(rejected / evaluated, 4) if evaluated else 0.0,
        "metric_distribution": [
            {
                "case_id": item["case_id"],
                "n": item["n"],
                "status": item["status"],
            }
            for item in groups
        ],
        "cost_latency": {
            "total_ms": round(elapsed_total_ms, 3),
            "per_group_ms": [item["latency_ms"] for item in groups],
        },
        "late_arrivals": {
            "note": "A late arrival or rectification invalidates only groups that include the affected contract_id.",
            "cases_changed": [],
        },
        "recommendation": recommendation,
        "recommendation_rationale": (
            "Canary has at least one COMPARABLE group and explicit refusals; keep the engine."
            if recommendation == "manter"
            else "No COMPARABLE group; adjust gates or corpus before any live claim."
            if recommendation == "ajustar"
            else "Every group refused; kill or redesign the canary question."
        ),
    }
