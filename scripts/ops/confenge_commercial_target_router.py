#!/usr/bin/env python3
"""Multi-target CONFENGE commercial cycle router (suppliers | public-agencies | all).

This module is intentionally OUTSIDE the CONFENGE-COMMERCIAL-READY-01 freeze
surface. The frozen supplier entrypoint remains:

  python -m scripts.ops.confenge_commercial_cycle

Makefile ``confenge-commercial-cycle`` with TARGET= routes here so that
public-agency work does not mutate protected freeze digests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.commercial_leads.pipeline import git_sha

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PAG_OUT = _ROOT / "output/confenge-commercial/public-agencies"
_DEFAULT_PAG_PROFILE = _ROOT / "config/commercial/public_agency_profile.yaml"
_DEFAULT_SUPPLIER_OUT = (
    _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run"
)
_DEFAULT_SUPPLIER_PROFILE = _ROOT / "config/commercial_profiles/confenge.yaml"


def _registry_required() -> bool:
    """Official registry fail-closed is on by default (same policy as registry wrapper)."""
    return os.environ.get("CONFENGE_REQUIRE_OFFICIAL_REGISTRY", "1") not in {
        "0",
        "false",
        "False",
        "no",
    }


def _run_suppliers(argv_tail: list[str]) -> tuple[int, dict]:
    """Run supplier modality via official-registry wrapper when required.

    Architecture:
    - frozen ``confenge_commercial_cycle`` stays suppliers-only (no --target)
    - ``confenge_registry_commercial_cycle`` is the external precheck/publish wrapper
    - this router must not silently bypass the registry when fail-closed is on
    """
    if _registry_required():
        from scripts.ops import confenge_registry_commercial_cycle as registry_cycle

        code = int(registry_cycle.main(argv_tail))
        status = "PASS" if code == 0 else ("BLOCKED" if code == 2 else "FAIL")
        return code, {
            "status": status,
            "exit_code": code,
            "modality": "suppliers",
            "entry": "confenge_registry_commercial_cycle",
            "official_registry_required": True,
        }

    from scripts.ops import confenge_commercial_cycle as supplier_cycle

    code = int(supplier_cycle.main(argv_tail))
    status = "PASS" if code == 0 else ("BLOCKED" if code == 2 else "FAIL")
    return code, {
        "status": status,
        "exit_code": code,
        "modality": "suppliers",
        "entry": "confenge_commercial_cycle",
        "official_registry_required": False,
    }


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
    p = argparse.ArgumentParser(
        description="CONFENGE commercial cycle multi-target router (outside freeze surface)"
    )
    p.add_argument(
        "--target",
        choices=["suppliers", "public-agencies", "all"],
        default=os.environ.get("CONFENGE_COMMERCIAL_TARGET", "suppliers"),
    )
    p.add_argument(
        "--dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN"),
    )
    p.add_argument("--source-dsn", default=os.environ.get("CONFENGE_COMMERCIAL_SOURCE_DSN"))
    p.add_argument(
        "--profile",
        default=os.environ.get("CONFENGE_COMMERCIAL_PROFILE", str(_DEFAULT_SUPPLIER_PROFILE)),
    )
    p.add_argument(
        "--snapshot-manifest",
        default=os.environ.get("CONFENGE_COMMERCIAL_SNAPSHOT"),
    )
    p.add_argument(
        "--out",
        default=os.environ.get("CONFENGE_COMMERCIAL_OUT", str(_DEFAULT_SUPPLIER_OUT)),
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
    p.add_argument("--uf", action="append", default=None)
    p.add_argument(
        "--public-agency-mode",
        choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"],
        default=None,
    )
    p.add_argument("--max-contracts", type=int, default=None)
    p.add_argument(
        "--population-mode",
        choices=["FULL_POPULATION", "BOUNDED_SAMPLE"],
        default=os.environ.get("CONFENGE_POPULATION_MODE", "FULL_POPULATION"),
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
    combined: dict = {"target": args.target, "results": {}, "router": "confenge_commercial_target_router"}

    if args.target in {"suppliers", "all"}:
        supplier_argv: list[str] = []
        if args.dsn:
            supplier_argv.extend(["--dsn", args.dsn])
        if args.source_dsn:
            supplier_argv.extend(["--source-dsn", args.source_dsn])
        if args.profile:
            supplier_argv.extend(["--profile", args.profile])
        if args.snapshot_manifest:
            supplier_argv.extend(["--snapshot-manifest", args.snapshot_manifest])
        if args.out:
            supplier_argv.extend(["--out", args.out])
        if args.max_contracts is not None:
            supplier_argv.extend(["--max-contracts", str(args.max_contracts)])
        if args.population_mode:
            supplier_argv.extend(["--population-mode", args.population_mode])
        if args.source_state_mode:
            supplier_argv.extend(["--source-state-mode", args.source_state_mode])
        if args.run_mode:
            supplier_argv.extend(["--run-mode", args.run_mode])
        if args.skip_migrations:
            supplier_argv.append("--skip-migrations")
        if args.skip_persist:
            supplier_argv.append("--skip-persist")
        if args.skip_hash_verify:
            supplier_argv.append("--skip-hash-verify")
        if args.as_of:
            supplier_argv.extend(["--as-of", args.as_of])
        code, res = _run_suppliers(supplier_argv)
        exits.append(code)
        combined["results"]["suppliers"] = res

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

    # Per-modality status is preserved; never average or promote one green modality.
    combined["modality_exit_codes"] = {
        k: (v.get("exit_code") if isinstance(v, dict) else None)
        for k, v in combined["results"].items()
    }
    combined["any_fail"] = any(c == 1 for c in exits)
    combined["any_blocked"] = any(c == 2 for c in exits)
    combined["all_pass"] = bool(exits) and all(c == 0 for c in exits)

    if args.target == "all":
        # Distinct combined summary path; individual modality artifacts stay separate.
        base_out = Path(args.out)
        pag_out = Path(
            args.public_agency_out
            or os.environ.get("CONFENGE_PUBLIC_AGENCY_OUT", str(_DEFAULT_PAG_OUT))
        )
        combined["artifact_roots"] = {
            "suppliers": str(base_out),
            "public_agencies": str(pag_out),
        }
        combined["git_sha"] = git_sha()
        combined["summary_note"] = (
            "Combined summary only; modality statuses are independent. "
            "One PASS does not approve the other."
        )
        for name, root in (
            ("combined-cycle-manifest.json", base_out),
            ("combined-cycle-manifest.json", pag_out),
        ):
            root.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(
                json.dumps(combined, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )

    if not exits:
        return 1
    if any(c == 1 for c in exits):
        return 1
    if any(c == 2 for c in exits):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
