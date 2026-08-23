"""CLI: python -m scripts.confenge_outreach_pipeline run ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.confenge_outreach_pipeline import MODULE_VERSION, PIPELINE_ID
from scripts.confenge_outreach_pipeline.pipeline import PipelineConfig, run_pipeline

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_outreach_pipeline",
        description=(
            "Canonical CONFENGE outreach pipeline: "
            "universe → activation planner (hot set) → account intelligence → "
            "contact resolution → confenge.outreach.v1 feed. "
            "Smoke mode can force diverse sample via --force-sample-mode."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
# Production: full reservoir + activation-driven hot set:
python -m scripts.confenge_outreach_pipeline run \\
  --dsn "$LOCAL_DATALAKE_DSN" \\
  --out output/confenge_outreach \\
  --as-of 2026-08-07 \\
  --use-activation-planner \\
  --limit-downstream 200

# Resume after interrupt (checkpoint under --out):
python -m scripts.confenge_outreach_pipeline run \\
  --dsn "$LOCAL_DATALAKE_DSN" \\
  --out output/confenge_outreach \\
  --skip-universe \\
  --limit-downstream 200

# Smoke / diagnostic diverse sample (NOT commercial strategy):
python -m scripts.confenge_outreach_pipeline run \\
  --csv tests/fixtures/confenge_universe/contracts_sample.csv \\
  --out /tmp/confenge_outreach_smoke \\
  --as-of 2026-08-01 \\
  --force-sample-mode \\
  --limit-downstream 20 \\
  --skip-contacts

IMPORTANT: --limit-downstream bounds only this round's expensive batch
(intel/contacts/feed). Universe discovery is independent and full-scale
when --max-rows is omitted. Round N+1 advances the durable activation cursor.
""".strip(),
    )
    p.add_argument("--version", action="version", version=f"{PIPELINE_ID} {MODULE_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Execute the full pipeline")
    run.add_argument("--out", required=True, help="Output root directory")
    run.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN for national datalake (or set LOCAL_DATALAKE_DSN)",
    )
    run.add_argument(
        "--csv",
        default=None,
        help="Offline CSV of contracts (fixture / diagnostic)",
    )
    run.add_argument(
        "--as-of",
        default=None,
        help="Reference date YYYY-MM-DD (default: today)",
    )
    run.add_argument(
        "--limit-downstream",
        type=int,
        default=200,
        help=("Max accounts for intelligence + contacts + feed (default 200). Does NOT limit universe discovery."),
    )
    run.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Worker concurrency for intelligence/contacts (default 4)",
    )
    run.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="DIAGNOSTIC only: cap universe source rows (marks run as sampled)",
    )
    run.add_argument("--dnc", default=None, help="Optional DNC file (one CNPJ per line)")
    run.add_argument(
        "--skip-universe",
        action="store_true",
        help="Reuse existing 01_universe artifacts under --out",
    )
    run.add_argument(
        "--skip-contacts",
        action="store_true",
        help="Skip contact resolution (empty contacts in feed)",
    )
    run.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow optional network adapters in contact resolution",
    )
    run.add_argument(
        "--enable-web-search",
        action="store_true",
        help="Enable optional web-search contact adapter",
    )
    run.add_argument(
        "--contact-fixtures-dir",
        type=Path,
        default=None,
        help="Optional fixtures dir for contact adapters",
    )
    run.add_argument(
        "--feed-limit",
        type=int,
        default=None,
        help="Optional hard cap on leads written to feed chunks",
    )
    run.add_argument(
        "--no-dnc-in-sample",
        action="store_true",
        help="Exclude DNC accounts from the diverse downstream sample",
    )
    run.add_argument(
        "--use-activation-planner",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use activation planner for hot set (default: on). Disable with --no-use-activation-planner.",
    )
    run.add_argument(
        "--force-sample-mode",
        action="store_true",
        help="SMOKE only: use diverse sample instead of activation hot set",
    )
    run.add_argument(
        "--activation-policy",
        default=None,
        help="Path to confenge_activation_policy.yaml",
    )
    run.add_argument(
        "--activation-capacity",
        type=int,
        default=None,
        help="Override hot-set capacity (default: policy capacity planning)",
    )
    run.add_argument(
        "--prior-activation",
        default=None,
        help="Prior activation-projections.jsonl for incremental deltas",
    )
    run.add_argument(
        "--commercial-memory",
        default=None,
        help="JSONL overlay of commercial outcomes (DNC/NOT_NOW/BOUNCE/REPLIED) by cnpj14",
    )
    run.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore pipeline-checkpoint.json and restart stage tracking",
    )
    run.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress logging",
    )
    return p


