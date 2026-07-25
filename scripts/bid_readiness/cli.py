"""CLI entry for bid readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.bid_readiness.isolation import IsolationError, assert_isolation
from scripts.bid_readiness.pipeline import create_case, revalidate_case, run_pipeline, verify_case


def _case_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "case", None):
        return Path(str(args.case))
    if getattr(args, "output", None):
        return Path(str(args.output))
    root: Path | None = Path(str(args.case_root)) if getattr(args, "case_root", None) else None
    if root is None:
        import os

        default_case_root = "/tmp/extra-cli-bid-readiness-01/cases"  # noqa: S108  # nosec B108
        root = Path(os.environ.get("BID_CASE_ROOT", default_case_root))
    return root / str(args.case_id)


def cmd_create(args: argparse.Namespace) -> int:
    case_dir = _case_dir(args)
    create_case(case_dir, case_id=args.case_id, requirements_path=Path(args.requirements))
    print(json.dumps({"ok": True, "case": str(case_dir)}, ensure_ascii=False))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        iso = assert_isolation()
        isolation_ok = True
    except IsolationError as exc:
        if args.allow_non_isolated:
            iso = {"ok": False, "error": str(exc)}
            isolation_ok = False
        else:
            print(f"ISOLATION_ERROR: {exc}", file=sys.stderr)
            return 2

    case_dir = Path(args.output) if args.output else _case_dir(args)
    entity = None
    if args.entity:
        entity = json.loads(Path(args.entity).read_text(encoding="utf-8"))

    result = run_pipeline(
        case_id=args.case_id,
        requirements_path=Path(args.requirements),
        documents_source=Path(args.documents),
        reference_date=args.reference_date,
        output_dir=case_dir,
        entity=entity,
        operational=bool(args.operational),
        isolation_ok=isolation_ok,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "case": str(case_dir),
                "system_status": result["system_status"],
                "package_status": result["package_status"],
                "final_status": result["final_status"],
                "summary": result["summary"],
                "isolation": iso.get("ok"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = verify_case(Path(args.case))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_inventory(args: argparse.Namespace) -> int:
    inv = json.loads((Path(args.case) / "documents" / "inventory.json").read_text(encoding="utf-8"))
    print(json.dumps(inv, ensure_ascii=False, indent=2))
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    matrix = json.loads((Path(args.case) / "matrices" / "requirement-document.json").read_text(encoding="utf-8"))
    print(json.dumps(matrix, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    summary = (Path(args.case) / "reports" / "executive-summary.md").read_text(encoding="utf-8")
    print(summary)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    # Re-run full pipeline is heavy; for incremental, re-invoke run if requirements exist
    case = Path(args.case)
    req = case / "requirements.json"
    if not req.is_file():
        print("case missing requirements.json — run create first", file=sys.stderr)
        return 1
    manifest = json.loads((case / "case-manifest.json").read_text(encoding="utf-8"))
    # Write a temp requirements file
    tmp_req = case / "_requirements_export.json"
    tmp_req.write_text(req.read_text(encoding="utf-8"), encoding="utf-8")
    # requirements loader expects list or {requirements:[]}
    result = run_pipeline(
        case_id=manifest["case_id"],
        requirements_path=tmp_req,
        documents_source=Path(args.documents),
        reference_date=args.reference_date or manifest.get("reference_date") or "2026-07-01",
        output_dir=case,
        entity=manifest.get("entity"),
        operational=False,
        isolation_ok=True,
    )
    print(json.dumps({"ok": True, "summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    case = Path(args.case)
    if not case.is_dir():
        print(f"case not found: {case}", file=sys.stderr)
        return 1
    # Prefer explicit --reference-date; fall back to case manifest
    ref = args.reference_date
    if not ref:
        manifest_path = case / "case-manifest.json"
        if manifest_path.is_file():
            ref = json.loads(manifest_path.read_text(encoding="utf-8")).get("reference_date")
    if not ref:
        print("reference-date required (flag or case-manifest.json)", file=sys.stderr)
        return 1
    result = revalidate_case(case, reference_date=ref)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_declarations(args: argparse.Namespace) -> int:
    path = Path(args.case) / "matrices" / "declarations.json"
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    recon = json.loads((Path(args.case) / "package" / "package-reconciliation.json").read_text(encoding="utf-8"))
    print(json.dumps(recon, ensure_ascii=False, indent=2))
    return 0 if recon.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m scripts.bid_readiness")
    sub = p.add_subparsers(dest="command", required=True)

    def add_case_id(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--case-id", required=False)
        sp.add_argument("--case", required=False)
        sp.add_argument("--output", required=False)
        sp.add_argument("--case-root", required=False)

    c = sub.add_parser("create")
    c.add_argument("--case-id", required=True)
    c.add_argument("--requirements", required=True)
    c.add_argument("--output", required=False)
    c.add_argument("--case-root", required=False)
    c.set_defaults(func=cmd_create)

    r = sub.add_parser("run")
    r.add_argument("--case-id", required=True)
    r.add_argument("--requirements", required=True)
    r.add_argument("--documents", required=True)
    r.add_argument("--reference-date", required=True)
    r.add_argument("--output", required=False)
    r.add_argument("--case-root", required=False)
    r.add_argument("--entity", required=False)
    r.add_argument("--operational", action="store_true")
    r.add_argument("--allow-non-isolated", action="store_true")
    r.set_defaults(func=cmd_run)

    for name, fn in [
        ("verify", cmd_verify),
        ("inventory", cmd_inventory),
        ("match", cmd_match),
        ("report", cmd_report),
        ("validate", cmd_validate),
        ("declarations", cmd_declarations),
        ("assemble", cmd_assemble),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--case", required=True)
        if name == "validate":
            sp.add_argument("--reference-date", required=False)
        sp.set_defaults(func=fn)

    ing = sub.add_parser("ingest")
    ing.add_argument("--case", required=True)
    ing.add_argument("--documents", required=True)
    ing.add_argument("--reference-date", required=False)
    ing.set_defaults(func=cmd_ingest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
