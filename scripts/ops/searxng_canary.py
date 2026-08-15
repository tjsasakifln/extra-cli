"""Compare DDGS vs private SearXNG on the first 10 TRACK_A accounts.

This runner does not change discovery policy. It drives the shipped
``run_account`` path twice (explicit backend each time) and writes a table
of useful yield, person/email pages, latency, failures, and cost.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS
from scripts.decision_unit_intelligence.repository import write_json
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.search_http import SearchHttpMetrics, SearxngHttpBackend
from scripts.decision_unit_intelligence.web_discovery import SearchBudget, SearchHit


def _pages_that_led_to_person_or_email(account: Any) -> list[str]:
    pages: list[str] = []
    for item in getattr(account, "evidence", None) or []:
        url = getattr(item, "source_url", None)
        field = str(getattr(item, "field", "") or "")
        if url and field in {"person_role", "email", "canonical_domain", "company_phone"}:
            pages.append(str(url))
    for route in getattr(account, "routes", None) or []:
        url = getattr(route, "source_url", None)
        if url:
            pages.append(str(url))
        extra = getattr(route, "extra", None) or {}
        if extra.get("source_url"):
            pages.append(str(extra["source_url"]))
    return list(dict.fromkeys(pages))


def summarize_account(account: Any) -> dict[str, Any]:
    search_attempts = [a for a in account.ledger.attempts if a.provider_id == "public_search"]
    attempt = search_attempts[0] if search_attempts else None
    people = [p.person_name for p in account.candidates if p.person_name]
    emails = [
        getattr(route, "channel_value", None)
        for route in account.routes
        if "mail" in str(getattr(route, "channel_type", "")).lower()
        or str(getattr(route, "channel_value", "")).find("@") >= 0
    ]
    emails = [e for e in emails if e]
    return {
        "cnpj": account.cnpj,
        "legal_name": account.legal_name,
        "terminal": getattr(account.terminal, "value", str(account.terminal)),
        "people": people,
        "emails": emails,
        "useful_yield": bool(people or emails),
        "person_email_pages": _pages_that_led_to_person_or_email(account),
        "latency_ms": attempt.duration_ms if attempt else account.ledger.duration_ms,
        "failures": list((attempt.extra.get("failures") if attempt else None) or []),
        "blocked": bool(attempt.blocked) if attempt else False,
        "stop_reason": attempt.stop_reason if attempt else None,
        "result_count": (attempt.extra.get("result_count") if attempt else 0) or 0,
        "search_backend": (attempt.extra.get("search_backend") if attempt else None),
        "cost_brl": account.ledger.cost_brl,
        "bytes_touched": account.ledger.bytes_touched,
    }


def compare_backend_hits(
    *,
    ddgs_hits: list[SearchHit],
    searxng_hits: list[SearchHit],
    ddgs_error: str | None,
    searxng_error: str | None,
    ddgs_ms: float,
    searxng_ms: float,
) -> dict[str, Any]:
    """Pure comparison used by live canary and by unit tests."""

    return {
        "ddgs": {
            "hit_count": len(ddgs_hits),
            "urls": [hit.url for hit in ddgs_hits],
            "error": ddgs_error,
            "latency_ms": round(ddgs_ms, 2),
        },
        "searxng": {
            "hit_count": len(searxng_hits),
            "urls": [hit.url for hit in searxng_hits],
            "error": searxng_error,
            "latency_ms": round(searxng_ms, 2),
        },
        "overlap_urls": sorted(set(h.url for h in ddgs_hits) & set(h.url for h in searxng_hits)),
    }


def run_backend_batch(
    cnpjs: list[str],
    *,
    search_backend: str,
    searxng_url: str | None,
    cache_dir: Path,
    budget: SearchBudget,
) -> list[dict[str, Any]]:
    rows = []
    for cnpj in cnpjs:
        started = perf_counter()
        error = None
        summary: dict[str, Any]
        try:
            account = run_account(
                cnpj,
                search_backend=search_backend,
                searxng_url=searxng_url,
                search_budget=budget,
                cache_dir=cache_dir / search_backend,
                infer_email=False,
            )
            summary = summarize_account(account)
        except Exception as exc:  # runner-level failure must stay visible
            error = f"{type(exc).__name__}:{exc}"
            summary = {
                "cnpj": cnpj,
                "legal_name": None,
                "terminal": "RUNNER_ERROR",
                "people": [],
                "emails": [],
                "useful_yield": False,
                "person_email_pages": [],
                "latency_ms": int((perf_counter() - started) * 1000),
                "failures": [error],
                "blocked": True,
                "stop_reason": "SOURCE_BLOCKED",
                "result_count": 0,
                "search_backend": search_backend,
                "cost_brl": 0.0,
                "bytes_touched": 0,
            }
        summary["wall_ms"] = int((perf_counter() - started) * 1000)
        rows.append(summary)
    return rows


def build_report(
    *,
    cnpjs: list[str],
    ddgs_rows: list[dict[str, Any]],
    searxng_rows: list[dict[str, Any]],
    searxng_url: str | None,
    metrics: dict[str, Any] | None = None,
    probe: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "accounts": len(rows),
            "useful_yield": sum(1 for row in rows if row.get("useful_yield")),
            "person_email_pages": sum(len(row.get("person_email_pages") or []) for row in rows),
            "latency_ms_p50": _mid([int(row.get("latency_ms") or 0) for row in rows]),
            "failures": sum(len(row.get("failures") or []) for row in rows),
            "blocked": sum(1 for row in rows if row.get("blocked")),
            "cost_brl": round(sum(float(row.get("cost_brl") or 0) for row in rows), 4),
        }

    return {
        "schema_id": "confenge.searxng.canary.v1",
        "accounts": cnpjs,
        "searxng_url": searxng_url,
        "ddgs": {"rows": ddgs_rows, "summary": _agg(ddgs_rows)},
        "searxng": {"rows": searxng_rows, "summary": _agg(searxng_rows)},
        "client_metrics": metrics or {},
        "instance_probe": probe or {},
        "cost_note": (
            "Both backends have R$ 0 purchased-data cost. SearXNG cost is host CPU/RAM; "
            "DDGS cost is upstream engine rate-limit risk only."
        ),
        "note": note,
        "recommendation": _recommend(_agg(ddgs_rows), _agg(searxng_rows), searxng_rows),
    }


def _mid(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _recommend(ddgs: dict[str, Any], searxng: dict[str, Any], searxng_rows: list[dict[str, Any]]) -> dict[str, Any]:
    searxng_blocked = int(searxng.get("blocked") or 0)
    if searxng_blocked == len(searxng_rows) and searxng_rows:
        return {
            "primary": "ddgs",
            "fallback": "off",
            "reason": "private SearXNG was unavailable for every account; do not hide that with silent failover",
        }
    if int(searxng.get("useful_yield") or 0) >= int(ddgs.get("useful_yield") or 0):
        return {
            "primary": "searxng",
            "fallback": "ddgs (new explicit run only)",
            "reason": "CONFENGE-controlled instance matched or beat DDGS useful yield; keep DDGS as a recorded operator re-run",
        }
    return {
        "primary": "ddgs",
        "fallback": "searxng",
        "reason": "DDGS useful yield was higher on this canary; keep SearXNG as the controlled batch path once engines stabilize",
    }


def probe_instance(url: str, *, timeout_seconds: float = 12.0) -> dict[str, Any]:
    metrics = SearchHttpMetrics()
    backend = SearxngHttpBackend(url, timeout_seconds=timeout_seconds, metrics=metrics)
    started = perf_counter()
    error = None
    hits: list[SearchHit] = []
    try:
        hits = backend.search("CONFENGE healthcheck empresa engenharia", limit=3)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "url": url,
        "ok": error is None,
        "error": error,
        "result_count": len(hits),
        "latency_ms": int((perf_counter() - started) * 1000),
        "metrics": metrics.snapshot(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="searxng-canary")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--searxng-url", default=os.getenv("CONFENGE_SEARXNG_URL"))
    parser.add_argument("--cache-dir", default=".cache/confenge-searxng-canary")
    parser.add_argument("--skip-ddgs", action="store_true")
    parser.add_argument("--skip-searxng", action="store_true")
    parser.add_argument("--search-max-queries", type=int, default=2)
    parser.add_argument("--search-results-per-query", type=int, default=4)
    parser.add_argument("--crawl-max-pages", type=int, default=2)
    args = parser.parse_args(argv)

    cnpjs = TRACK_A_CNPJS[: args.limit]
    budget = SearchBudget(
        max_queries=args.search_max_queries,
        max_results_per_query=args.search_results_per_query,
        max_pages=args.crawl_max_pages,
        max_bytes=800_000,
        timeout_seconds=12.0,
        min_query_interval_seconds=1.0,
        cache_ttl_days=7,
    )
    cache_dir = Path(args.cache_dir)
    probe = None
    if args.searxng_url and not args.skip_searxng:
        probe = probe_instance(args.searxng_url)

    ddgs_rows: list[dict[str, Any]] = []
    if not args.skip_ddgs:
        ddgs_rows = run_backend_batch(
            cnpjs,
            search_backend="ddgs",
            searxng_url=None,
            cache_dir=cache_dir,
            budget=budget,
        )
    searxng_rows: list[dict[str, Any]] = []
    if not args.skip_searxng:
        if not args.searxng_url:
            searxng_rows = [
                {
                    "cnpj": cnpj,
                    "legal_name": None,
                    "terminal": "RUNNER_ERROR",
                    "people": [],
                    "emails": [],
                    "useful_yield": False,
                    "person_email_pages": [],
                    "latency_ms": 0,
                    "failures": ["SearchBackendUnavailableError:missing_url"],
                    "blocked": True,
                    "stop_reason": "SOURCE_BLOCKED",
                    "result_count": 0,
                    "search_backend": "searxng",
                    "cost_brl": 0.0,
                    "bytes_touched": 0,
                    "wall_ms": 0,
                }
                for cnpj in cnpjs
            ]
        else:
            searxng_rows = run_backend_batch(
                cnpjs,
                search_backend="searxng",
                searxng_url=args.searxng_url,
                cache_dir=cache_dir,
                budget=budget,
            )

    report = build_report(
        cnpjs=cnpjs,
        ddgs_rows=ddgs_rows,
        searxng_rows=searxng_rows,
        searxng_url=args.searxng_url,
        probe=probe,
        note="Failover is never implicit: each backend is a separate recorded run.",
    )
    out = Path(args.out)
    write_json(out, report)
    print(json.dumps({"wrote": str(out), "recommendation": report["recommendation"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