def cmd_run(args: argparse.Namespace) -> int:
    # An explicit CSV is an offline source and must not silently inherit a live
    # target-fit store from the operator environment. Combining CSV + store is
    # still available, but only through an explicit --dsn.
    dsn = args.dsn or (None if args.csv else os.environ.get("LOCAL_DATALAKE_DSN"))
    if not dsn and not args.csv and not args.skip_universe:
        sys.stderr.write("error: provide --dsn / LOCAL_DATALAKE_DSN, --csv, or --skip-universe\n")
        return EXIT_USAGE
    if args.limit_downstream < 1:
        sys.stderr.write("error: --limit-downstream must be >= 1\n")
        return EXIT_USAGE

    authoritative_source_freshness = None
    if dsn:
        from scripts.ops.pncp_contract_freshness import build_contract, collect_snapshot

        contract = build_contract(collect_snapshot(live=True, dsn=dsn))
        if contract.get("status") != "FRESH":
            reasons = ",".join(contract.get("reason_codes") or []) or "none"
            sys.stderr.write(
                f"error: authoritative PNCP source is not FRESH; status={contract.get('status')} reasons={reasons}\n"
            )
            return EXIT_FAIL
        as_of = datetime.fromisoformat(str(contract["as_of"]).replace("Z", "+00:00"))
        target_hours = float((contract.get("slo") or {}).get("desired_operational_target_hours") or 6.0)
        lag_hours = float(contract.get("current_lag_hours") or 0.0)
        expires_at = as_of + timedelta(hours=max(0.0, target_hours - lag_hours))
        authoritative_source_freshness = {
            key: contract.get(key)
            for key in (
                "contract_version",
                "status",
                "reason_codes",
                "as_of",
                "deployed_sha",
                "policy_version",
                "run_id",
                "source_window",
                "latest_successful_closed_window",
                "current_lag_hours",
                "pages_expected",
                "pages_fetched",
            )
        }
        authoritative_source_freshness["expires_at"] = expires_at.isoformat().replace("+00:00", "Z")

    as_of: date | None = None
    if args.as_of:
        try:
            as_of = date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(f"error: invalid --as-of {args.as_of!r}\n")
            return EXIT_USAGE

    cfg = PipelineConfig(
        out_dir=Path(args.out),
        dsn=dsn,
        csv_path=args.csv,
        as_of=as_of,
        limit_downstream=args.limit_downstream,
        max_workers=max(1, args.max_workers),
        max_rows=args.max_rows,
        dnc_path=args.dnc,
        skip_universe=args.skip_universe,
        skip_contacts=args.skip_contacts,
        allow_network=args.allow_network,
        enable_web_search=args.enable_web_search,
        contact_fixtures_dir=args.contact_fixtures_dir,
        include_dnc_in_sample=not args.no_dnc_in_sample,
        feed_limit=args.feed_limit,
        use_activation_planner=bool(args.use_activation_planner),
        activation_policy_path=args.activation_policy,
        activation_capacity=args.activation_capacity,
        prior_activation_path=args.prior_activation,
        force_sample_mode=bool(args.force_sample_mode),
        commercial_memory_path=args.commercial_memory,
        resume=not bool(args.no_resume),
        progress=not bool(args.quiet),
        authoritative_source_freshness=authoritative_source_freshness,
    )
    result = run_pipeline(cfg)
    payload = {
        "ok": result.ok,
        "out_dir": result.out_dir,
        "manifest_path": result.manifest_path,
        "errors": result.errors,
        "stages_summary": {
            "universe_rows": result.stages.get("universe_row_count"),
            "reservoir_count": result.stages.get("reservoir_count"),
            "sample_count": (result.stages.get("sample") or {}).get("count"),
            "sample_mode": (result.stages.get("sample") or {}).get("mode"),
            "activation_counts": result.stages.get("activation_counts"),
            "hot_set_count": result.stages.get("hot_set_count"),
            "expensive_enrichment_count": result.stages.get("expensive_enrichment_count"),
            "feed_count": result.stages.get("feed_count"),
            "policy_version": result.stages.get("policy_version"),
            "source_watermark": result.stages.get("source_watermark"),
            "use_activation_planner": result.stages.get("use_activation_planner"),
            "intel_count": (result.stages.get("account_intelligence") or {}).get("count"),
            "service_distribution": (result.stages.get("account_intelligence") or {}).get("service_distribution"),
            "contact_metrics": (result.stages.get("contacts") or {}).get("metrics"),
            "feed": {
                k: (result.stages.get("feed") or {}).get(k)
                for k in ("ok", "run_id", "chunks", "lead_count", "out_dir")
                if (result.stages.get("feed") or {}).get(k) is not None
            },
            "elapsed_seconds": result.stages.get("elapsed_seconds"),
            "peak_rss_mb": result.stages.get("peak_rss_mb"),
            "sampling": result.stages.get("sampling"),
            "full_scale_universe": result.stages.get("full_scale_universe"),
            "as_of": result.stages.get("as_of"),
            "repo_sha": result.stages.get("repo_sha"),
            "manifest_summary": result.stages.get("manifest_summary"),
        },
    }
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    return EXIT_OK if result.ok else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
