"""Shipped CLI for the research-flagship export and health read."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.public_read.export import (
    EXPORT_FILENAME,
    load_export_artifact,
    write_research_export,
)
from scripts.public_read.payload import load_research_payload


def _cmd_export(args: argparse.Namespace) -> int:
    payload = load_research_payload(args.fixture)
    path = write_research_export(payload, args.out)
    artifact = load_export_artifact(path)
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "path": str(path),
                "content_hash": artifact["content_hash"],
                "national_claim_allowed": artifact["claim"]["national_claim_allowed"],
                "reason_codes": artifact["claim"]["reason_codes"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    artifact_path = Path(args.artifact)
    if artifact_path.is_dir():
        artifact_path = artifact_path / EXPORT_FILENAME
    artifact = load_export_artifact(artifact_path)
    sys.stdout.write(json.dumps(artifact["health"], ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.public_read")
    sub = parser.add_subparsers(dest="command", required=True)
    export_cmd = sub.add_parser("export-research", help="Write the versioned research export")
    export_cmd.add_argument("--fixture", required=True, help="Research fixture JSON")
    export_cmd.add_argument("--out", required=True, help="Output directory")
    export_cmd.set_defaults(func=_cmd_export)
    health_cmd = sub.add_parser("health", help="Read freshness/coverage/consumer errors")
    health_cmd.add_argument("--artifact", required=True, help="Export JSON or directory")
    health_cmd.set_defaults(func=_cmd_health)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
