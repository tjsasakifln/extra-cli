#!/usr/bin/env python3
"""ROI scoring worker — pure function over candidate dimensions + weights."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


DEFAULT_WEIGHTS = {
    "version": "1.0.0",
    "value_dimensions": {
        "gate_value": {"weight": 1.5},
        "unlock_power": {"weight": 1.3},
        "operational_impact": {"weight": 1.2},
        "risk_reduction": {"weight": 1.4},
        "evidence_gain": {"weight": 1.1},
    },
    "cost_dimensions": {
        "effort": {"weight": 1.2},
        "uncertainty": {"weight": 1.1},
        "external_dependency": {"weight": 1.3},
        "change_surface": {"weight": 1.0},
    },
}


def load_weights(path: Path | None) -> dict[str, Any]:
    if path and path.is_file():
        text = path.read_text(encoding="utf-8")
        if yaml:
            return yaml.safe_load(text)
        # minimal fallback: only used if PyYAML missing — use defaults
        return DEFAULT_WEIGHTS
    return DEFAULT_WEIGHTS


def clamp(v: float, lo: float = 0.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, float(v)))


def score_candidate(candidate: dict[str, Any], weights: dict[str, Any]) -> dict[str, Any]:
    value_dims = weights.get("value_dimensions", DEFAULT_WEIGHTS["value_dimensions"])
    cost_dims = weights.get("cost_dimensions", DEFAULT_WEIGHTS["cost_dimensions"])
    value = candidate.get("value") or {}
    cost = candidate.get("cost") or {}

    value_sum = 0.0
    value_detail = {}
    for name, meta in value_dims.items():
        w = float(meta.get("weight", 1.0))
        raw = clamp(value.get(name, 0))
        value_detail[name] = {"raw": raw, "weight": w, "weighted": raw * w}
        value_sum += raw * w

    cost_sum = 0.0
    cost_detail = {}
    for name, meta in cost_dims.items():
        w = float(meta.get("weight", 1.0))
        raw = clamp(cost.get(name, 0))
        # cost of 0 is invalid — treat as tiny epsilon to avoid div0 / free lunch
        if raw <= 0:
            raw = 0.25
        cost_detail[name] = {"raw": raw, "weight": w, "weighted": raw * w}
        cost_sum += raw * w

    roi = value_sum / cost_sum if cost_sum > 0 else 0.0
    out = dict(candidate)
    out["roi"] = round(roi, 4)
    out["value_sum"] = round(value_sum, 4)
    out["cost_sum"] = round(cost_sum, 4)
    out["value_detail"] = value_detail
    out["cost_detail"] = cost_detail
    return out


def rank_candidates(candidates: list[dict[str, Any]], weights: dict[str, Any]) -> list[dict[str, Any]]:
    scored = [score_candidate(c, weights) for c in candidates]
    scored.sort(key=lambda x: x.get("roi", 0), reverse=True)
    return scored


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", default=None)
    p.add_argument("--input", required=True, help="JSON file or - for stdin with {candidates:[...]}")
    p.add_argument("--top", type=int, default=0)
    args = p.parse_args(argv)

    weights = load_weights(Path(args.weights) if args.weights else None)
    if args.input == "-":
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    candidates = payload if isinstance(payload, list) else payload.get("candidates", [])
    ranked = rank_candidates(candidates, weights)
    if args.top > 0:
        ranked = ranked[: args.top]
    print(json.dumps({"weights_version": weights.get("version"), "candidates": ranked}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
