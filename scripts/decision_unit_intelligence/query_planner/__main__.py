"""python -m scripts.decision_unit_intelligence.query_planner"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.decision_unit_intelligence.query_planner.benchmark import run_query_yield
from scripts.decision_unit_intelligence.query_planner.spec import DEFAULT_POLICY_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dui-query-planner")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--query-policy-version", default=DEFAULT_POLICY_VERSION)
    parser.add_argument(
        "--primary",
        choices=("searxng", "ddgs", "replay", "replay-searxng", "replay-ddgs"),
        default="searxng",
    )
    parser.add_argument(
        "--compare",
        choices=("ddgs", "searxng", "replay", "replay-ddgs", "replay-searxng", "off"),
        default="ddgs",
    )
    parser.add_argument("--searxng-url")
    parser.add_argument("--search-results-per-query", type=int, default=5)
    parser.add_argument("--web-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--search-cache-dir", default=".cache/confenge-prospect")
    parser.add_argument("--require-live", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_query_yield(
        out_dir=Path(args.out),
        limit=args.limit,
        policy_version=args.query_policy_version,
        primary=args.primary,
        compare=None if args.compare in {"off", "none", None} else args.compare,
        searxng_url=args.searxng_url or os.getenv("CONFENGE_SEARXNG_URL"),
        cache_dir=Path(args.search_cache_dir),
        results_per_query=args.search_results_per_query,
        timeout_seconds=args.web_timeout_seconds,
        allow_replay=not args.require_live,
    )
    print(
        json.dumps(
            {
                "out": args.out,
                "n": report["n"],
                "paths": report.get("paths"),
                "uplift": report.get("uplift"),
                "live_error": report.get("live_error"),
                "policy_version": report.get("derived_policy_version"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
