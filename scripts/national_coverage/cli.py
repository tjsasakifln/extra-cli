"""CLI for the versioned national coverage denominator.

python3 -m scripts.national_coverage evaluate --input FIXTURE --out PAYLOAD
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from scripts.national_coverage.evaluate import evaluate_from_dict


def evaluate_path(input_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coverage input must be a JSON object")
    return evaluate_from_dict(payload)


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _summary(payload: dict[str, Any], *, cost_ms: float) -> dict[str, Any]:
    consumer = payload.get("consumer") or {}
    return {
        "verdict": payload.get("verdict"),
        "national_claim_authorized": payload.get("national_claim_authorized"),
        "national_universe_id": payload.get("national_universe_id"),
        "catalog_hash": payload.get("catalog_hash"),
        "raw_hash": payload.get("raw_hash"),
        "expected_partitions": (payload.get("partitions") or {}).get("expected"),
        "closed_partitions": (payload.get("partitions") or {}).get("closed"),
        "reason_codes": payload.get("reason_codes"),
        "coverage_pct": consumer.get("coverage_pct"),
        "content_hash": payload.get("content_hash"),
        "consumer_content_hash": consumer.get("content_hash"),
        "cost_ms": cost_ms,
    }


def _cmd_evaluate(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    payload = evaluate_path(args.input)
    cost_ms = round((time.perf_counter() - started) * 1000, 3)
    if args.out:
        _write_json(Path(args.out), payload)
    sys.stdout.write(json.dumps(_summary(payload, cost_ms=cost_ms), ensure_ascii=False, sort_keys=True) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.national_coverage")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="Evaluate a coverage fixture")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--out", default=None)
    evaluate.set_defaults(func=_cmd_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
