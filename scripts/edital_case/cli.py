"""CLI entry point: python -m scripts.edital_case ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.edital_case import CAMPAIGN_ID, __version__
from scripts.edital_case.isolation import IsolationError, enforce_isolation
from scripts.edital_case.pipeline import (
    cmd_analyze,
    cmd_create,
    cmd_ingest,
    cmd_report,
    cmd_run,
    cmd_verify,
    default_case_root,
)


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.edital_case",
        description=(
            f"{CAMPAIGN_ID}: triagem técnica rastreável de editais "
            "(case pack imutável, sem banco/VPS)."
        ),
    )
    p.add_argument("--version", action="version", version=f"edital_case {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="Create empty case scaffold")
    c.add_argument("--case-id", required=True)
    c.add_argument("--source", required=True, help="file|directory|zip|url|manifest")
    c.add_argument("--case-root", default=None)

    c = sub.add_parser("ingest", help="Acquire, hash, extract, classify")
    c.add_argument("--case", required=True, dest="case_dir")

    c = sub.add_parser("analyze", help="Checklist, missing annexes, findings, recommendation")
    c.add_argument("--case", required=True, dest="case_dir")
    c.add_argument(
        "--profile",
        default="config/client_profiles/extra.yaml",
        help="Client profile YAML (read-only)",
    )

    c = sub.add_parser("report", help="Generate MD/HTML/XLSX/PDF reports")
    c.add_argument("--case", required=True, dest="case_dir")

    c = sub.add_parser("verify", help="Verify hashes, citations, reconciliation")
    c.add_argument("--case", required=True, dest="case_dir")

    c = sub.add_parser("run", help="Full pipeline: create→ingest→analyze→report→verify")
    c.add_argument("--case-id", required=True)
    c.add_argument("--source", required=True)
    c.add_argument("--profile", default="config/client_profiles/extra.yaml")
    c.add_argument("--output", default=None, help="Case root or case directory")

    c = sub.add_parser("gate", help="Run campaign gates")
    c.add_argument(
        "gate_name",
        nargs="?",
        default="campaign",
        choices=[
            "campaign",
            "parallel-isolation",
            "isolation",
            "release-candidate",
            "rc",
            "verify",
        ],
    )
    c.add_argument(
        "--campaign-dir",
        default="artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command != "gate":
            enforce_isolation()
    except IsolationError as exc:
        print(json.dumps({"error": "ISOLATION", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3

    try:
        if args.command == "create":
            case_root = Path(args.case_root) if args.case_root else default_case_root()
            result = cmd_create(args.case_id, args.source, case_root=case_root)
        elif args.command == "ingest":
            result = cmd_ingest(Path(args.case_dir))
        elif args.command == "analyze":
            profile = Path(args.profile) if args.profile else None
            result = cmd_analyze(Path(args.case_dir), profile)
            # compact output
            result = {
                "recommendation": (result.get("recommendation") or {}).get("recommendation"),
                "checklist_items": (result.get("checklist") or {}).get("item_count"),
                "findings": (result.get("findings") or {}).get("count"),
                "missing": (result.get("missing") or {}).get("missing_count"),
                "timeline_events": (result.get("timeline") or {}).get("event_count"),
            }
        elif args.command == "report":
            result = cmd_report(Path(args.case_dir))
            result = {
                "reports_dir": result.get("reports_dir"),
                "reconciliation": result.get("reconciliation"),
                "recommendation": (result.get("model") or {}).get("recommendation"),
            }
        elif args.command == "verify":
            result = cmd_verify(Path(args.case_dir))
        elif args.command == "run":
            profile = Path(args.profile) if args.profile else None
            output = Path(args.output) if args.output else None
            result = cmd_run(
                case_id=args.case_id,
                source=args.source,
                profile=profile,
                output=output,
            )
        elif args.command == "gate":
            from scripts.edital_case import gate as gate_mod

            camp = Path(args.campaign_dir)
            if args.gate_name in {"parallel-isolation", "isolation"}:
                result = gate_mod.gate_parallel_isolation(camp)
            elif args.gate_name == "campaign":
                result = gate_mod.gate_campaign(camp)
            elif args.gate_name in {"release-candidate", "rc"}:
                result = gate_mod.gate_release_candidate(camp)
            elif args.gate_name == "verify":
                result = gate_mod.gate_verify(camp)
            else:
                result = {"error": "unknown gate"}
            _print(result)
            return 0 if result.get("ok") else 1
        else:
            parser.error(f"unknown command {args.command}")
            return 2
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"error": type(exc).__name__, "detail": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    _print(result)
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
