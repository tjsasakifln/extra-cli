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
from scripts.public_read.live_payload import (
    load_contracts_jsonl,
    load_json_payload,
    payload_from_live_corpus,
    payload_from_snapshot_document,
)
from scripts.public_read.margin_export import write_margin_export
from scripts.public_read.payload import load_research_payload


def _load_export_payload(args: argparse.Namespace):
    sources = {
        "fixture": args.fixture,
        "payload": args.payload,
        "snapshot": args.snapshot,
        "contracts_jsonl": args.contracts_jsonl,
    }
    present = [name for name, value in sources.items() if value]
    if len(present) != 1:
        raise SystemExit("export-research requires exactly one of --fixture, --payload, --snapshot, --contracts-jsonl")
    if args.fixture:
        return load_research_payload(args.fixture)
    if args.payload:
        return load_research_payload(args.payload)
    if args.snapshot:
        return payload_from_snapshot_document(load_json_payload(args.snapshot))
    if not args.denominator:
        raise SystemExit("--contracts-jsonl requires --denominator")
    denominator = load_json_payload(args.denominator)
    contracts = load_contracts_jsonl(args.contracts_jsonl)
    return payload_from_live_corpus(
        contracts=contracts,
        denominator=denominator,
        as_of=str(args.as_of or denominator.get("cutoff")),
        competence=str(args.competence or denominator.get("competence")),
        publication_age_hours=float(args.publication_age_hours),
        publication_lag_p99_hours=float(args.publication_lag_p99_hours),
        payload_id=str(args.payload_id or "live-corpus"),
    )


def _cmd_export(args: argparse.Namespace) -> int:
    payload = _load_export_payload(args)
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


def _cmd_export_margin(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    path = write_margin_export(raw, args.out)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "path": str(path),
                "content_hash": artifact["content_hash"],
                "record_count": artifact["coverage"]["record_count"],
                "reason_codes": artifact["reason_codes"],
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
    export_cmd.add_argument("--fixture", help="Research fixture JSON (tests only)")
    export_cmd.add_argument("--payload", help="Live/snapshot research payload JSON")
    export_cmd.add_argument("--snapshot", help="READY snapshot document JSON")
    export_cmd.add_argument("--contracts-jsonl", help="Official live contracts JSONL")
    export_cmd.add_argument("--denominator", help="#302 national-denominator JSON (with --contracts-jsonl)")
    export_cmd.add_argument("--as-of", dest="as_of", help="Snapshot cutoff (never wall-clock for live)")
    export_cmd.add_argument("--competence", help="Competence label for live corpus")
    export_cmd.add_argument("--payload-id", dest="payload_id", default="live-corpus")
    export_cmd.add_argument("--publication-age-hours", type=float, default=1.0)
    export_cmd.add_argument("--publication-lag-p99-hours", type=float, default=1.0)
    export_cmd.add_argument("--out", required=True, help="Output directory")
    export_cmd.set_defaults(func=_cmd_export)
    margin_cmd = sub.add_parser("export-margin", help="Write the versioned margin-defense facts export")
    margin_cmd.add_argument("--payload", required=True, help="Official contract facts JSON")
    margin_cmd.add_argument("--out", required=True, help="Output directory")
    margin_cmd.set_defaults(func=_cmd_export_margin)
    health_cmd = sub.add_parser("health", help="Read freshness/coverage/consumer errors")
    health_cmd.add_argument("--artifact", required=True, help="Export JSON or directory")
    health_cmd.set_defaults(func=_cmd_health)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
