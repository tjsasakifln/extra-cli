"""CLI: python -m scripts.production_readiness <command>"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.production_readiness.evidence import evidence_root, write_baseline, write_environment, write_json
from scripts.production_readiness.full_scale import run_full_scale_proof
from scripts.production_readiness.official_reference import (
    build_demo_official_snapshot,
    compare_budget_to_official,
)


def cmd_baseline(_args: argparse.Namespace) -> int:
    root = evidence_root()
    write_baseline(root)
    write_environment(root)
    print(json.dumps({"evidence_root": str(root)}, ensure_ascii=False))
    return 0


def cmd_full_scale(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else Path("artifacts/production-readiness/full-scale")
    result = run_full_scale_proof(
        out_root=out,
        dsn=args.dsn,
        synthetic_n=args.synthetic_n,
        dual_run=not args.no_dual,
        page_size=args.page_size,
    )
    print(
        json.dumps(
            {
                "source": result.get("source"),
                "expected_total": result.get("expected_total"),
                "run1_accepted": (result.get("run1") or {}).get("accepted"),
                "publication_allowed": (result.get("run1") or {}).get("publication_allowed"),
                "compare": result.get("compare"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if (result.get("run1") or {}).get("publication_allowed") else 2


def cmd_official_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    man = build_demo_official_snapshot(out)
    budget = [
        {"item_id": "1", "code": "88389", "description": "Concreto fck 25 MPa", "unit": "m3"},
        {"item_id": "2", "code": "74109/001", "description": "Servente de obras", "unit": "h"},
        {"item_id": "3", "code": "NOREF", "description": "Item sem referencia", "unit": "un"},
        {"item_id": "4", "code": "99901", "description": "Tubo PVC 100mm", "unit": "kg"},  # unit mismatch
        {"item_id": "5", "code": "88389", "description": "Concreto", "unit": "m3"},
    ]
    report = compare_budget_to_official(
        budget,
        out / "manifest.json",
        budget_competence="2026-05",  # competence mismatch demo
        budget_locality="SC",
        allow_demo_structure=True,
    )
    # second pass without competence clash for unit/exact/missing
    report2 = compare_budget_to_official(
        budget,
        out / "manifest.json",
        budget_competence="2026-06",
        budget_locality="SC",
        allow_demo_structure=True,
    )
    payload = {
        "demo_manifest_claim_level": man.get("claim_level"),
        "with_competence_mismatch": report["counts"],
        "aligned_competence": report2["counts"],
        "sample_statuses": [m["status"] for m in report2["matches"]],
        "non_claim": "NOT live official SINAPI acquisition",
    }
    write_json(out / "sinapi-sicro-comparison.json", payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="production_readiness")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("baseline")
    b.set_defaults(func=cmd_baseline)

    f = sub.add_parser("full-scale")
    f.add_argument("--out", default=None)
    f.add_argument("--dsn", default=None)
    f.add_argument("--synthetic-n", type=int, default=None)
    f.add_argument("--no-dual", action="store_true")
    f.add_argument("--page-size", type=int, default=5000)
    f.set_defaults(func=cmd_full_scale)

    o = sub.add_parser("official-demo")
    o.add_argument("--out", default="artifacts/production-readiness/official-demo")
    o.set_defaults(func=cmd_official_demo)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
