"""CLI entry points for budget audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print_status(status: str) -> None:
    """Global exit status must be exactly PASS | BLOCKED | FAIL as last line semantics."""
    print(status)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m scripts.budget_audit",
        description="Engineering budget / composition / BDI audit (file-based, isolated)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="Create case and acquire sources")
    c.add_argument("--case-id", required=True)
    c.add_argument("--source", required=True)
    c.add_argument("--output", default=None, help="Case directory (default: $BUDGET_CASE_ROOT/<id>)")

    c = sub.add_parser("ingest", help="Parse workbooks into case store")
    c.add_argument("--case", required=True)

    c = sub.add_parser("map", help="Classify sheets and normalize items")
    c.add_argument("--case", required=True)

    c = sub.add_parser("audit", help="Run arithmetic, composition, BDI audits")
    c.add_argument("--case", required=True)

    c = sub.add_parser("compare", help="Compare two documents in a case")
    c.add_argument("--case", required=True)
    c.add_argument("--left", required=True)
    c.add_argument("--right", required=True)

    c = sub.add_parser("references", help="Compare against official reference manifest")
    c.add_argument("--case", required=True)
    c.add_argument("--reference-manifest", required=True)

    c = sub.add_parser("report", help="Generate PDF/HTML/MD/XLSX reports")
    c.add_argument("--case", required=True)

    c = sub.add_parser("verify", help="Independent verification (no silent regen of audits)")
    c.add_argument("--case", required=True)

    c = sub.add_parser("run", help="Full cycle: create→ingest→map→audit→report→verify")
    c.add_argument("--case-id", required=True)
    c.add_argument("--source", required=True)
    c.add_argument("--output", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    # Isolation first — skip_diff during early create before any commits
    from scripts.budget_audit.isolation import IsolationError, ensure_isolated

    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        ensure_isolated(skip_diff=False)
    except IsolationError as exc:
        print(f"ISOLATION FAIL: {exc}", file=sys.stderr)
        _print_status("FAIL")
        return 2

    try:
        status, payload = _dispatch(args)
    except Exception as exc:  # noqa: BLE001 — surface then FAIL
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        _print_status("FAIL")
        return 1

    if payload is not None:
        if isinstance(payload, (dict, list)):
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            print(payload)
    _print_status(status)
    return 0 if status == "PASS" else (3 if status == "BLOCKED" else 1)


def _dispatch(args: argparse.Namespace) -> tuple[str, object]:
    from scripts.budget_audit.ingest import create_case, ingest_case
    from scripts.budget_audit.pipeline import (
        audit_case,
        compare_case,
        map_case,
        references_case,
        report_case,
        run_full,
        verify_case,
    )

    cmd = args.command
    if cmd == "create":
        out = Path(args.output) if args.output else None
        case_dir = create_case(args.case_id, args.source, out)
        return "PASS", {"case_dir": str(case_dir)}
    if cmd == "ingest":
        result = ingest_case(Path(args.case))
        return "PASS", result
    if cmd == "map":
        result = map_case(Path(args.case))
        return "PASS", result
    if cmd == "audit":
        result = audit_case(Path(args.case))
        return "PASS", result
    if cmd == "compare":
        result = compare_case(Path(args.case), args.left, args.right)
        return "PASS", result
    if cmd == "references":
        result = references_case(Path(args.case), args.reference_manifest)
        return "PASS", result
    if cmd == "report":
        result = report_case(Path(args.case))
        recon = (result.get("reconciliation") or {}).get("status", "PASS")
        return ("PASS" if recon == "PASS" else "FAIL"), result
    if cmd == "verify":
        result = verify_case(Path(args.case))
        return str(result.get("status") or "FAIL"), result
    if cmd == "run":
        result = run_full(args.case_id, args.source, args.output)
        return str(result.get("global_status") or "FAIL"), result
    raise ValueError(f"unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
