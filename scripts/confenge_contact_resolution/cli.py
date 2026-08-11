"""CLI: single-CNPJ and batch public business contact resolution."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.confenge_contact_resolution.cache import ResolutionCache
from scripts.confenge_contact_resolution.enrichment_batch import (
    CompanyJob,
    EnrichmentBatchRunner,
    priority_sort_key,
)
from scripts.confenge_contact_resolution.export import write_resolution_artifacts
from scripts.confenge_contact_resolution.models import ServiceContext
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig, default_adapters


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _load_cnpj_list(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    cnpjs: list[str] = []
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    cnpjs.append(item)
                elif isinstance(item, dict):
                    cnpjs.append(str(item.get("cnpj") or item.get("cnpj14") or ""))
        elif isinstance(data, dict) and "cnpjs" in data:
            cnpjs.extend(str(x) for x in data["cnpjs"])
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # jsonl line or plain CNPJ
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    cnpjs.append(str(obj.get("cnpj") or obj.get("cnpj14") or ""))
                    continue
                except json.JSONDecodeError:
                    pass
            cnpjs.append(line.split(",")[0].strip())
    return [c for c in cnpjs if _digits(c)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_contact_resolution",
        description=(
            "Resolve public business contacts for CONFENGE outreach (candidates + provenance; no outreach send)."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--output-dir",
            "-o",
            type=Path,
            required=True,
            help="Directory for confenge-contact-candidates-v1.jsonl + run_manifest.json",
        )
        sp.add_argument(
            "--service-context",
            choices=[s.value for s in ServiceContext],
            default=ServiceContext.GENERIC.value,
            help="Service context for role ranking",
        )
        sp.add_argument(
            "--fixtures-dir",
            type=Path,
            default=None,
            help="Optional directory with synthetic/injected source fixtures",
        )
        sp.add_argument(
            "--cache-dir",
            type=Path,
            default=None,
            help="Filesystem cache with TTL (default: <output-dir>/.cache)",
        )
        sp.add_argument("--cache-ttl", type=int, default=86400, help="Cache TTL seconds")
        sp.add_argument("--no-cache", action="store_true", help="Disable resolution cache")
        sp.add_argument(
            "--allow-network",
            action="store_true",
            help="Allow optional network adapters (BrasilAPI / web search if enabled)",
        )
        sp.add_argument(
            "--enable-web-search",
            action="store_true",
            help="Enable optional web-search adapter (still NoOp without provider config)",
        )
        sp.add_argument(
            "--check-mx",
            action="store_true",
            help="Run MX layer when dnspython available (never sends mail)",
        )
        sp.add_argument("--max-workers", type=int, default=4, help="Batch concurrency limit")
        sp.add_argument("--run-id", default=None, help="Optional stable run id")

    single = sub.add_parser("resolve", help="Resolve contacts for one CNPJ")
    single.add_argument("--cnpj", required=True, help="CNPJ (digits or formatted)")
    add_common(single)

    batch = sub.add_parser("batch", help="Resolve contacts for a list of CNPJs")
    batch.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="File with CNPJs (txt, csv first column, json list, or jsonl)",
    )
    add_common(batch)

    enrich = sub.add_parser(
        "enrich-batch",
        help=(
            "Ownership-aware mass enrichment with checkpoint, metrics, "
            "third-party rejection artifacts, and Warmbly feed"
        ),
    )
    enrich.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="CNPJ list or jsonl with cnpj14/razao_social/priority_tier",
    )
    enrich.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Directory under artifacts/confenge/contact-enrichment/<run_id>/ preferred",
    )
    enrich.add_argument(
        "--service-context",
        choices=[s.value for s in ServiceContext],
        default=ServiceContext.GENERIC.value,
    )
    enrich.add_argument("--fixtures-dir", type=Path, default=None)
    enrich.add_argument("--cache-dir", type=Path, default=None)
    enrich.add_argument("--cache-ttl", type=int, default=86400)
    enrich.add_argument("--no-cache", action="store_true")
    enrich.add_argument("--allow-network", action="store_true")
    enrich.add_argument(
        "--enable-web-search",
        action="store_true",
        help="Enable web search (auto-on with --allow-network in production; uses DuckDuckGo/Brave)",
    )
    enrich.add_argument("--check-mx", action="store_true")
    enrich.add_argument("--max-workers", type=int, default=4)
    enrich.add_argument("--run-id", default=None)
    enrich.add_argument("--max-companies", type=int, default=None)
    enrich.add_argument("--no-resume", action="store_true", help="Ignore checkpoint")
    cont = sub.add_parser(
        "enrich-continuous",
        help=(
            "Continuous contact enrichment over the live construction universe "
            "(no pilot Top-50 capacity; omit --max-companies for full advance)"
        ),
    )
    cont.add_argument("--dsn", default=None, help="Postgres DSN (or LOCAL_DATALAKE_DSN)")
    cont.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("artifacts/confenge/contact-enrichment/continuous-construction"),
    )
    cont.add_argument(
        "--max-companies",
        type=int,
        default=None,
        help="Smoke/batch bound only — never set to 50 (MINIMUM_PILOT_ACCEPTANCE_SAMPLE)",
    )
    cont.add_argument("--allow-network", action="store_true")
    cont.add_argument("--fixtures-dir", type=Path, default=None)
    cont.add_argument("--no-resume", action="store_true")
    cont.add_argument("--max-search-queries", type=int, default=3)
    cont.add_argument("--max-pages", type=int, default=5)
    cont.add_argument("--max-seconds-per-company", type=float, default=20.0)
    cont.add_argument("--max-workers", type=int, default=4)

    enrich.add_argument(
        "--baseline-metrics",
        type=Path,
        default=None,
        help="Optional JSON with prior verified_email_rate for coverage-spike detection",
    )
    enrich.add_argument(
        "--max-search-queries",
        type=int,
        default=None,
        help="Override MAX_SEARCH_QUERIES_PER_COMPANY",
    )
    enrich.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override MAX_PAGES_PER_COMPANY",
    )
    enrich.add_argument(
        "--max-seconds-per-company",
        type=float,
        default=None,
        help="Override MAX_SECONDS_PER_COMPANY",
    )

    return p


def _make_resolver(args: argparse.Namespace) -> ContactResolver:
    cache = None
    if not args.no_cache:
        cdir = args.cache_dir or (args.output_dir / ".cache")
        cache = ResolutionCache(cdir, ttl_seconds=args.cache_ttl)
    adapters = default_adapters(
        web_search_enabled=bool(args.enable_web_search),
        registry_prefer_network=bool(args.allow_network),
    )
    cfg = ResolverConfig(
        service_context=args.service_context,
        adapters=adapters,
        cache=cache,
        check_mx=bool(args.check_mx),
        allow_network=bool(args.allow_network),
        fixtures_dir=args.fixtures_dir,
        max_workers=max(1, int(args.max_workers)),
    )
    return ContactResolver(cfg)


def cmd_resolve(args: argparse.Namespace) -> int:
    resolver = _make_resolver(args)
    result = resolver.resolve_one(args.cnpj)
    summary = write_resolution_artifacts(
        [result],
        args.output_dir,
        mode="single",
        service_context=args.service_context,
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {**summary, "cnpj14": result.cnpj14, "absence_reason": result.absence_reason}, ensure_ascii=False, indent=2
        )
    )
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    cnpjs = _load_cnpj_list(args.input)
    if not cnpjs:
        print(json.dumps({"ok": False, "error": "empty_input"}, ensure_ascii=False))
        return 2
    resolver = _make_resolver(args)
    results = resolver.resolve_batch(cnpjs, max_workers=args.max_workers)
    summary = write_resolution_artifacts(
        results,
        args.output_dir,
        mode="batch",
        service_context=args.service_context,
        run_id=args.run_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _load_enrichment_jobs(path: Path) -> list[CompanyJob]:
    text = path.read_text(encoding="utf-8")
    jobs: list[CompanyJob] = []
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("companies") or data.get("cnpjs") or []
        for item in rows:
            if isinstance(item, str):
                jobs.append(CompanyJob(cnpj14=_digits(item)))
            elif isinstance(item, dict):
                jobs.append(
                    CompanyJob(
                        cnpj14=_digits(str(item.get("cnpj14") or item.get("cnpj") or "")),
                        razao_social=item.get("razao_social") or item.get("company_name"),
                        priority_tier=str(item.get("priority_tier") or item.get("tier") or "universe"),
                        priority_rank=int(item.get("priority_rank") or item.get("rank") or 10_000_000),
                        meta=item,
                    )
                )
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    jobs.append(CompanyJob(cnpj14=_digits(line)))
                    continue
                jobs.append(
                    CompanyJob(
                        cnpj14=_digits(str(obj.get("cnpj14") or obj.get("cnpj") or "")),
                        razao_social=obj.get("razao_social") or obj.get("company_name"),
                        priority_tier=str(obj.get("priority_tier") or obj.get("tier") or "universe"),
                        priority_rank=int(obj.get("priority_rank") or obj.get("rank") or 10_000_000),
                        meta=obj,
                    )
                )
            else:
                jobs.append(CompanyJob(cnpj14=_digits(line.split(",")[0])))
    return [j for j in jobs if len(j.cnpj14) == 14]


def cmd_enrich_batch(args: argparse.Namespace) -> int:
    jobs = _load_enrichment_jobs(args.input)
    if not jobs:
        print(json.dumps({"ok": False, "error": "empty_input"}, ensure_ascii=False))
        return 2
    jobs = sorted(jobs, key=priority_sort_key)
    baseline = None
    if args.baseline_metrics and args.baseline_metrics.is_file():
        baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8"))

    cache = None
    if not args.no_cache:
        cdir = args.cache_dir or (args.output_dir / ".cache")
        cache = ResolutionCache(cdir, ttl_seconds=args.cache_ttl)

    web_provider = None
    discovery_cascade = None
    enable_web = bool(args.enable_web_search) or bool(args.allow_network)
    if enable_web and bool(args.allow_network) and not args.fixtures_dir:
        from scripts.confenge_contact_resolution.discovery import (
            DiscoveryBudget,
            DiscoveryCascade,
            build_web_search_provider,
        )

        web_provider = build_web_search_provider()
        budget = DiscoveryBudget.from_env_or_defaults(
            max_search_queries=args.max_search_queries,
            max_pages=args.max_pages,
            max_seconds=args.max_seconds_per_company,
        )
        discovery_cascade = DiscoveryCascade(
            budget=budget,
            web_provider=web_provider,
            allow_network=True,
        )

    adapters = default_adapters(
        web_search_enabled=enable_web,
        web_search_provider=web_provider,
        registry_prefer_network=bool(args.allow_network),
    )
    cfg = ResolverConfig(
        service_context=args.service_context,
        adapters=adapters,
        cache=cache,
        check_mx=bool(args.check_mx),
        allow_network=bool(args.allow_network),
        fixtures_dir=args.fixtures_dir,
        max_workers=max(1, int(args.max_workers)),
        apply_ownership=True,
        discovery_cascade=discovery_cascade,
    )
    runner = EnrichmentBatchRunner(
        output_dir=args.output_dir,
        resolver_config=cfg,
        run_id=args.run_id,
        baseline_metrics=baseline,
    )
    # Attach fixtures via context only when fixtures_dir provided — adapters read it
    summary = runner.run(
        jobs,
        resume=not bool(args.no_resume),
        max_companies=args.max_companies,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


def cmd_enrich_continuous(args: argparse.Namespace) -> int:
    import os

    from scripts.confenge_contact_resolution.continuous_from_target_fit import (
        ContinuousEnrichmentConfig,
        run_continuous_enrichment,
    )
    from scripts.confenge_contact_resolution.resolver import ResolverConfig, default_adapters

    dsn = args.dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: set --dsn or LOCAL_DATALAKE_DSN", file=sys.stderr)
        return 2
    cfg = ContinuousEnrichmentConfig(
        output_dir=args.output_dir,
        max_companies=args.max_companies,
        allow_network=bool(args.allow_network),
        fixtures_dir=args.fixtures_dir,
        resume=not bool(args.no_resume),
    )
    # Wire the same discovery cascade as enrich-batch so --allow-network actually
    # runs cheap web search + official site crawl (not an offline no-op).
    web_provider = None
    discovery_cascade = None
    if cfg.allow_network and not cfg.fixtures_dir:
        from scripts.confenge_contact_resolution.discovery import (
            DiscoveryBudget,
            DiscoveryCascade,
            build_web_search_provider,
        )

        web_provider = build_web_search_provider()
        budget = DiscoveryBudget.from_env_or_defaults(
            max_search_queries=int(getattr(args, "max_search_queries", 3) or 3),
            max_pages=int(getattr(args, "max_pages", 5) or 5),
            max_seconds=float(getattr(args, "max_seconds_per_company", 20.0) or 20.0),
        )
        discovery_cascade = DiscoveryCascade(
            budget=budget,
            web_provider=web_provider,
            allow_network=True,
        )
    adapters = default_adapters(
        web_search_enabled=bool(cfg.allow_network),
        web_search_provider=web_provider,
        registry_prefer_network=bool(cfg.allow_network),
    )
    rcfg = ResolverConfig(
        allow_network=cfg.allow_network,
        fixtures_dir=cfg.fixtures_dir,
        apply_ownership=True,
        adapters=adapters,
        discovery_cascade=discovery_cascade,
        max_workers=max(1, int(getattr(args, "max_workers", 4) or 4)),
    )
    report = run_continuous_enrichment(dsn, cfg=cfg, resolver_config=rcfg)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    cov = report.get("contact_coverage") or {}
    # Non-zero exit only on closed-sum failure
    closed = (cov.get("closed_sum_check") or {}).get("confirmed_eq_attempted_plus_never")
    return 0 if closed is not False else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "batch":
        return cmd_batch(args)
    if args.command == "enrich-batch":
        return cmd_enrich_batch(args)
    if args.command == "enrich-continuous":
        return cmd_enrich_continuous(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
