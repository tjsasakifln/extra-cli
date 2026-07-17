#!/usr/bin/env python3
"""Entity Source Registry CLI.

Commands:
    build       — Build registry from target_entities_200km.csv
    gaps        — Generate nominal gap report
    discover    — Semi-automatic source discovery
    show        — Show registry record(s) by CNPJ
    stats       — Print registry summary stats
    acquire     — Run an acquisition strategy (pncp_orgao_probe | ciga_municipio_expand)

Usage::

    python -m scripts.source_registry.cli build
    python -m scripts.source_registry.cli gaps --output output/coverage/
    python -m scripts.source_registry.cli discover --limit 50 --dry-run
    python -m scripts.source_registry.cli show --cnpj 82892324
    python -m scripts.source_registry.cli stats
    python -m scripts.source_registry.cli acquire --strategy pncp_orgao_probe --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scripts.source_registry.builder import (
    DEFAULT_CSV,
    DEFAULT_REGISTRY_JSONL,
    build_registry_from_csv,
    find_by_cnpj,
    load_registry,
    summarize_registry,
)
from scripts.source_registry.discovery import discover_batch
from scripts.source_registry.gap_report import generate_gap_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("source_registry")


def cmd_build(args: argparse.Namespace) -> int:
    records = build_registry_from_csv(
        csv_path=args.csv,
        persist=True,
        registry_path=args.output,
    )
    summary = summarize_registry(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nRegistry: {args.output or DEFAULT_REGISTRY_JSONL} ({len(records)} entities)", file=sys.stderr)
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    records = load_registry(args.registry)
    summary = generate_gap_report(records, output_dir=args.output)
    print(json.dumps({k: v for k, v in summary.items() if k != "sample"}, ensure_ascii=False, indent=2))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    records = load_registry(args.registry)
    results = discover_batch(
        records,
        limit=args.limit,
        dry_run=args.dry_run,
        only_gaps=not args.all,
        save=True,
    )
    payload = {
        "count": len(results),
        "dry_run": args.dry_run,
        "results": [
            {
                "canonical_id": r.canonical_id,
                "confidence": r.confidence,
                "best": r.best_candidate,
                "candidates": len(r.candidates),
                "probed": len(r.probed),
                "notes": r.notes,
            }
            for r in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    records = load_registry(args.registry)
    matches = find_by_cnpj(records, args.cnpj)
    if not matches:
        print(json.dumps({"cnpj": args.cnpj, "matches": []}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps([m.to_dict() for m in matches], ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    records = load_registry(args.registry)
    summary = summarize_registry(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_acquire(args: argparse.Namespace) -> int:
    records = load_registry(args.registry)
    strategy = (args.strategy or "").strip().lower()
    dry_run = args.dry_run
    limit = args.limit

    if strategy == "pncp_orgao_probe":
        from scripts.source_registry.acquisition.pncp_orgao_probe import probe_pncp_orgaos

        summary = probe_pncp_orgaos(
            records,
            limit=limit,
            dry_run=dry_run,
            persist=True,
        )
    elif strategy in {"ciga_municipio_expand", "ciga"}:
        from scripts.source_registry.acquisition.ciga_municipio_expand import (
            expand_ciga_by_municipio,
        )

        summary = expand_ciga_by_municipio(
            records,
            limit=limit if limit > 0 else 0,
            persist=True,
        )
    else:
        print(
            f"Unknown strategy: {strategy!r}. Use: pncp_orgao_probe | ciga_municipio_expand",
            file=sys.stderr,
        )
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.source_registry.cli",
        description="Canonical entity source registry for the 1093-entity universe",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build registry from CSV")
    p_build.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Seed CSV path")
    p_build.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Registry JSONL output path (default: data/entity_source_registry.jsonl)",
    )
    p_build.set_defaults(func=cmd_build)

    p_gaps = sub.add_parser("gaps", help="Generate gap report for uncovered entities")
    p_gaps.add_argument("--registry", type=Path, default=None)
    p_gaps.add_argument(
        "--output",
        type=Path,
        default=Path("output/coverage"),
        help="Output directory for gap JSONL + MD",
    )
    p_gaps.set_defaults(func=cmd_gaps)

    p_disc = sub.add_parser("discover", help="Semi-automatic source discovery")
    p_disc.add_argument("--registry", type=Path, default=None)
    p_disc.add_argument("--limit", type=int, default=50)
    p_disc.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip HTTP probes (default: true)",
    )
    p_disc.add_argument("--all", action="store_true", help="Include operational entities")
    p_disc.set_defaults(func=cmd_discover)

    p_show = sub.add_parser("show", help="Show entity record(s) by CNPJ")
    p_show.add_argument("--cnpj", required=True, help="CNPJ (partial or full)")
    p_show.add_argument("--registry", type=Path, default=None)
    p_show.set_defaults(func=cmd_show)

    p_stats = sub.add_parser("stats", help="Print registry summary")
    p_stats.add_argument("--registry", type=Path, default=None)
    p_stats.set_defaults(func=cmd_stats)

    p_acq = sub.add_parser("acquire", help="Run acquisition strategy")
    p_acq.add_argument(
        "--strategy",
        required=True,
        choices=["pncp_orgao_probe", "ciga_municipio_expand", "ciga"],
        help="Acquisition strategy name",
    )
    p_acq.add_argument("--limit", type=int, default=100)
    p_acq.add_argument("--registry", type=Path, default=None)
    p_acq.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="For pncp_orgao_probe: skip live API (default true)",
    )
    p_acq.set_defaults(func=cmd_acquire)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return int(func(args))
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
