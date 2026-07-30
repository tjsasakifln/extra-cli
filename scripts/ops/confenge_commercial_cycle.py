#!/usr/bin/env python3
"""Canonical CONFENGE commercial cycle entry point.

Env:
  CONFENGE_COMMERCIAL_STATE_DSN  — state/write DB (isolated campaign port)
  CONFENGE_COMMERCIAL_SOURCE_DSN — optional read-only source (defaults to STATE)
  CONFENGE_COMMERCIAL_SNAPSHOT   — path to authenticated snapshot manifest
  CONFENGE_COMMERCIAL_PROFILE    — profile path (default config/commercial_profiles/confenge.yaml)
  CONFENGE_COMMERCIAL_OUT        — output directory
  CONFENGE_COMMERCIAL_TARGET     — suppliers | public-agencies | all (default suppliers)
  CONFENGE_PUBLIC_AGENCY_OUT     — output dir for public-agency modality
  LOCAL_DATALAKE_DSN             — fallback DSN (public-agency can use buyer-side tables)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.commercial_leads import CAMPAIGN_ID
from scripts.commercial_leads.pipeline import git_sha, run_pipeline

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROFILE = _ROOT / "config/commercial_profiles/confenge.yaml"
_DEFAULT_OUT = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run"
_DEFAULT_PAG_OUT = _ROOT / "output/confenge-commercial/public-agencies"
_DEFAULT_PAG_PROFILE = _ROOT / "config/commercial/public_agency_profile.yaml"


def _run_suppliers(args: argparse.Namespace) -> tuple[int, dict]:
    if not args.dsn:
        print(
            "FAIL: missing STATE DSN. Set CONFENGE_COMMERCIAL_STATE_DSN "
            "or pass --dsn (isolated local port, never production).",
            file=sys.stderr,
        )
        return 1, {"status": "FAIL", "reason": "missing_dsn"}
    if not args.snapshot_manifest:
        print(
            "FAIL: missing snapshot manifest. Set CONFENGE_COMMERCIAL_SNAPSHOT "
            "or pass --snapshot-manifest with authenticated real snapshot.",
            file=sys.stderr,
        )
        return 1, {"status": "FAIL", "reason": "missing_snapshot"}

    dsn = args.dsn
    source = args.source_dsn or dsn
    if source == dsn and args.source_state_mode == "SOURCE_STATE_SEPARATED":
        print(
            "FAIL: source==state but SOURCE_STATE_SEPARATED claimed. "
            "Use RESTORED_SNAPSHOT_SINGLE_DB.",
            file=sys.stderr,
        )
        return 1, {"status": "FAIL", "reason": "source_state_mode"}

    from datetime import date

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = run_pipeline(
        dsn=dsn,
        profile_path=args.profile,
        snapshot_manifest=args.snapshot_manifest,
        out_dir=args.out,
        max_contracts=args.max_contracts,
        as_of=as_of,
        skip_migrations=args.skip_migrations,
        skip_persist=args.skip_persist,
        verify_snapshot_hash=not args.skip_hash_verify,
        source_dsn=source,
        state_dsn=dsn,
        population_mode=args.population_mode,
        source_state_mode=args.source_state_mode,
        run_mode=args.run_mode,
    )
    result.setdefault("source_dsn_env_set", bool(args.source_dsn))
    result.setdefault("git_sha", git_sha())
    result.setdefault("target", "suppliers")
    status = result.get("status")
    print(
        f"[{CAMPAIGN_ID}] target=suppliers status={status} "
        f"leads={len(result.get('leads') or [])} "
        f"run_id={result.get('run_id')} sha={result.get('git_sha')}"
    )
    out_manifest = Path(args.out) / "cycle-manifest.json"
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.write_text(
        json.dumps(
            {
                "campaign_id": CAMPAIGN_ID,
                "target": "suppliers",
                "status": status,
                "run_id": result.get("run_id"),
                "git_sha": result.get("git_sha"),
                "profile_hash": result.get("profile_hash"),
                "catalog_hash": result.get("catalog_hash"),
                "snapshot_hash": result.get("snapshot_hash"),
                "metrics": result.get("metrics"),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    if status == "PASS":
        return 0, result
    if str(status).startswith("BLOCKED"):
        return 2, result
    return 1, result


def _run_public_agencies(args: argparse.Namespace) -> tuple[int, dict]:
    from datetime import date

    from scripts.public_agency import CAMPAIGN_ID as PAG_ID
    from scripts.public_agency.pipeline import run_public_agency_pipeline

    dsn = (
        args.dsn
        or os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN")
    )
    if not dsn:
        print(
            "FAIL: public-agencies target requires DSN "
            "(CONFENGE_COMMERCIAL_STATE_DSN or LOCAL_DATALAKE_DSN).",
            file=sys.stderr,
        )
        return 1, {"status": "FAIL", "reason": "missing_dsn", "target": "public-agencies"}

    pag_out = args.public_agency_out or os.environ.get(
        "CONFENGE_PUBLIC_AGENCY_OUT", str(_DEFAULT_PAG_OUT)
    )
    pag_profile = args.public_agency_profile or str(_DEFAULT_PAG_PROFILE)
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    ufs = args.uf or None

    result = run_public_agency_pipeline(
        dsn=dsn,
        out_dir=pag_out,
        profile_path=pag_profile,
        as_of=as_of,
        ufs=ufs,
        max_contracts=args.max_contracts or 100_000,
        max_leads=args.max_public_agency_leads,
        priority_population_max=args.priority_population_max,
        mode_filter=args.public_agency_mode,
    )
    result.setdefault("git_sha", git_sha())
    status = result.get("status")
    print(
        f"[{PAG_ID}] target=public-agencies status={status} reason={result.get('reason')} "
        f"leads={len(result.get('leads') or [])} run_id={result.get('run_id')} "
        f"sha={result.get('git_sha')}"
    )
    if status == "PASS":
        return 0, result
    if str(status).startswith("BLOCKED"):
        return 2, result
    return 1, result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=f"{CAMPAIGN_ID} canonical commercial cycle")
    p.add_argument(
        "--target",
        choices=["suppliers", "public-agencies", "all"],
        default=os.environ.get("CONFENGE_COMMERCIAL_TARGET", "suppliers"),
        help="Commercial modality: suppliers (default), public-agencies, or all",
    )
    p.add_argument(
        "--dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN"),
        help="State DSN (isolated). Env: CONFENGE_COMMERCIAL_STATE_DSN",
    )
    p.add_argument(
        "--source-dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_SOURCE_DSN"),
        help="Optional source DSN (read path). Defaults to --dsn.",
    )
    p.add_argument(
        "--profile",
        default=os.environ.get("CONFENGE_COMMERCIAL_PROFILE", str(_DEFAULT_PROFILE)),
    )
    p.add_argument(
        "--snapshot-manifest",
        default=os.environ.get("CONFENGE_COMMERCIAL_SNAPSHOT"),
        required=False,
    )
    p.add_argument(
        "--out",
        default=os.environ.get("CONFENGE_COMMERCIAL_OUT", str(_DEFAULT_OUT)),
    )
    p.add_argument(
        "--public-agency-out",
        default=os.environ.get("CONFENGE_PUBLIC_AGENCY_OUT", str(_DEFAULT_PAG_OUT)),
    )
    p.add_argument(
        "--public-agency-profile",
        default=os.environ.get("CONFENGE_PUBLIC_AGENCY_PROFILE", str(_DEFAULT_PAG_PROFILE)),
    )
    p.add_argument("--max-public-agency-leads", type=int, default=20)
    p.add_argument("--priority-population-max", type=int, default=None)
    p.add_argument("--uf", action="append", default=None, help="UF filter for public-agencies")
    p.add_argument(
        "--public-agency-mode",
        choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"],
        default=None,
    )
    p.add_argument("--max-contracts", type=int, default=None)
    p.add_argument(
        "--population-mode",
        choices=["FULL_POPULATION", "BOUNDED_SAMPLE"],
        default=os.environ.get(
            "CONFENGE_POPULATION_MODE",
            "FULL_POPULATION",
        ),
    )
    p.add_argument(
        "--source-state-mode",
        choices=["SOURCE_STATE_SEPARATED", "RESTORED_SNAPSHOT_SINGLE_DB"],
        default=os.environ.get("CONFENGE_SOURCE_STATE_MODE", "RESTORED_SNAPSHOT_SINGLE_DB"),
    )
    p.add_argument(
        "--run-mode",
        choices=["RC", "TEST", "DRY_RUN", "EXPERIMENTAL_SAMPLE"],
        default=os.environ.get("CONFENGE_RUN_MODE", "RC"),
    )
    p.add_argument("--skip-migrations", action="store_true")
    p.add_argument("--skip-persist", action="store_true")
    p.add_argument("--skip-hash-verify", action="store_true")
    p.add_argument("--as-of", default=None)
    args = p.parse_args(argv)

    exits: list[int] = []
    combined: dict = {"target": args.target, "results": {}}

    if args.target in {"suppliers", "all"}:
        code, res = _run_suppliers(args)
        exits.append(code)
        combined["results"]["suppliers"] = {
            "status": res.get("status"),
            "run_id": res.get("run_id"),
            "leads": len(res.get("leads") or []),
        }

    if args.target in {"public-agencies", "all"}:
        code, res = _run_public_agencies(args)
        exits.append(code)
        combined["results"]["public-agencies"] = {
            "status": res.get("status"),
            "reason": res.get("reason"),
            "run_id": res.get("run_id"),
            "leads": len(res.get("leads") or []),
            "ready_state": res.get("ready_state"),
        }

    # Combined manifest when target=all
    if args.target == "all":
        manifest_path = Path(args.out) / "combined-cycle-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        combined["git_sha"] = git_sha()
        manifest_path.write_text(
            json.dumps(combined, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    if not exits:
        return 1
    # Prefer worst non-zero: FAIL(1) over BLOCKED(2)? Keep max severity: any 1 wins, else 2, else 0
    if any(c == 1 for c in exits):
        return 1
    if any(c == 2 for c in exits):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
