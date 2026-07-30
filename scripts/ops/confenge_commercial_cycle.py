#!/usr/bin/env python3
"""Canonical CONFENGE commercial cycle entry point.

Env:
  CONFENGE_COMMERCIAL_STATE_DSN  — state/write DB (isolated campaign port)
  CONFENGE_COMMERCIAL_SOURCE_DSN — optional read-only source (defaults to STATE)
  CONFENGE_COMMERCIAL_SNAPSHOT   — path to authenticated snapshot manifest
  CONFENGE_COMMERCIAL_PROFILE    — profile path (default config/commercial_profiles/confenge.yaml)
  CONFENGE_COMMERCIAL_OUT        — output directory
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
# Prefer activation campaign out dir; fall back handled if parent missing at write time.


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=f"{CAMPAIGN_ID} canonical commercial cycle")
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
    p.add_argument("--max-contracts", type=int, default=None)
    p.add_argument(
        "--population-mode",
        choices=["FULL_POPULATION", "BOUNDED_SAMPLE"],
        default=os.environ.get(
            "CONFENGE_POPULATION_MODE",
            # Activation campaign default: full eligible population (not 60k sample theater)
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

    if not args.dsn:
        print(
            "FAIL: missing STATE DSN. Set CONFENGE_COMMERCIAL_STATE_DSN "
            "or pass --dsn (isolated local port, never production).",
            file=sys.stderr,
        )
        return 1
    if not args.snapshot_manifest:
        print(
            "FAIL: missing snapshot manifest. Set CONFENGE_COMMERCIAL_SNAPSHOT "
            "or pass --snapshot-manifest with authenticated real snapshot.",
            file=sys.stderr,
        )
        return 1

    dsn = args.dsn
    source = args.source_dsn or dsn
    if source == dsn and args.source_state_mode == "SOURCE_STATE_SEPARATED":
        print(
            "FAIL: source==state but SOURCE_STATE_SEPARATED claimed. "
            "Use RESTORED_SNAPSHOT_SINGLE_DB.",
            file=sys.stderr,
        )
        return 1

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
    status = result.get("status")
    print(
        f"[{CAMPAIGN_ID}] status={status} leads={len(result.get('leads') or [])} "
        f"run_id={result.get('run_id')} sha={result.get('git_sha')}"
    )
    out_manifest = Path(args.out) / "cycle-manifest.json"
    out_manifest.write_text(
        json.dumps(
            {
                "campaign_id": CAMPAIGN_ID,
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
        return 0
    if str(status).startswith("BLOCKED"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
