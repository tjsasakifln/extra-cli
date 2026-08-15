"""Additive CLI for the public-document miner. Does not edit #393/#394."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.decision_unit_intelligence.contact_discovery.public_documents import (
    REASON_DOC_IDENTITY_ASSOCIATED,
    DocumentBudget,
    enrich_query_from_campaign,
    mine_public_documents,
    query_from_context,
)
from scripts.decision_unit_intelligence.models import normalize_email
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.historical_campaign import load_campaign_index
from scripts.decision_unit_intelligence.repository import write_json
from scripts.decision_unit_intelligence.runner import default_providers
from scripts.decision_unit_intelligence.web_discovery import SearchBudget


def _cnpjs(args: argparse.Namespace) -> list[str]:
    if args.cnpjs:
        return [item.strip() for item in args.cnpjs.split(",") if item.strip()]
    from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS

    return TRACK_A_CNPJS[: args.limit]


def cmd_mine_docs(args: argparse.Namespace) -> int:
    cnpjs = _cnpjs(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    search_budget = SearchBudget(
        max_queries=args.search_max_queries,
        max_results_per_query=args.search_results_per_query,
        max_pages=args.crawl_max_pages,
        max_bytes=args.crawl_max_bytes,
        timeout_seconds=args.web_timeout_seconds,
        min_query_interval_seconds=args.search_min_interval_seconds,
        cache_ttl_days=args.search_cache_ttl_days,
    )
    providers = default_providers(
        search_backend=args.search_backend,
        searxng_url=args.searxng_url or os.getenv("CONFENGE_SEARXNG_URL"),
        search_budget=search_budget,
        cache_dir=Path(args.search_cache_dir),
    )
    backend = None
    for provider in providers:
        if getattr(provider, "provider_id", "") == "official_documents":
            backend = getattr(provider, "backend", None)
            break
    campaign_index = load_campaign_index()
    rows = []
    totals = {
        "accounts": 0,
        "documents_found": 0,
        "documents_useful": 0,
        "emails_observed": 0,
        "emails_nominally_associated": 0,
        "people_corroborated": 0,
        "stale": 0,
        "ambiguous": 0,
        "searches": 0,
        "bytes_touched": 0,
        "duration_ms": 0,
        "incremental_vs_web": 0,
        "environment_error": None,
    }
    by_source: dict[str, int] = {}
    for cnpj in cnpjs:
        totals["accounts"] += 1
        query = enrich_query_from_campaign(
            query_from_context(
                InvestigationContext(cnpj=cnpj, service=args.service),
                budget=DocumentBudget(
                    max_queries=search_budget.max_queries,
                    max_results_per_query=search_budget.max_results_per_query,
                    max_documents=search_budget.max_pages,
                    max_bytes=search_budget.max_bytes,
                    timeout_seconds=search_budget.timeout_seconds,
                ),
            )
        )
        try:
            mined = mine_public_documents(query, backend=backend, enrich_campaign=False)
        except Exception as exc:
            totals["environment_error"] = f"{type(exc).__name__}:{exc}"
            rows.append({"cnpj": cnpj, "error": totals["environment_error"]})
            continue
        associated = [item for item in mined.associations if item.associated]
        campaign_email = normalize_email(str((campaign_index.get(cnpj) or {}).get("email") or "") or None)
        incremental = [
            item
            for item in associated
            if REASON_DOC_IDENTITY_ASSOCIATED in item.reason_codes and item.email != campaign_email
        ]
        for document in mined.documents:
            by_source[document.source_class] = by_source.get(document.source_class, 0) + 1
        row = {
            "cnpj": cnpj,
            "legal_name": query.legal_name,
            "reason_codes": list(mined.reason_codes),
            "metrics": mined.metrics.to_dict(),
            "document_urls": [doc.url for doc in mined.documents],
            "associated": [item.to_dict() for item in associated],
            "incremental_vs_campaign_email": [item.to_dict() for item in incremental],
            "attempt_status": mined.attempts[0].status if mined.attempts else None,
            "attempt_reason": mined.attempts[0].reason if mined.attempts else None,
        }
        rows.append(row)
        totals["documents_found"] += mined.metrics.documents_found
        totals["documents_useful"] += mined.metrics.documents_useful
        totals["emails_observed"] += mined.metrics.emails_observed
        totals["emails_nominally_associated"] += mined.metrics.emails_nominally_associated
        totals["people_corroborated"] += mined.metrics.people_corroborated
        totals["stale"] += mined.metrics.stale
        totals["ambiguous"] += mined.metrics.ambiguous
        totals["searches"] += mined.metrics.searches
        totals["bytes_touched"] += mined.metrics.bytes_touched
        totals["duration_ms"] += mined.metrics.duration_ms
        totals["incremental_vs_web"] += len(incremental)
    payload = {
        "schema_id": "confenge.dui.public_documents.canary.v1",
        "n": len(cnpjs),
        "search_backend": args.search_backend,
        "totals": totals,
        "documents_by_source_class": by_source,
        "defensible_nominal_emails_not_found_by_392_alone": totals["incremental_vs_web"],
        "accounts": rows,
    }
    write_json(out / "canary-30.json", payload)
    print(json.dumps({"out": str(out / "canary-30.json"), "totals": totals}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="public-documents-miner")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cnpjs")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--service", default="reajuste_14133")
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
    parser.set_defaults(func=cmd_mine_docs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
