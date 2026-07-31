"""CLI: python -m scripts.public_agency ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from scripts.public_agency import CAMPAIGN_ID
from scripts.public_agency.pipeline import git_sha, run_public_agency_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=f"{CAMPAIGN_ID} public-agency commercial cycle")
    p.add_argument(
        "--dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN"),
    )
    p.add_argument(
        "--out",
        default=os.environ.get(
            "CONFENGE_PUBLIC_AGENCY_OUT",
            "output/confenge-commercial/public-agencies",
        ),
    )
    p.add_argument("--profile", default="config/commercial/public_agency_profile.yaml")
    p.add_argument("--as-of", default=None)
    p.add_argument("--uf", action="append", default=None)
    p.add_argument("--max-contracts", type=int, default=100_000)
    p.add_argument("--max-leads", type=int, default=20)
    p.add_argument("--priority-population-max", type=int, default=None)
    p.add_argument("--mode", choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"], default=None)
    p.add_argument("--skip-kit", action="store_true")
    args = p.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = run_public_agency_pipeline(
        dsn=args.dsn,
        out_dir=args.out,
        profile_path=args.profile,
        as_of=as_of,
        ufs=args.uf,
        max_contracts=args.max_contracts,
        max_leads=args.max_leads,
        priority_population_max=args.priority_population_max,
        mode_filter=args.mode,
        skip_kit=args.skip_kit,
    )
    result.setdefault("git_sha", git_sha())
    print(
        f"[{CAMPAIGN_ID}] status={result.get('status')} reason={result.get('reason')} "
        f"leads={len(result.get('leads') or [])} run_id={result.get('run_id')} "
        f"sha={result.get('git_sha')}"
    )
    # compact metrics on stdout
    metrics = result.get("metrics") or {}
    print(
        json.dumps(
            {
                "evaluated": metrics.get("evaluated_agencies"),
                "publishable": metrics.get("publishable_agencies"),
                "top_n": metrics.get("top_n"),
                "ready_state": result.get("ready_state"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") in {"PASS", "BLOCKED"} else 1


if __name__ == "__main__":
    sys.exit(main())
