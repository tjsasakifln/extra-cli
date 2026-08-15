"""Benchmark the same 30, then 100, accounts. Replay is the honest live fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS, build_manifest
from scripts.decision_unit_intelligence.email_discovery import is_third_party_echo_source
from scripts.decision_unit_intelligence.models import normalize_email, now_iso
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.historical_campaign import load_campaign_index, parse_qsa_blob
from scripts.decision_unit_intelligence.query_planner.planner import (
    QueryPlannerError,
    QuerySearchCache,
    execute_plan,
    load_policy,
    plan_queries,
)
from scripts.decision_unit_intelligence.query_planner.spec import (
    DEFAULT_POLICY_VERSION,
    QueryExecution,
    QueryFamily,
    QueryPolicy,
    host_of,
    infer_trade_name,
    operators_for,
)
from scripts.decision_unit_intelligence.query_planner.yield_eval import (
    aggregate_executions,
    rank_families,
    rank_queries,
)
from scripts.decision_unit_intelligence.web_discovery import JsonDiscoveryCache, SearchHit

OBSERVATIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "track_a_30.observations.json"


@dataclass
class BenchmarkAccount:
    cnpj: str
    legal_name: str | None
    site: str | None
    email: str | None
    fonte: str | None
    people: list[str]
    trade_name: str | None = None

    @property
    def domain(self) -> str | None:
        return host_of(self.site)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cnpj": self.cnpj,
            "legal_name": self.legal_name,
            "site": self.site,
            "email": self.email,
            "fonte": self.fonte,
            "people": list(self.people),
            "trade_name": self.trade_name,
            "domain": self.domain,
        }


class ObservationReplayBackend:
    """Deterministic hits grounded in campaign observations. Does not invent emails."""

    def __init__(
        self,
        accounts: list[BenchmarkAccount],
        *,
        simulate_backend: str = "searxng",
        failures: dict[str, Exception] | None = None,
    ) -> None:
        self.backend_id = f"replay-{simulate_backend}"
        self.simulate_backend = simulate_backend
        self.accounts = {account.cnpj: account for account in accounts}
        self.failures = failures or {}
        self.queries: list[str] = []

    def fail(self, query: str, exc: Exception) -> None:
        self.failures[query] = exc

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        self.queries.append(query)
        if query in self.failures:
            raise self.failures[query]
        hits: list[SearchHit] = []
        for account in self.accounts.values():
            hits.extend(self._hits_for(account, query))
        return hits[:limit]

    def _hits_for(self, account: BenchmarkAccount, query: str) -> list[SearchHit]:
        if not _query_mentions(account, query):
            return []
        hits: list[SearchHit] = []
        for url in _observed_urls(account):
            if not _url_matches_query(url, query, account):
                continue
            hits.append(
                SearchHit(
                    url=url,
                    title=_observed_title(account, url, query),
                    snippet=_observed_snippet(account, url, query),
                    engine=self.simulate_backend,
                )
            )
        return hits


def _query_mentions(account: BenchmarkAccount, query: str) -> bool:
    folded = query.lower()
    if account.cnpj in query:
        return True
    if account.legal_name and account.legal_name.lower() in folded:
        return True
    if account.trade_name and account.trade_name.lower() in folded:
        return True
    if account.domain and account.domain in folded:
        return True
    return any(person.lower() in folded for person in account.people)


def _person_in_query(account: BenchmarkAccount, query: str) -> str | None:
    folded = query.lower()
    for person in account.people:
        if person.lower() in folded:
            return person
    return None


def _observed_urls(account: BenchmarkAccount) -> list[str]:
    """Only URLs recorded on the observation. Never construct /equipe or /ata.pdf."""
    urls: list[str] = []
    for raw in (account.site, account.fonte):
        if raw and raw not in urls:
            urls.append(raw)
    return urls


def _site_slug(query: str) -> str | None:
    for slug in ("equipe", "diretoria", "contato", "engenharia"):
        if slug in query.lower():
            return slug
    return None


def _url_matches_query(url: str, query: str, account: BenchmarkAccount) -> bool:
    folded = query.lower()
    path = (urlsplit(url).path or "").lower()
    host = host_of(url)
    if "filetype:pdf" in folded:
        return path.endswith(".pdf") or url.lower().split("?", 1)[0].endswith(".pdf")
    slug = _site_slug(query)
    if slug and "site:" in folded:
        return bool(account.domain and host == account.domain and slug in path)
    if account.domain and (f"site:{account.domain}" in folded or f"@{account.domain}" in folded):
        return host == account.domain
    return True


def _include_observed_email(account: BenchmarkAccount, url: str, query: str) -> bool:
    email = normalize_email(account.email)
    if not email or is_third_party_echo_source(url):
        return False
    folded = query.lower()
    if "email" not in folded and "@" not in folded:
        return False
    person = _person_in_query(account, query)
    mentions_company = bool(
        (account.legal_name and account.legal_name.lower() in folded)
        or account.cnpj in query
        or (account.domain and account.domain in folded)
        or (account.trade_name and account.trade_name.lower() in folded)
    )
    if person and not mentions_company:
        return _email_belongs_to_person(email, person)
    return mentions_company


def _observed_title(account: BenchmarkAccount, url: str, query: str) -> str:
    person = _person_in_query(account, query)
    label = account.legal_name or account.cnpj
    if person:
        return f"{person} {label}"
    if url.lower().split("?", 1)[0].endswith(".pdf"):
        return f"{label} documento"
    return label


def _observed_snippet(account: BenchmarkAccount, url: str, query: str) -> str:
    parts = [account.legal_name or account.cnpj]
    person = _person_in_query(account, query)
    if person:
        parts.append(person)
    if url.lower().split("?", 1)[0].endswith(".pdf"):
        parts.append("documento público")
    if _include_observed_email(account, url, query):
        email = normalize_email(account.email)
        if email:
            parts.append(email)
            if person and _email_belongs_to_person(email, person):
                parts.append(f"E-mail de {person}: {email}")
    return ". ".join(part for part in parts if part)


def _email_belongs_to_person(email: str, person: str) -> bool:
    local = email.split("@", 1)[0].replace(".", " ").replace("_", " ")
    tokens = [tok for tok in person.lower().split() if len(tok) > 2]
    return bool(tokens) and tokens[0] in local and tokens[-1] in local


class LiveBackendError(QueryPlannerError):
    pass


def load_benchmark_accounts(limit: int) -> tuple[list[BenchmarkAccount], dict[str, Any]]:
    index = load_campaign_index()
    requested = _cohort_cnpjs(limit)
    accounts: list[BenchmarkAccount] = []
    for cnpj in requested:
        row = index.get(cnpj) or {"cnpj": cnpj}
        people = [name for name, _role in parse_qsa_blob(row.get("qsa"))]
        people.extend(name for name, _role in parse_qsa_blob(row.get("qsa2")) if name not in people)
        legal = row.get("legal_name") or row.get("razao_social") or row.get("Empresa")
        site = row.get("site")
        email = row.get("email") or None
        if isinstance(email, str) and not email.strip():
            email = None
        domain = host_of(site) if site else None
        accounts.append(
            BenchmarkAccount(
                cnpj=cnpj,
                legal_name=str(legal) if legal else None,
                site=str(site) if site else None,
                email=str(email) if email else None,
                fonte=str(row.get("fonte") or "") or None,
                people=people,
                trade_name=infer_trade_name(str(legal) if legal else None, domain),
            )
        )
    meta = {
        "requested": limit,
        "available": len(accounts),
        "selection": build_manifest([account.cnpj for account in accounts])["selection"],
        "shortage": None
        if len(accounts) >= limit
        else "campaign index does not contain enough real CNPJs; no invented accounts",
    }
    return accounts, meta


def _cohort_cnpjs(limit: int) -> list[str]:
    if limit <= len(TRACK_A_CNPJS):
        return TRACK_A_CNPJS[:limit]
    extra = [cnpj for cnpj in load_campaign_index() if cnpj not in TRACK_A_CNPJS]
    extra.sort()
    return (TRACK_A_CNPJS + extra)[:limit]


def run_backend_benchmark(
    accounts: list[BenchmarkAccount],
    *,
    backend,
    policy: QueryPolicy,
    cache: QuerySearchCache | None,
    results_per_query: int,
) -> list[QueryExecution]:
    executions: list[QueryExecution] = []
    for account in accounts:
        context = InvestigationContext(cnpj=account.cnpj, legal_name=account.legal_name, service="reajuste_14133")
        plan = plan_queries(
            context,
            policy=policy,
            known_domain=account.domain,
            known_people=account.people,
            trade_name=account.trade_name,
        )
        executions.extend(
            execute_plan(
                plan,
                backend,
                policy=policy,
                cache=cache,
                limit=results_per_query,
                legal_name=account.legal_name,
                known_people=account.people,
            ).executions
        )
    return executions


def compare_backends(
    primary: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    def _uplift(metric: str) -> float | None:
        base = comparison.get(metric)
        next_value = primary.get(metric)
        if base in (None, 0) and next_value in (None, 0):
            return 0.0
        if not base:
            return None
        return round((float(next_value) - float(base)) / float(base), 4)

    return {
        "primary": primary.get("backend"),
        "comparison": comparison.get("backend"),
        "observed_email_per_search": _uplift("observed_email_per_search"),
        "identity_associated_per_search": _uplift("identity_associated_per_search"),
        "useful_pages_per_search": _uplift("useful_pages_per_search"),
        "observed_email_per_minute": _uplift("observed_email_per_minute"),
        "identity_associated_per_minute": _uplift("identity_associated_per_minute"),
        "no_gain": _no_gain(primary, comparison),
    }


def _no_gain(primary: dict[str, Any], comparison: dict[str, Any]) -> bool:
    keys = ("observed_email_per_search", "identity_associated_per_search")
    return all(float(primary.get(key) or 0) <= float(comparison.get(key) or 0) for key in keys)


def derive_policy(family_ranking: list[dict[str, Any]], *, version: str = DEFAULT_POLICY_VERSION) -> QueryPolicy:
    budgets: dict[QueryFamily, int] = {}
    disabled: list[QueryFamily] = []
    order: list[QueryFamily] = []
    for row in family_ranking:
        family = QueryFamily(row["family"])
        order.append(family)
        identity = float(row.get("identity_associated_per_search") or 0)
        observed = float(row.get("observed_email_per_search") or 0)
        useful = float(row.get("useful_pages_per_search") or 0)
        if identity >= 0.05 or observed >= 0.10:
            budgets[family] = 4 if family != QueryFamily.ROLE else 2
        elif useful >= 0.25:
            budgets[family] = 3
        elif family == QueryFamily.COMPANY:
            budgets[family] = 4
        else:
            budgets[family] = 1
            if useful <= 0 and observed <= 0 and identity <= 0 and family != QueryFamily.COMPANY:
                disabled.append(family)
                budgets[family] = 0
    for family in QueryFamily:
        if family not in budgets:
            budgets[family] = 1 if family == QueryFamily.COMPANY else 0
            order.append(family)
    if QueryFamily.COMPANY in disabled:
        disabled.remove(QueryFamily.COMPANY)
        budgets[QueryFamily.COMPANY] = 4
    if QueryFamily.PERSON in disabled:
        disabled.remove(QueryFamily.PERSON)
        budgets[QueryFamily.PERSON] = max(budgets.get(QueryFamily.PERSON, 0), 2)
    if QueryFamily.ROLE in disabled:
        disabled.remove(QueryFamily.ROLE)
        budgets[QueryFamily.ROLE] = 1
    ranked_specific = tuple(
        family
        for family in order
        if family in {QueryFamily.COMPANY, QueryFamily.PERSON, QueryFamily.SITE_PATH, QueryFamily.DOCUMENT}
    ) or (QueryFamily.COMPANY, QueryFamily.PERSON, QueryFamily.SITE_PATH)
    return QueryPolicy(
        version=version,
        ranking_metric="identity_associated_per_search",
        family_order=tuple(order) or tuple(QueryFamily),
        family_budgets=budgets,
        disabled_families=frozenset(family for family in disabled if family != QueryFamily.ROLE),
        known_person_and_domain_families=ranked_specific,
    )


def build_report(
    *,
    n: int,
    policy: QueryPolicy,
    primary_name: str,
    primary_exec: list[QueryExecution],
    comparison_name: str | None,
    comparison_exec: list[QueryExecution] | None,
    cohort_meta: dict[str, Any],
    live_error: str | None,
) -> dict[str, Any]:
    primary_metrics = aggregate_executions(primary_exec)
    primary_metrics["backend"] = primary_name
    families = rank_families(primary_exec)
    queries = rank_queries(primary_exec)
    comparison_metrics = None
    uplift = None
    if comparison_exec is not None and comparison_name:
        comparison_metrics = aggregate_executions(comparison_exec)
        comparison_metrics["backend"] = comparison_name
        uplift = compare_backends(primary_metrics, comparison_metrics)
    derived = derive_policy(families, version=DEFAULT_POLICY_VERSION)
    return {
        "schema_id": "confenge.dui.query-yield-report.v1",
        "generated_at": now_iso(),
        "policy_version": policy.version,
        "derived_policy_version": derived.version,
        "n": n,
        "cohort": cohort_meta,
        "primary": primary_metrics,
        "comparison": comparison_metrics,
        "uplift": uplift,
        "families": families,
        "queries_ranked": queries,
        "top_queries": queries[:5],
        "bottom_queries": list(reversed(queries[-5:])) if queries else [],
        "operator_support": {
            "searxng": sorted(op.value for op in operators_for("searxng")),
            "ddgs": sorted(op.value for op in operators_for("ddgs")),
        },
        "weak_sources_separate": True,
        "ranking_metric": policy.ranking_metric,
        "live_error": live_error,
        "derived_policy": derived.to_dict(),
        "note": (
            "Ranking is downstream yield (useful pages / observed email / identity-associated), "
            "never SERP result count."
        ),
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    primary = report["primary"]
    lines = [
        f"# Query yield report — {report['policy_version']}",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- n: **{report['n']}** (requested {report['cohort'].get('requested')}, available {report['cohort'].get('available')})",
        f"- ranking: `{report['ranking_metric']}` (not SERP count)",
        f"- derived policy: `{report['derived_policy_version']}`",
        "",
        "## Primary backend",
        "",
        f"- backend: `{primary.get('backend')}`",
        f"- searches: {primary.get('searches')}",
        f"- useful pages/search: {primary.get('useful_pages_per_search')}",
        f"- observed email/search: {primary.get('observed_email_per_search')}",
        f"- identity-associated/search: {primary.get('identity_associated_per_search')}",
        f"- p50/p95 latency ms: {primary.get('latency_p50_ms')} / {primary.get('latency_p95_ms')}",
        f"- failures / 429: {primary.get('failures')} / {primary.get('http_429')}",
        f"- weak sources (separate): {primary.get('weak_sources')}",
        "",
    ]
    if report.get("comparison"):
        other = report["comparison"]
        uplift = report.get("uplift") or {}
        lines.extend(
            [
                "## SearXNG vs DDGS",
                "",
                f"- comparison backend: `{other.get('backend')}`",
                f"- observed email/search uplift: {uplift.get('observed_email_per_search')}",
                f"- identity-associated/search uplift: {uplift.get('identity_associated_per_search')}",
                f"- no_gain: **{uplift.get('no_gain')}**",
                "",
            ]
        )
    if report.get("live_error"):
        lines.extend(["## Live backends", "", "```", str(report["live_error"]), "```", ""])
    lines.extend(
        [
            "## Families (downstream yield)",
            "",
            "| family | searches | useful/s | observed/s | identity/s |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in report.get("families") or []:
        lines.append(
            f"| {row['family']} | {row['searches']} | {row['useful_pages_per_search']} | "
            f"{row['observed_email_per_search']} | {row['identity_associated_per_search']} |"
        )
    lines.extend(["", "## Top queries", ""])
    for row in report.get("top_queries") or []:
        lines.append(
            f"- `{row['shape_id']}` ({row['family']}): identity/s={row['identity_associated_per_search']} "
            f"observed/s={row['observed_email_per_search']} useful/s={row['useful_pages_per_search']}"
        )
    lines.extend(["", "## Bottom queries", ""])
    for row in report.get("bottom_queries") or []:
        lines.append(
            f"- `{row['shape_id']}` ({row['family']}): identity/s={row['identity_associated_per_search']} "
            f"observed/s={row['observed_email_per_search']} useful/s={row['useful_pages_per_search']}"
        )
    if report["cohort"].get("shortage"):
        lines.extend(["", "## Cohort note", "", report["cohort"]["shortage"], ""])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "query-yield-report.json"
    md_path = out_dir / "query-yield-report.md"
    policy_path = out_dir / f"{report['derived_policy_version']}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    policy_path.write_text(json.dumps(report["derived_policy"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path), "policy": str(policy_path)}


def try_live_backend(name: str, *, searxng_url: str | None, timeout_seconds: float):
    from scripts.decision_unit_intelligence.web_discovery import DdgsSearchBackend, SearxngSearchBackend

    if name == "searxng":
        if not searxng_url:
            raise LiveBackendError("searxng requires --searxng-url or CONFENGE_SEARXNG_URL", backend="searxng")
        return SearxngSearchBackend(searxng_url, timeout_seconds=timeout_seconds)
    if name == "ddgs":
        return DdgsSearchBackend(timeout_seconds=timeout_seconds)
    raise LiveBackendError(f"unsupported live backend: {name}", backend=name)


def run_query_yield(
    *,
    out_dir: Path,
    limit: int,
    policy_version: str,
    primary: str,
    compare: str | None,
    searxng_url: str | None,
    cache_dir: Path,
    results_per_query: int = 5,
    timeout_seconds: float = 8.0,
    allow_replay: bool = True,
) -> dict[str, Any]:
    policy = load_policy(policy_version)
    accounts, cohort_meta = load_benchmark_accounts(limit)
    cache = QuerySearchCache(JsonDiscoveryCache(cache_dir, ttl_days=7), policy_version=policy.version)
    live_error: str | None = None
    primary_backend = None
    compare_backend = None
    if primary not in {"replay", "replay-searxng", "replay-ddgs"}:
        try:
            primary_backend = try_live_backend(primary, searxng_url=searxng_url, timeout_seconds=timeout_seconds)
            primary_backend.search('"teste" email', limit=1)
        except Exception as exc:
            live_error = f"primary {primary} failed: {type(exc).__name__}:{exc}"
            if not allow_replay:
                raise LiveBackendError(live_error, backend=primary) from exc
            primary_backend = ObservationReplayBackend(accounts, simulate_backend=primary)
    else:
        simulated = "searxng" if primary != "replay-ddgs" else "ddgs"
        primary_backend = ObservationReplayBackend(accounts, simulate_backend=simulated)
    if compare and compare not in {"off", "none"}:
        if compare in {"replay", "replay-ddgs", "replay-searxng"}:
            simulated = "ddgs" if compare != "replay-searxng" else "searxng"
            compare_backend = ObservationReplayBackend(accounts, simulate_backend=simulated)
        else:
            try:
                compare_backend = try_live_backend(compare, searxng_url=searxng_url, timeout_seconds=timeout_seconds)
                compare_backend.search('"teste" email', limit=1)
            except Exception as exc:
                extra = f"compare {compare} failed: {type(exc).__name__}:{exc}"
                live_error = f"{live_error}; {extra}" if live_error else extra
                if allow_replay:
                    compare_backend = ObservationReplayBackend(accounts, simulate_backend=compare)
                else:
                    compare_backend = None
    primary_exec = run_backend_benchmark(
        accounts,
        backend=primary_backend,
        policy=policy,
        cache=cache,
        results_per_query=results_per_query,
    )
    comparison_exec = None
    if compare_backend is not None:
        comparison_exec = run_backend_benchmark(
            accounts,
            backend=compare_backend,
            policy=policy,
            cache=cache,
            results_per_query=results_per_query,
        )
    report = build_report(
        n=len(accounts),
        policy=policy,
        primary_name=getattr(primary_backend, "backend_id", primary),
        primary_exec=primary_exec,
        comparison_name=getattr(compare_backend, "backend_id", compare) if compare_backend else None,
        comparison_exec=comparison_exec,
        cohort_meta=cohort_meta,
        live_error=live_error,
    )
    paths = write_report(report, out_dir)
    report["paths"] = paths
    return report
