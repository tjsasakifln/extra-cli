"""CLI: python3 -m scripts.ops.coverage_live_proof run --output DIR"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.ops.coverage_live_proof.admission import sanitize_text
from scripts.ops.coverage_live_proof.errors import CoverageLiveProofError
from scripts.ops.coverage_live_proof.runner import (
    resolve_cli_dsn,
    run_live_proof,
    teardown_ephemeral,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.ops.coverage_live_proof",
        description=(
            "Hermetic real-PostgreSQL live proof of source-wide vs entity-scoped "
            "coverage identity (issue #350). Does not change coverage engines."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="provision, migrate, seed, evaluate, hash, teardown")
    run_p.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN (default: LOCAL_DATALAKE_DSN). Required; no implicit default.",
    )
    run_p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory for evidence.json, evidence.normalized.json, SHA256SUMS",
    )
    run_p.add_argument(
        "--skip-golden-path",
        action="store_true",
        help="Skip the shipped golden-path subprocess (tests only)",
    )
    run_p.add_argument(
        "--keep-database",
        action="store_true",
        help="Do not DROP the ephemeral database (debug only)",
    )

    td = sub.add_parser("teardown", help="DROP a campaign ephemeral database by name")
    td.add_argument("--dsn", default=None, help="Admin DSN (default: LOCAL_DATALAKE_DSN)")
    td.add_argument(
        "--database",
        required=True,
        help="Must match coverage_live_proof_[12 hex chars]",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dsn = resolve_cli_dsn(getattr(args, "dsn", None))
    try:
        if args.command == "run":
            pack = run_live_proof(
                dsn=dsn,
                output_dir=args.output,
                execute_golden=not args.skip_golden_path,
                skip_teardown=bool(args.keep_database),
            )
            digest = pack["normalized_semantic_hash"]
            print(f"coverage_live_proof_ok hash={digest}")
            print(f"evidence={args.output / 'evidence.json'}")
            return 0
        if args.command == "teardown":
            if not dsn:
                print("explicit DSN required (--dsn or LOCAL_DATALAKE_DSN)", file=sys.stderr)
                return 2
            teardown_ephemeral(dsn, args.database)
            print(f"dropped {args.database}")
            return 0
    except CoverageLiveProofError as exc:
        print(sanitize_text(str(exc), dsn), file=sys.stderr)
        return 2
    except Exception as exc:
        print(sanitize_text(f"{type(exc).__name__}: {exc}", dsn), file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
