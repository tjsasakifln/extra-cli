#!/usr/bin/env python3
"""CLI for the formal coverage contract report.

Usage::

    python -m scripts.coverage.coverage_contract_cli report \\
        --output output/coverage/contract-report.json

    python -m scripts.coverage.coverage_contract_cli report --format table

Never renames commercial signal as coverage. Prints numerator/denominator/pct
for every metric.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.coverage_contract import (  # noqa: E402
    ALL_METRIC_IDS,
    LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY,
    METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
    build_contract_report,
    format_report_table,
    try_connect,
)


def _cmd_report(args: argparse.Namespace) -> int:
    conn = None
    db_note: str | None = None
    if not args.offline:
        conn = try_connect()
        if conn is None:
            db_note = (
                "DATABASE_URL unavailable or connection failed — "
                "using session artifacts / CSV with honest limitations"
            )

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    try:
        report = build_contract_report(
            conn=conn,
            as_of=as_of,
            session_dir=args.session_dir,
            registry_path=args.registry,
            sla_path=args.sla_config,
            benchmark_path=args.benchmark,
            seed_path=args.seed,
            csv_path=args.entities_csv,
        )
    finally:
        if conn is not None:
            with suppress(Exception):
                conn.close()

    payload = report.to_dict()
    if db_note:
        payload.setdefault("notes", []).append(db_note)

    # Guard: commercial signal must never be labeled coverage in the payload.
    commercial = payload["metrics"].get(METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL, {})
    if commercial.get("is_coverage_metric") is True:
        raise SystemExit(
            "FATAL: entities_with_recent_commercial_signal incorrectly marked as coverage"
        )
    if commercial.get("kind") == "coverage":
        raise SystemExit(
            "FATAL: entities_with_recent_commercial_signal kind must not be 'coverage'"
        )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"Wrote {out}", file=sys.stderr)

    fmt = (args.format or "json").lower()
    if fmt == "table":
        print(format_report_table(payload), end="")
    elif fmt == "json":
        if not args.output or args.print_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Unknown format: {fmt}", file=sys.stderr)
        return 2

    # Always print a compact metric summary to stderr for operators
    _print_metric_summary(payload)
    return 0


def _print_metric_summary(payload: dict[str, Any]) -> None:
    """Print numerator/denominator/pct for every metric to stderr."""
    print("\n--- metric summary (commercial signal ≠ coverage) ---", file=sys.stderr)
    print(f"headline: {payload.get('headline_metric')} (NOT coverage)", file=sys.stderr)
    metrics = payload.get("metrics") or {}
    for mid in list(ALL_METRIC_IDS) + [LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY]:
        m = metrics.get(mid)
        if not m:
            continue
        kind = m.get("kind")
        status = m.get("status")
        num = m.get("numerator")
        den = m.get("denominator")
        pct = m.get("pct")
        tag = "SIGNAL" if kind == "commercial_signal" else kind
        print(
            f"  [{tag}] {mid}: status={status}  {num}/{den}  pct={pct}",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coverage_contract_cli",
        description=(
            "Formal coverage contract reporter. "
            "Commercial signal is never renamed as coverage."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Generate coverage contract report")
    report.add_argument(
        "--output",
        "-o",
        default=None,
        help="Write JSON report to this path (e.g. output/coverage/contract-report.json)",
    )
    report.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="Stdout format (default: json)",
    )
    report.add_argument(
        "--print-json",
        action="store_true",
        help="Also print JSON to stdout when --output is set",
    )
    report.add_argument("--as-of", default=None, help="YYYY-MM-DD")
    report.add_argument("--session-dir", default=None, help="Session artifacts directory")
    report.add_argument(
        "--registry",
        default=None,
        help="Path to entity_source_registry.jsonl",
    )
    report.add_argument(
        "--sla-config",
        default=None,
        help="Path to coverage_slas.yaml",
    )
    report.add_argument(
        "--benchmark",
        default=None,
        help="Path to stratified opportunity_recall sample",
    )
    report.add_argument("--seed", default=None, help="Canonical universe seed spreadsheet")
    report.add_argument(
        "--entities-csv",
        default=None,
        help="Fallback entities CSV (default config/target_entities_200km.csv)",
    )
    report.add_argument(
        "--offline",
        action="store_true",
        help="Skip DB connection entirely (session/CSV only)",
    )
    report.set_defaults(func=_cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
