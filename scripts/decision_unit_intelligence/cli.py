"""CLI: plan / run / report / replay / shadow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.decision_unit_intelligence import POLICY_VERSION, PROVIDER_VERSION, SCHEMA_VERSION
from scripts.decision_unit_intelligence.benchmark import funnel, replay_report
from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS, build_manifest
from scripts.decision_unit_intelligence.operator_pack import build_card, write_operator_pack
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach
from scripts.decision_unit_intelligence.repository import JsonRunRepository, account_hash, write_json
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.web_discovery import SearchBudget


def _load_cnpjs(args: argparse.Namespace) -> list[str]:
    if args.cnpjs:
        return [c.strip() for c in args.cnpjs.split(",") if c.strip()]
    if args.manifest:
        payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        return [a["cnpj"] for a in payload.get("accounts") or []]
    limit = args.limit or 30
    if limit <= len(TRACK_A_CNPJS):
        return TRACK_A_CNPJS[:limit]
    from scripts.decision_unit_intelligence.providers.historical_campaign import load_campaign_index

    extra = [c for c in load_campaign_index() if c not in TRACK_A_CNPJS]
    extra.sort()
    return (TRACK_A_CNPJS + extra)[:limit]


def cmd_plan(args: argparse.Namespace) -> int:
    out = Path(args.out)
    manifest = build_manifest(_load_cnpjs(args))
    write_json(out, manifest)
    print(
        json.dumps({"wrote": str(out), "n": manifest["n"], "seed": manifest["selection"]["seed"]}, ensure_ascii=False)
    )
    return 0


def _execute(args: argparse.Namespace, *, label: str) -> int:
    cnpjs = _load_cnpjs(args)
    repo = JsonRunRepository(Path(args.out))
    accounts = []
    search_budget = SearchBudget(
        max_queries=args.search_max_queries,
        max_results_per_query=args.search_results_per_query,
        max_pages=args.crawl_max_pages,
        max_bytes=args.crawl_max_bytes,
        timeout_seconds=args.web_timeout_seconds,
        min_query_interval_seconds=args.search_min_interval_seconds,
        cache_ttl_days=args.search_cache_ttl_days,
    )
    for cnpj in cnpjs:
        acc = run_account(
            cnpj,
            service=args.service,
            infer_email=not args.no_infer_email,
            search_backend=args.search_backend,
            searxng_url=args.searxng_url or os.getenv("CONFENGE_SEARXNG_URL"),
            search_budget=search_budget,
            cache_dir=Path(args.search_cache_dir),
            verify_email_dns=args.verify_email_dns,
        )
        payload = acc.to_dict()
        payload["replay_hash"] = account_hash(payload)
        repo.save_account(payload)
        accounts.append(acc)
        print(
            f"{label}\t{acc.cnpj}\t{acc.terminal.value}\t{acc.extra.get('account_reachability_class')}\t{acc.legal_name}"
        )
    fun = funnel(accounts)
    repo.save_funnel(fun)
    cards = [build_card(a) for a in accounts]
    operator_dir = Path(args.operator_out) if args.operator_out else Path(args.out) / "operator"
    pack_paths = write_operator_pack(cards, operator_dir)
    warmbly = [project_warmbly_outreach(a) for a in accounts]
    email_safe = sum(w["email_safe_count"] for w in warmbly)
    write_json(Path(args.out) / "warmbly_outreach.json", {"accounts": warmbly, "email_safe_total": email_safe})
    web_attempts = [
        attempt for account in accounts for attempt in account.ledger.attempts if attempt.provider_id == "public_search"
    ]
    web_metrics = {
        "accounts_attempted": sum(attempt.status != "skipped" for attempt in web_attempts),
        "domains_resolved": sum(
            bool((attempt.extra.get("domain_resolution") or {}).get("canonical_domain")) for attempt in web_attempts
        ),
        "searches": sum(len(attempt.queries) for attempt in web_attempts if attempt.status != "skipped"),
        "pages": sum(attempt.documents_checked for attempt in web_attempts),
        "bytes_touched": sum(attempt.bytes_touched for attempt in web_attempts),
        "external_cost_brl": sum(attempt.cost_brl for attempt in web_attempts),
    }
    cache_hits = sum(int(attempt.extra.get("cache_hits") or 0) for attempt in web_attempts)
    cache_misses = sum(int(attempt.extra.get("cache_misses") or 0) for attempt in web_attempts)
    attempted_accounts = int(web_metrics["accounts_attempted"])
    web_metrics["cache_hits"] = cache_hits
    web_metrics["cache_misses"] = cache_misses
    web_metrics["cache_hit_rate"] = round(cache_hits / (cache_hits + cache_misses), 4) if cache_hits + cache_misses else 0.0
    web_metrics["duration_ms"] = sum(attempt.duration_ms for attempt in web_attempts)
    web_metrics["searches_per_account"] = (
        round(int(web_metrics["searches"]) / attempted_accounts, 4) if attempted_accounts else 0.0
    )
    web_metrics["pages_per_account"] = (
        round(int(web_metrics["pages"]) / attempted_accounts, 4) if attempted_accounts else 0.0
    )
    web_metrics["time_per_account_ms"] = (
        round(int(web_metrics["duration_ms"]) / attempted_accounts, 2) if attempted_accounts else 0.0
    )
    manifest = {
        "schema_id": "confenge.dui.run.v1",
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "provider_version": PROVIDER_VERSION,
        "n": len(accounts),
        "cnpjs": cnpjs,
        "funnel": fun,
        "operator_pack": pack_paths,
        "email_safe_warmbly": email_safe,
        "web_discovery": {
            "backend": args.search_backend,
            "budget": {
                "max_queries_per_account": search_budget.max_queries,
                "max_results_per_query": search_budget.max_results_per_query,
                "max_pages_per_account": search_budget.max_pages,
                "max_bytes_per_account": search_budget.max_bytes,
            },
            "metrics": web_metrics,
        },
        "email_verification": {
            "enabled": args.verify_email_dns,
            "emails_checked": sum(len(account.extra.get("email_verification") or []) for account in accounts),
            "mx_present": sum(
                report.get("mx") == "MX_PRESENT"
                for account in accounts
                for report in (account.extra.get("email_verification") or [])
            ),
            "smtp_skipped_policy": sum(
                report.get("smtp") == "SKIPPED_POLICY"
                for account in accounts
                for report in (account.extra.get("email_verification") or [])
            ),
            "identity_proven": 0,
        },
        "selection": build_manifest(cnpjs)["selection"],
        "auto_send": False,
    }
    repo.save_manifest(manifest)
    print(json.dumps({"out": args.out, "operator": pack_paths, "funnel": fun}, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _execute(args, label="RUN")


def cmd_shadow(args: argparse.Namespace) -> int:
    return _execute(args, label="SHADOW")


def cmd_report(args: argparse.Namespace) -> int:
    repo = JsonRunRepository(Path(args.run))
    accounts = repo.load_accounts()
    print(
        json.dumps(
            {"n": len(accounts), "path": args.run, "sample": accounts[0]["cnpj"] if accounts else None}, indent=2
        )
    )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    first = JsonRunRepository(Path(args.run_a)).load_accounts()
    second = JsonRunRepository(Path(args.run_b)).load_accounts()
    print(json.dumps(replay_report(first, second), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="decision-unit-intelligence")
    sub = p.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--out", required=True)
    plan.add_argument("--manifest")
    plan.add_argument("--cnpjs")
    plan.add_argument("--limit", type=int, default=30)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run")
    run.add_argument("--out", required=True)
    run.add_argument("--operator-out")
    run.add_argument("--manifest")
    run.add_argument("--cnpjs")
    run.add_argument("--limit", type=int, default=30)
    run.add_argument("--service", default="reajuste_14133")
    run.add_argument("--no-infer-email", action="store_true")
    _add_web_discovery_args(run)
    run.set_defaults(func=cmd_run)

    shadow = sub.add_parser("shadow")
    shadow.add_argument("--out", required=True)
    shadow.add_argument("--operator-out")
    shadow.add_argument("--manifest")
    shadow.add_argument("--cnpjs")
    shadow.add_argument("--limit", type=int, default=100)
    shadow.add_argument("--service", default="reajuste_14133")
    shadow.add_argument("--no-infer-email", action="store_true")
    _add_web_discovery_args(shadow)
    shadow.set_defaults(func=cmd_shadow)

    report = sub.add_parser("report")
    report.add_argument("--run", required=True)
    report.set_defaults(func=cmd_report)

    replay = sub.add_parser("replay")
    replay.add_argument("--run-a", required=True)
    replay.add_argument("--run-b", required=True)
    replay.set_defaults(func=cmd_replay)
    return p


def _add_web_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--search-backend", choices=("off", "searxng", "ddgs"), default="off")
    parser.add_argument("--searxng-url")
    parser.add_argument("--search-max-queries", type=int, default=4)
    parser.add_argument("--search-results-per-query", type=int, default=5)
    parser.add_argument("--crawl-max-pages", type=int, default=4)
    parser.add_argument("--crawl-max-bytes", type=int, default=1_500_000)
    parser.add_argument("--web-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--search-min-interval-seconds", type=float, default=1.0)
    parser.add_argument("--search-cache-ttl-days", type=int, default=7)
    parser.add_argument("--search-cache-dir", default=".cache/confenge-prospect")
    parser.add_argument("--verify-email-dns", action="store_true")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
