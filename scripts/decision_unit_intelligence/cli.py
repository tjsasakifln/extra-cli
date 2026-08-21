"""CLI: plan / run / report / replay / shadow / batch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.decision_unit_intelligence import POLICY_VERSION, PROVIDER_VERSION, SCHEMA_VERSION
from scripts.decision_unit_intelligence.affiliation_report import build_affiliation_cohort_report
from scripts.decision_unit_intelligence.batch_queue import (
    ContactDiscoveryQueue,
    budget_version_from_knobs,
    connect,
)
from scripts.decision_unit_intelligence.batch_snapshot import publish_snapshot
from scripts.decision_unit_intelligence.batch_worker import ContactDiscoveryWorker
from scripts.decision_unit_intelligence.benchmark import funnel, replay_report
from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS, build_manifest
from scripts.decision_unit_intelligence.controlled_email_cohort import run_cohort_funnel
from scripts.decision_unit_intelligence.email_discovery import summarize_email_discovery
from scripts.decision_unit_intelligence.operator_pack import build_card, write_operator_pack
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.repository import JsonRunRepository, account_hash, write_json
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.site_contact_crawl import (
    SITE_CRAWL_BUDGET_DEFAULTS,
    SiteCrawlBudget,
    load_fixture_corpus,
    run_site_contact_crawl,
)
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
    site_budget = _site_budget_from_args(args)
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
            search_failover=args.search_failover or os.getenv("CONFENGE_SEARCH_FAILOVER", "off"),
            site_budget=site_budget,
            site_crawl=not args.no_site_crawl,
            site_crawl_baseline=args.site_crawl_baseline,
            query_policy_version=args.query_policy_version,
            search_fallback=args.search_fallback,
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
    email_discovery = summarize_email_discovery(accounts)
    affiliation_cohort = build_affiliation_cohort_report(accounts)
    write_json(Path(args.out) / "affiliation_cohort.json", affiliation_cohort)
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
    web_metrics["cache_hit_rate"] = (
        round(cache_hits / (cache_hits + cache_misses), 4) if cache_hits + cache_misses else 0.0
    )
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
            "failover": args.search_failover or os.getenv("CONFENGE_SEARCH_FAILOVER", "off"),
            "budget": {
                "max_queries_per_account": search_budget.max_queries,
                "max_results_per_query": search_budget.max_results_per_query,
                "max_pages_per_account": search_budget.max_pages,
                "max_bytes_per_account": search_budget.max_bytes,
            },
            "metrics": web_metrics,
        },
        "site_contact_crawl": _site_crawl_manifest(accounts, site_budget),
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
            "identity_proven": email_discovery.observed_identity_associated,
        },
        "email_discovery": email_discovery.to_dict(),
        "affiliation_cohort": {
            "path": "affiliation_cohort.json",
            "schema_id": affiliation_cohort["schema_id"],
            "n": affiliation_cohort["n"],
            "uplift": affiliation_cohort["uplift"],
            "remaining_blockers": affiliation_cohort["remaining_blockers"],
            "next_recommendation": affiliation_cohort["next_recommendation"],
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


def cmd_email_reachability_funnel(args: argparse.Namespace) -> int:
    payload = run_cohort_funnel(args.n)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _resolve_code_sha(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.getenv("EXTRA_CODE_SHA") or os.getenv("GITHUB_SHA")
    if env:
        return env
    head = Path(".git/HEAD")
    if not head.is_file():
        return "unknown"
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = Path(".git") / text.split(" ", 1)[1].strip()
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
    return text or "unknown"


def _budget_knobs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "max_queries": args.search_max_queries,
        "max_results_per_query": args.search_results_per_query,
        "max_pages": args.crawl_max_pages,
        "max_bytes": args.crawl_max_bytes,
        "timeout_seconds": args.web_timeout_seconds,
        "min_query_interval_seconds": args.search_min_interval_seconds,
        "cache_ttl_days": args.search_cache_ttl_days,
        "cache_dir": args.search_cache_dir,
        "infer_email": not args.no_infer_email,
        "verify_email_dns": args.verify_email_dns,
        "searxng_url": args.searxng_url or os.getenv("CONFENGE_SEARXNG_URL"),
    }


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def cmd_batch_enqueue(args: argparse.Namespace) -> int:
    cnpjs = _load_cnpjs(args)
    knobs = _budget_knobs(args)
    version = budget_version_from_knobs(knobs)
    code_sha = _resolve_code_sha(args.code_sha)
    inserted = 0
    reused = 0
    ids: list[int] = []
    with connect(args.dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        queue.upsert_cohort(
            cohort_id=args.cohort,
            service=args.service,
            offer_context=args.offer_context,
            discovery_policy_version=POLICY_VERSION,
            search_backend=args.search_backend,
            budget_version=version,
            code_sha=code_sha,
            input_evidence_version=args.input_evidence_version,
            metadata={"n": len(cnpjs), "output_root": args.out},
        )
        for cnpj in cnpjs:
            job_id, created = queue.enqueue(
                cohort_id=args.cohort,
                canonical_account_id=cnpj,
                service=args.service,
                offer_context=args.offer_context,
                discovery_policy_version=POLICY_VERSION,
                search_backend=args.search_backend,
                budget_version=version,
                code_sha=code_sha,
                input_evidence_version=args.input_evidence_version,
                max_attempts=args.max_attempts,
                backend_concurrency_limit=args.backend_concurrency,
                domain_concurrency_limit=args.domain_concurrency,
                cursor={"budget": knobs},
            )
            ids.append(job_id)
            if created:
                inserted += 1
            else:
                reused += 1
        progress = queue.progress(cohort_id=args.cohort)
    _print(
        {
            "cohort": args.cohort,
            "enqueued": inserted,
            "reused": reused,
            "job_ids": ids,
            "policy_version": POLICY_VERSION,
            "budget_version": version,
            "code_sha": code_sha,
            "search_backend": args.search_backend,
            "progress": progress,
        }
    )
    return 0


def cmd_batch_inspect(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id=args.cohort, job_id=args.job_id)
    _print({"cohort": args.cohort, "n": len(jobs), "jobs": jobs})
    return 0


def cmd_batch_progress(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        _print(ContactDiscoveryQueue(connection).progress(cohort_id=args.cohort))
    return 0


def cmd_batch_failures(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        rows = ContactDiscoveryQueue(connection).failures(cohort_id=args.cohort)
    _print({"cohort": args.cohort, "n": len(rows), "failures": rows})
    return 0


def cmd_batch_retry(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        n = ContactDiscoveryQueue(connection).retry(
            cohort_id=args.cohort,
            job_id=args.job_id,
            reason_codes=args.reason_code,
        )
    _print({"retried": n, "cohort": args.cohort, "job_id": args.job_id})
    return 0


def cmd_batch_cancel(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        n = ContactDiscoveryQueue(connection).request_cancel(cohort_id=args.cohort, job_id=args.job_id)
    _print({"cancelled": n, "cohort": args.cohort, "job_id": args.job_id})
    return 0


def cmd_batch_resume(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        _print(ContactDiscoveryQueue(connection).resume(cohort_id=args.cohort))
    return 0


def cmd_batch_publish(args: argparse.Namespace) -> int:
    with connect(args.dsn) as connection:
        result = publish_snapshot(
            ContactDiscoveryQueue(connection),
            cohort_id=args.cohort,
            output_root=Path(args.out),
            allow_partial=args.allow_partial,
        )
    _print(result)
    return 0 if result.get("approved") else 2


def cmd_batch_worker(args: argparse.Namespace) -> int:
    dsn = args.dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    worker = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id=args.worker_id,
        lease_seconds=args.lease_seconds,
        output_root=Path(args.out),
        claim_limit=args.claim_limit,
        backend_filter=args.backend,
    )
    if args.loop:
        _print(worker.run_loop(idle_sleep=args.idle_sleep, max_jobs=args.max_jobs))
    else:
        _print(worker.run_once())
    return 0


def cmd_batch_kill_switch(args: argparse.Namespace) -> int:
    if args.enable == args.disable:
        raise SystemExit("kill-switch requires exactly one of --enable or --disable")
    with connect(args.dsn) as connection:
        result = ContactDiscoveryQueue(connection).set_kill_switch(
            enabled=bool(args.enable),
            reason=args.reason or ("enabled" if args.enable else "disabled"),
            actor=args.actor,
        )
    _print(result)
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

    email_funnel = sub.add_parser("email-reachability-funnel")
    email_funnel.add_argument("--n", type=int, default=120)
    email_funnel.add_argument("--out")
    email_funnel.set_defaults(func=cmd_email_reachability_funnel)

    batch = sub.add_parser("batch", help="Durable contact-discovery cohort operations")
    batch_sub = batch.add_subparsers(dest="batch_cmd", required=True)

    enqueue = batch_sub.add_parser("enqueue")
    enqueue.add_argument("--cohort", required=True)
    enqueue.add_argument("--out", default="output/contact-discovery")
    enqueue.add_argument("--manifest")
    enqueue.add_argument("--cnpjs")
    enqueue.add_argument("--limit", type=int)
    enqueue.add_argument("--service", default="reajuste_14133")
    enqueue.add_argument("--offer-context")
    enqueue.add_argument("--input-evidence-version", default="input.v1")
    enqueue.add_argument("--code-sha")
    enqueue.add_argument("--dsn")
    enqueue.add_argument("--max-attempts", type=int, default=5)
    enqueue.add_argument("--backend-concurrency", type=int, default=2)
    enqueue.add_argument("--domain-concurrency", type=int, default=1)
    enqueue.add_argument("--no-infer-email", action="store_true")
    _add_web_discovery_args(enqueue)
    enqueue.set_defaults(func=cmd_batch_enqueue)

    inspect = batch_sub.add_parser("inspect")
    inspect.add_argument("--cohort", required=True)
    inspect.add_argument("--job-id", type=int)
    inspect.add_argument("--dsn")
    inspect.set_defaults(func=cmd_batch_inspect)

    progress = batch_sub.add_parser("progress")
    progress.add_argument("--cohort", required=True)
    progress.add_argument("--dsn")
    progress.set_defaults(func=cmd_batch_progress)

    failures = batch_sub.add_parser("failures")
    failures.add_argument("--cohort", required=True)
    failures.add_argument("--dsn")
    failures.set_defaults(func=cmd_batch_failures)

    retry = batch_sub.add_parser("retry")
    retry.add_argument("--cohort")
    retry.add_argument("--job-id", type=int)
    retry.add_argument("--reason-code", action="append")
    retry.add_argument("--dsn")
    retry.set_defaults(func=cmd_batch_retry)

    cancel = batch_sub.add_parser("cancel")
    cancel.add_argument("--cohort")
    cancel.add_argument("--job-id", type=int)
    cancel.add_argument("--dsn")
    cancel.set_defaults(func=cmd_batch_cancel)

    resume = batch_sub.add_parser("resume")
    resume.add_argument("--cohort", required=True)
    resume.add_argument("--dsn")
    resume.set_defaults(func=cmd_batch_resume)

    publish = batch_sub.add_parser("publish")
    publish.add_argument("--cohort", required=True)
    publish.add_argument("--out", default="output/contact-discovery")
    publish.add_argument("--allow-partial", action="store_true")
    publish.add_argument("--dsn")
    publish.set_defaults(func=cmd_batch_publish)

    worker = batch_sub.add_parser("worker")
    worker.add_argument("--dsn")
    worker.add_argument("--worker-id")
    worker.add_argument("--loop", action="store_true")
    worker.add_argument("--idle-sleep", type=float, default=2.0)
    worker.add_argument("--max-jobs", type=int)
    worker.add_argument("--lease-seconds", type=int, default=300)
    worker.add_argument("--claim-limit", type=int, default=1)
    worker.add_argument("--backend")
    worker.add_argument("--out", default="output/contact-discovery")
    worker.set_defaults(func=cmd_batch_worker)

    kill = batch_sub.add_parser("kill-switch")
    kill.add_argument("--enable", action="store_true")
    kill.add_argument("--disable", action="store_true")
    kill.add_argument("--reason", default="")
    kill.add_argument("--actor", default="operator")
    kill.add_argument("--dsn")
    kill.set_defaults(func=cmd_batch_kill_switch)

    site = sub.add_parser("site-crawl")
    site.add_argument("--out", required=True)
    site.add_argument(
        "--fixture",
        default="tests/fixtures/site_contact_crawl/empresaexemplo.com.br",
    )
    site.add_argument("--domain")
    site.add_argument("--cnpj", default="12345678000190")
    site.add_argument("--legal-name", default="EMPRESA EXEMPLO ENGENHARIA LTDA")
    site.add_argument("--service", default="reajuste_14133")
    site.add_argument("--seed-url", action="append")
    site.add_argument("--baseline", action="store_true")
    _add_site_crawl_args(site)
    site.set_defaults(func=cmd_site_crawl)
    return p


def _add_web_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--search-backend", choices=("off", "searxng", "ddgs"), default="off")
    parser.add_argument("--searxng-url")
    parser.add_argument(
        "--search-failover",
        choices=("off", "ddgs"),
        default="off",
        help="Explicit recorded failover only. Default off; never hides SearXNG downtime.",
    )
    parser.add_argument("--search-max-queries", type=int, default=4)
    parser.add_argument("--search-results-per-query", type=int, default=5)
    parser.add_argument("--crawl-max-pages", type=int, default=4)
    parser.add_argument("--crawl-max-bytes", type=int, default=1_500_000)
    parser.add_argument("--web-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--search-min-interval-seconds", type=float, default=1.0)
    parser.add_argument("--search-cache-ttl-days", type=int, default=7)
    parser.add_argument("--search-cache-dir", default=".cache/confenge-prospect")
    parser.add_argument("--verify-email-dns", action="store_true")
    parser.add_argument("--no-site-crawl", action="store_true")
    parser.add_argument("--site-crawl-baseline", action="store_true")
    _add_site_crawl_args(parser)


def cmd_site_crawl(args: argparse.Namespace) -> int:
    """Drive the shipped site-contact crawl against a local fixture corpus."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    crawler, domain = load_fixture_corpus(Path(args.fixture))
    domain = args.domain or domain
    budget = _site_budget_from_args(args)
    context = InvestigationContext(
        cnpj=args.cnpj,
        legal_name=args.legal_name,
        service=args.service,
        extra={"company_site": f"https://{domain}", "domain_resolution": {"canonical_domain": domain}},
    )
    result = run_site_contact_crawl(
        crawler=crawler,
        context=context,
        canonical_domain=domain,
        seed_urls=list(args.seed_url or []),
        budget=budget,
        baseline=args.baseline,
        rate_limit=False,
    )
    payload = {
        "schema_id": "confenge.dui.site-contact-crawl.v1",
        "domain": domain,
        "cnpj": args.cnpj,
        "legal_name": args.legal_name,
        "baseline": args.baseline,
        "budget": budget.to_dict(),
        "result": result.to_dict(),
        "metrics": result.metrics,
        "named_associated": [
            {
                "email": item.email,
                "person_name": item.person_name,
                "reason_codes": list(item.reason_codes),
                "source_url": item.source_url,
                "page_type": item.page_type,
            }
            for item in result.contacts
            if item.associated and item.person_name
        ],
    }
    write_json(out / "site-crawl.json", payload)
    print(json.dumps({"out": str(out / "site-crawl.json"), "metrics": result.metrics}, ensure_ascii=False, indent=2))
    return 0


