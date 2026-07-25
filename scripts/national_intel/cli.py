"""CLI entry: python -m scripts.national_intel <command>"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts.national_intel.agencies import run_agencies
from scripts.national_intel.benchmarks import run_benchmarks
from scripts.national_intel.competitors import run_competitors
from scripts.national_intel.db import connect, resolve_dsn
from scripts.national_intel.lineage import write_json


def _print(data: dict[str, Any], output: str | None) -> int:
    write_json(output, data)
    if not output:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(f"wrote {output} rows={data.get('row_count')} product={data.get('product_id')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.national_intel",
        description=(
            "Strategic intelligence over national PNCP contracts. "
            "Does NOT compute SC operational dual coverage. "
            "Prefer NATIONAL_INTEL_DSN on port 5435 (isolated)."
        ),
    )
    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--dsn",
            default=None,
            help="Postgres DSN (default NATIONAL_INTEL_DSN or LOCAL_DATALAKE_DSN)",
        )
        p.add_argument("--output", default=None, help="Write JSON artifact path")

    _add_common(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("competitors", help="Supplier rankings + UF footprint")
    _add_common(p_c)
    p_c.add_argument("--keyword", default=None)
    p_c.add_argument("--uf", default=None)
    p_c.add_argument("--limit", type=int, default=50)

    p_b = sub.add_parser("benchmarks", help="Value distribution benchmarks")
    _add_common(p_b)
    p_b.add_argument("--keyword", default=None)
    p_b.add_argument("--uf", default=None)
    p_b.add_argument("--min-sample", type=int, default=20)

    p_a = sub.add_parser("agencies", help="Contracting agency profiles")
    _add_common(p_a)
    p_a.add_argument("--keyword", default=None)
    p_a.add_argument("--uf", default=None)
    p_a.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)
    dsn = resolve_dsn(getattr(args, "dsn", None))

    with connect(dsn) as conn:
        if args.cmd == "competitors":
            data = run_competitors(
                conn,
                keyword=args.keyword,
                uf=args.uf,
                limit=args.limit,
                dsn=dsn,
            )
            return _print(data, args.output)
        if args.cmd == "benchmarks":
            data = run_benchmarks(
                conn,
                keyword=args.keyword,
                uf=args.uf,
                min_sample=args.min_sample,
                dsn=dsn,
            )
            return _print(data, args.output)
        if args.cmd == "agencies":
            data = run_agencies(
                conn,
                keyword=args.keyword,
                uf=args.uf,
                limit=args.limit,
                dsn=dsn,
            )
            return _print(data, args.output)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
