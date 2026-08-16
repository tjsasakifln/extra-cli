"""CLI for the unique national-claims gate.

python3 -m scripts.national_claims evaluate --input FIXTURE --out PAYLOAD
python3 -m scripts.national_claims report --input FIXTURE --format md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from scripts.national_claims.gate import decide
from scripts.national_claims.loader import load_request
from scripts.national_claims.preflight import live_smoke_command
from scripts.national_claims.report import observability, render_markdown


def evaluate_path(input_path: str | Path, *, producer_sha: str | None = None) -> dict[str, Any]:
    request = load_request(input_path)
    if producer_sha:
        from dataclasses import replace

        request = replace(request, producer_sha=producer_sha)
    return decide(request)


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cmd_evaluate(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    payload = evaluate_path(args.input, producer_sha=args.producer_sha)
    cost_ms = round((time.perf_counter() - started) * 1000, 3)
    report = observability(payload, cost_ms=cost_ms)
    if args.out:
        _write_json(Path(args.out), payload)
    if args.report:
        report_path = Path(args.report)
        if args.format == "md":
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_markdown(report), encoding="utf-8")
        else:
            _write_json(report_path, report)
    sys.stdout.write(
        json.dumps(
            {
                "authorization_state": payload["authorization_state"],
                "consumer_view": payload["consumer_view"],
                "nacional_completo": payload["nacional_completo"],
                "reason_codes": payload["reason_codes"],
                "content_hash": payload["content_hash"],
                "national_universe_id": payload["national_universe_id"],
                "catalog_hash": payload["catalog_hash"],
                "extra_1093_used_as_denominator": payload["extra_1093_used_as_denominator"],
                "row_count_used_as_completeness": payload["row_count_used_as_completeness"],
                "cost_ms": cost_ms,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    payload = evaluate_path(args.input, producer_sha=args.producer_sha)
    report = observability(payload, cost_ms=None)
    if args.format == "md":
        sys.stdout.write(render_markdown(report))
    else:
        _write_json(None, report)
    return 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    sys.stdout.write(live_smoke_command() + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.national_claims")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="run the six-state gate")
    evaluate.add_argument("--input", required=True, help="fixture JSON")
    evaluate.add_argument("--out", help="write the versioned payload")
    evaluate.add_argument("--report", help="write observability JSON/MD")
    evaluate.add_argument("--format", choices=("json", "md"), default="json")
    evaluate.add_argument("--producer-sha", dest="producer_sha")
    evaluate.set_defaults(func=_cmd_evaluate)
    report = sub.add_parser("report", help="print observability only")
    report.add_argument("--input", required=True)
    report.add_argument("--format", choices=("json", "md"), default="md")
    report.add_argument("--producer-sha", dest="producer_sha")
    report.set_defaults(func=_cmd_report)
    smoke = sub.add_parser("live-smoke", help="print the live smoke command")
    smoke.set_defaults(func=_cmd_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