def _site_budget_from_args(args: argparse.Namespace) -> SiteCrawlBudget:
    defaults = SITE_CRAWL_BUDGET_DEFAULTS
    return SiteCrawlBudget(
        max_pages=getattr(args, "site_max_pages", defaults.max_pages),
        max_depth=getattr(args, "site_max_depth", defaults.max_depth),
        max_bytes=getattr(args, "site_max_bytes", defaults.max_bytes),
        timeout_seconds=getattr(args, "site_timeout_seconds", defaults.timeout_seconds),
        max_redirects=getattr(args, "site_max_redirects", defaults.max_redirects),
        requests_per_minute=getattr(args, "site_requests_per_minute", defaults.requests_per_minute),
        max_sitemap_urls=getattr(args, "site_max_sitemap_urls", defaults.max_sitemap_urls),
    )


def _site_crawl_manifest(accounts, site_budget: SiteCrawlBudget) -> dict:
    attempts = [
        attempt
        for account in accounts
        for attempt in account.ledger.attempts
        if attempt.provider_id == "company_website"
    ]
    executed = [attempt for attempt in attempts if attempt.status != "skipped"]
    metrics = {
        "accounts_attempted": len(executed),
        "high_value_pages": 0,
        "pages": 0,
        "emails_observed": 0,
        "named_associated": 0,
        "false_association": 0,
        "bytes_touched": 0,
        "latency_ms": 0,
        "yield_by_page_type": {},
    }
    for attempt in executed:
        extra = attempt.extra.get("metrics") or (attempt.extra.get("site_crawl") or {}).get("metrics") or {}
        metrics["high_value_pages"] += int(extra.get("high_value_pages") or 0)
        metrics["pages"] += int(attempt.documents_checked or extra.get("pages_fetched") or 0)
        metrics["emails_observed"] += int(extra.get("emails_observed") or 0)
        metrics["named_associated"] += int(extra.get("named_associated") or 0)
        metrics["false_association"] += int(extra.get("false_association") or 0)
        metrics["bytes_touched"] += int(attempt.bytes_touched or extra.get("bytes_touched") or 0)
        metrics["latency_ms"] += int(attempt.duration_ms or extra.get("latency_ms") or 0)
        for page_type, count in (extra.get("yield_by_page_type") or {}).items():
            metrics["yield_by_page_type"][page_type] = metrics["yield_by_page_type"].get(page_type, 0) + int(count)
    attempted = metrics["accounts_attempted"] or 0
    metrics["pages_per_account"] = round(metrics["pages"] / attempted, 4) if attempted else 0.0
    return {"budget": site_budget.to_dict(), "metrics": metrics}


def _add_site_crawl_args(parser: argparse.ArgumentParser) -> None:
    defaults = SITE_CRAWL_BUDGET_DEFAULTS
    parser.add_argument("--site-max-pages", type=int, default=defaults.max_pages)
    parser.add_argument("--site-max-depth", type=int, default=defaults.max_depth)
    parser.add_argument("--site-max-bytes", type=int, default=defaults.max_bytes)
    parser.add_argument("--site-timeout-seconds", type=float, default=defaults.timeout_seconds)
    parser.add_argument("--site-max-redirects", type=int, default=defaults.max_redirects)
    parser.add_argument("--site-requests-per-minute", type=int, default=defaults.requests_per_minute)
    parser.add_argument("--site-max-sitemap-urls", type=int, default=defaults.max_sitemap_urls)
    parser.add_argument("--query-policy-version", default="query-policy.v2")
    parser.add_argument("--search-fallback", choices=("off", "ddgs", "searxng"), default="off")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
