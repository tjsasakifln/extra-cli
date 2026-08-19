"""CLI for the inbound contract-comparables engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.contract_comparables.corpus import (
    CANARY_CASES,
    case_records,
    case_request,
    load_corpus,
)
from scripts.contract_comparables.engine import build_peer_group
from scripts.contract_comparables.handoff import write_comparables_handoff
from scripts.contract_comparables.live import live_or_fixture_only, live_smoke_instructions
from scripts.contract_comparables.official_canary import run_official_canary
from scripts.contract_comparables.official_paving import (
    DEFAULT_AS_OF,
    DEFAULT_LIMIT,
    FOCAL_CANARY_CONTRACT_ID,
    LIVE_PAVING_CANARY_ID,
    run_live_paving_canary,
)
from scripts.contract_comparables.report import evaluate_corpus
from scripts.contract_comparables.serialize import validate_against_schema


def _dump(payload: Any) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    case_id = args.case
    if case_id not in corpus["cases"]:
        raise SystemExit(f"unknown case: {case_id}")
    request = case_request(corpus, case_id)
    if args.as_of:
        request = type(request)(**{**request.__dict__, "as_of": args.as_of})
    if args.focal:
        request = type(request)(**{**request.__dict__, "focal_contract_id": args.focal})
    _result, document = build_peer_group(case_records(corpus, case_id), request)
    errors = validate_against_schema(document)
    if errors:
        raise SystemExit(f"document failed schema checks: {errors}")
    if args.out:
        Path(args.out).write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return _dump(document)


def _cmd_canary(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    documents = []
    for case_id in CANARY_CASES:
        _result, document = build_peer_group(case_records(corpus, case_id), case_request(corpus, case_id))
        documents.append({"case_id": case_id, "document": document})
    return _dump({"cases": documents, "live_smoke": live_smoke_instructions()})


def _cmd_report(args: argparse.Namespace) -> int:
    corpus = load_corpus(args.corpus)
    report = evaluate_corpus(corpus)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.markdown:
            md_path = Path(args.markdown)
            md_path.write_text(render_markdown(report), encoding="utf-8")
    return _dump(report)


def _cmd_live(args: argparse.Namespace) -> int:
    payload = live_or_fixture_only(
        dsn=args.dsn,
        focal_id=args.focal,
        as_of=args.as_of,
        limit=args.limit,
    )
    return _dump(payload)


def _cmd_official_canary(args: argparse.Namespace) -> int:
    payload = run_official_canary(
        dsn=args.dsn,
        focal_id=args.focal,
        as_of=args.as_of,
        limit=args.limit,
        metric=args.metric,
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if payload.get("catalog_mode") == "official_live":
        raise SystemExit("official-canary refused to emit catalog_mode=official_live")
    return _dump(payload)


def _cmd_live_paving_handoff(args: argparse.Namespace) -> int:
    payload = run_live_paving_canary(
        dsn=args.dsn,
        focal_id=args.focal,
        as_of=args.as_of,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
        metric=args.metric,
        max_pages=args.max_pages,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    if payload.get("catalog_mode") == "official_live":
        raise SystemExit("live-paving-handoff refused to emit catalog_mode=official_live")
    if args.output:
        write_comparables_handoff(payload, Path(args.output))
        payload = {**payload, "handoff_dir": str(Path(args.output))}
    return _dump(payload)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Observabilidade — contract comparables inbound (#415)",
        "",
        f"- grupos avaliados: {report['groups_evaluated']}",
        f"- COMPARABLE: {report['status_counts']['COMPARABLE']}",
        f"- HOLD_FOR_DATA: {report['status_counts']['HOLD_FOR_DATA']}",
        f"- NOT_COMPARABLE: {report['status_counts']['NOT_COMPARABLE']}",
        f"- taxa de rejeição: {report['rejection_rate']}",
        f"- custo/latência total (ms): {report['cost_latency']['total_ms']}",
        f"- recomendação: {report['recommendation']}",
        "",
        "## Grupos",
        "",
    ]
    for group in report["groups"]:
        lines.append(
            f"- `{group['case_id']}` status={group['status']} n={group['n']} "
            f"usable={group['usable_n']}/{group['total_n']} reasons={group['reason_codes']}"
        )
    lines.extend(["", "## Reason codes", ""])
    for code, count in report["reason_codes"].items():
        lines.append(f"- `{code}`: {count}")
    lines.extend(
        [
            "",
            "## Late arrivals",
            "",
            report["late_arrivals"]["note"],
            "",
            "## Recomendação",
            "",
            report["recommendation_rationale"],
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.contract_comparables")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Emit one versioned peer-group document")
    build.add_argument("--corpus", default=None)
    build.add_argument("--case", default="comparable_clear")
    build.add_argument("--focal", default=None)
    build.add_argument("--as-of", dest="as_of", default=None)
    build.add_argument("--out", default=None)
    build.set_defaults(func=_cmd_build)

    canary = sub.add_parser("canary", help="Evaluate the seven golden cases")
    canary.add_argument("--corpus", default=None)
    canary.set_defaults(func=_cmd_canary)

    report = sub.add_parser("report", help="Write the observability report")
    report.add_argument("--corpus", default=None)
    report.add_argument("--out", default=None)
    report.add_argument("--markdown", default=None)
    report.set_defaults(func=_cmd_report)

    live = sub.add_parser("live", help="Probe a live snapshot or emit FIXTURE_ONLY")
    live.add_argument("--dsn", default=None)
    live.add_argument("--focal", default=None)
    live.add_argument("--as-of", dest="as_of", default="2026-08-01")
    live.add_argument("--limit", type=int, default=200)
    live.set_defaults(func=_cmd_live)

    official = sub.add_parser(
        "official-canary",
        help="Run the official paving canary or emit BLOCKED with the exact prerequisite",
    )
    official.add_argument("--dsn", default=None)
    official.add_argument("--focal", default=None)
    official.add_argument("--as-of", dest="as_of", default="2026-08-01")
    official.add_argument("--limit", type=int, default=200)
    official.add_argument("--metric", default="valor_integral_nominal")
    official.add_argument("--out", default=None)
    official.set_defaults(func=_cmd_official_canary)

    paving = sub.add_parser(
        "live-paving-handoff",
        help="Prove one official-live paving peer group or a named fail-closed refusal (#415)",
    )
    paving.add_argument("--dsn", default=None)
    paving.add_argument("--focal", default=FOCAL_CANARY_CONTRACT_ID)
    paving.add_argument("--as-of", dest="as_of", default=DEFAULT_AS_OF)
    paving.add_argument("--start-date", dest="start_date", default=None)
    paving.add_argument("--end-date", dest="end_date", default=None)
    paving.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    paving.add_argument("--metric", default="valor_integral_nominal")
    paving.add_argument("--max-pages", dest="max_pages", type=int, default=8)
    paving.add_argument("--cache-dir", dest="cache_dir", default=None)
    paving.add_argument(
        "--output",
        default=None,
        help=f"Handoff directory. Default: exports/authority-handoff/contract-comparables/1.0/{LIVE_PAVING_CANARY_ID}",
    )
    paving.set_defaults(func=_cmd_live_paving_handoff)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
