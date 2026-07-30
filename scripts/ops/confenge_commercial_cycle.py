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

    # Official RFB local mirror — fail closed when unavailable or incomplete.
    # Consumes active_official_registry_release only (no per-CNPJ network fetch).
    # Set CONFENGE_REQUIRE_OFFICIAL_REGISTRY=0 only for legacy fixture tests.
    require_official = os.environ.get("CONFENGE_REQUIRE_OFFICIAL_REGISTRY", "1") not in {
        "0",
        "false",
        "False",
        "no",
    }
    official_precheck: dict = {"ok": False, "reason": "not_evaluated"}
    interest_cnpjs: list[str] | None = None
    try:
        from scripts.company_registry.commercial_bridge import (
            fail_closed_commercial_precheck,
        )
        from scripts.company_registry.lookup import read_active_pointer

        interest_file = os.environ.get("CONFENGE_OFFICIAL_INTEREST_CNPJ_FILE")
        if interest_file and Path(interest_file).is_file():
            interest_cnpjs = [
                ln.strip()
                for ln in Path(interest_file).read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
        official_precheck = fail_closed_commercial_precheck(
            candidates=interest_cnpjs,
            top20=None,
            require_top20_full=False,
        )
        if require_official and not official_precheck.get("ok"):
            reason = str(
                official_precheck.get("reason") or "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
            )
            blocked = {
                "campaign_id": CAMPAIGN_ID,
                "status": "BLOCKED",
                "reason": reason,
                "official_registry_precheck": official_precheck,
                "active_official_registry_release": official_precheck.get(
                    "active_official_registry_release"
                ),
                "git_sha": git_sha(),
            }
            out_path = Path(args.out)
            out_path.mkdir(parents=True, exist_ok=True)
            (out_path / "cycle-manifest.json").write_text(
                json.dumps(blocked, indent=2, ensure_ascii=False, default=str) + "
",
                encoding="utf-8",
            )
            (out_path / "run-result.json").write_text(
                json.dumps(blocked, indent=2, ensure_ascii=False, default=str) + "
",
                encoding="utf-8",
            )
            print(f"[{CAMPAIGN_ID}] status=BLOCKED reason={reason}", file=sys.stderr)
            return 2
        if not require_official and not official_precheck.get("ok"):
            official_precheck = {
                "ok": False,
                "gate": "SKIPPED_LEGACY",
                "reason": "CONFENGE_REQUIRE_OFFICIAL_REGISTRY=0",
            }
        if (
            require_official
            and interest_cnpjs
            and os.environ.get("CONFENGE_PUBLISH_OFFICIAL_REGISTRY", "1")
            not in {"0", "false", "False"}
        ):
            from scripts.commercial_leads.dbutil import connect
            from scripts.company_registry.commercial_bridge import (
                publish_matches_to_supplier_registry,
            )

            conn = connect(dsn)
            try:
                pub = publish_matches_to_supplier_registry(
                    conn,
                    interest_cnpjs,
                    source="rfb_public_cadastral_via_opencnpj",
                )
            finally:
                conn.close()
            official_precheck["publish"] = {
                "upserted": pub.get("upserted"),
                "stats": pub.get("stats"),
            }
        official_precheck["active_pointer"] = read_active_pointer()
    except Exception as exc:  # noqa: BLE001
        blocked = {
            "campaign_id": CAMPAIGN_ID,
            "status": "BLOCKED",
            "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "error": f"{type(exc).__name__}:{exc}",
            "git_sha": git_sha(),
        }
        out_path = Path(args.out)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "cycle-manifest.json").write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False, default=str) + "
",
            encoding="utf-8",
        )
        print(f"[{CAMPAIGN_ID}] status=BLOCKED official_registry_error={exc}", file=sys.stderr)
        return 2

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
    result["official_registry_precheck"] = official_precheck
    result["active_official_registry_release"] = official_precheck.get(
        "active_official_registry_release"
    )

    if require_official:
        try:
            from scripts.company_registry.commercial_bridge import (
                fail_closed_commercial_precheck as _post_gate,
            )
            from scripts.company_registry.coverage import compute_coverage

            leads = list(result.get("leads") or [])
            top20_cnpjs = [
                str(x.get("cnpj14") or x.get("cnpj") or "")
                for x in leads[:20]
                if x.get("cnpj14") or x.get("cnpj")
            ]
            cand_for_cov = interest_cnpjs
            if not cand_for_cov:
                lm = result.get("load_meta") or {}
                cand_for_cov = list(lm.get("candidate_supplier_cnpjs") or [])
            post_official = _post_gate(
                candidates=cand_for_cov or None,
                top20=top20_cnpjs or None,
                require_top20_full=bool(top20_cnpjs),
            )
            cov = compute_coverage(
                cand_for_cov or top20_cnpjs,
                ranking_eligible=cand_for_cov or top20_cnpjs,
                top20=top20_cnpjs,
            )
            result["official_registry_coverage_post"] = cov
            result["official_registry_postcheck"] = post_official
            if not post_official.get("ok"):
                result["status"] = "BLOCKED"
                result["reason"] = str(
                    post_official.get("reason") or "BLOCKED_OFFICIAL_REGISTRY_POST_GATE"
                )
        except Exception as post_exc:  # noqa: BLE001
            result["status"] = "BLOCKED"
            result["reason"] = "BLOCKED_OFFICIAL_REGISTRY_POST_GATE"
            result["official_registry_postcheck"] = {
                "ok": False,
                "error": f"{type(post_exc).__name__}:{post_exc}",
            }

    status = result.get("status")
    print(
        f"[{CAMPAIGN_ID}] status={status} leads={len(result.get('leads') or [])} "
        f"run_id={result.get('run_id')} sha={result.get('git_sha')} "
        f"official_release={result.get('active_official_registry_release')}"
    )
    out_manifest = Path(args.out) / "cycle-manifest.json"
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
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
                "active_official_registry_release": result.get(
                    "active_official_registry_release"
                ),
                "official_registry_precheck": official_precheck,
                "official_registry_postcheck": result.get("official_registry_postcheck"),
                "official_registry_coverage_post": result.get(
                    "official_registry_coverage_post"
                ),
                "reason": result.get("reason"),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "
",
        encoding="utf-8",
    )
    run_result_path = Path(args.out) / "run-result.json"
    run_result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "
",
        encoding="utf-8",
    )
    if status == "PASS":
        return 0
    if str(status).startswith("BLOCKED"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
