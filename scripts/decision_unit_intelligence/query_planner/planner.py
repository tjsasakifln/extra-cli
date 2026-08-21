"""Adaptive query planner: budget, early-stop, dedupe, policy selection.

Does not perform crawl/extraction. The executor only calls SearchBackend.search.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.query_planner.spec import (
    BASELINE_POLICY_VERSION,
    DEFAULT_POLICY_VERSION,
    QueryExecution,
    QueryFamily,
    QueryPlan,
    QueryPolicy,
    QuerySpec,
    cache_key,
    emit_query_specs,
    normalize_query,
    unsupported_operators,
)
from scripts.decision_unit_intelligence.query_planner.yield_eval import apply_yield, evaluate_serp_yield
from scripts.decision_unit_intelligence.web_discovery import JsonDiscoveryCache, SearchHit

POLICY_DIR = Path(__file__).resolve().parents[1] / "data" / "query_policies"

KNOWN_PERSON_AND_DOMAIN = "known_person_and_domain"
UNKNOWN_DOMAIN = "unknown_domain"
KNOWN_DOMAIN_ONLY = "known_domain_only"


class SearchBackendLike(Protocol):
    backend_id: str

    def search(self, query: str, *, limit: int) -> list[SearchHit]: ...


class QueryPlannerError(Exception):
    """Visible backend/planner failure. Never converted to an empty miss."""

    def __init__(self, message: str, *, backend: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.backend = backend
        self.status_code = status_code


@dataclass
class QuerySearchCache:
    store: JsonDiscoveryCache
    policy_version: str
    hits: int = 0
    misses: int = 0

    def get(self, *, backend: str, query: str, limit: int) -> list[SearchHit] | None:
        key = cache_key(query=query, backend=backend, policy_version=self.policy_version, limit=limit)
        cached = self.store.get("query-planner", key)
        if cached is None:
            self.misses += 1
            return None
        self.hits += 1
        return [SearchHit(**row) for row in cached]

    def set(self, *, backend: str, query: str, limit: int, hits: list[SearchHit]) -> None:
        key = cache_key(query=query, backend=backend, policy_version=self.policy_version, limit=limit)
        self.store.set(
            "query-planner",
            key,
            [{"url": hit.url, "title": hit.title, "snippet": hit.snippet, "engine": hit.engine} for hit in hits],
        )


@dataclass
class FallbackEvent:
    primary: str
    secondary: str
    query: str
    error: str
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "query": self.query,
            "error": self.error,
            "status_code": self.status_code,
            "silent": False,
        }


@dataclass
class ExplicitFallbackBackend:
    """Primary → secondary. Failures stay visible; never return [] as a miss."""

    primary: SearchBackendLike
    secondary: SearchBackendLike
    events: list[FallbackEvent] = field(default_factory=list)

    @property
    def backend_id(self) -> str:
        return self.primary.backend_id

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        try:
            return self.primary.search(query, limit=limit)
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "response", None)
            status_code = (
                getattr(status, "status_code", None) if status is not None and not isinstance(status, int) else status
            )
            self.events.append(
                FallbackEvent(
                    primary=self.primary.backend_id,
                    secondary=self.secondary.backend_id,
                    query=query,
                    error=f"{type(exc).__name__}:{exc}",
                    status_code=int(status_code) if status_code else None,
                )
            )
            return self.secondary.search(query, limit=limit)


def baseline_policy() -> QueryPolicy:
    return QueryPolicy(
        version=BASELINE_POLICY_VERSION,
        family_order=(
            QueryFamily.COMPANY,
            QueryFamily.PERSON,
            QueryFamily.ROLE,
            QueryFamily.DOCUMENT,
            QueryFamily.SITE_PATH,
        ),
        family_budgets={
            QueryFamily.COMPANY: 4,
            QueryFamily.PERSON: 8,
            QueryFamily.ROLE: 6,
            QueryFamily.DOCUMENT: 5,
            QueryFamily.SITE_PATH: 4,
        },
        disabled_families=frozenset(),
    )


def default_policy() -> QueryPolicy:
    return load_policy(DEFAULT_POLICY_VERSION)


def load_policy(version: str | None = None) -> QueryPolicy:
    name = version or DEFAULT_POLICY_VERSION
    path = POLICY_DIR / f"{name}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return QueryPolicy.from_dict(payload)
    if name == BASELINE_POLICY_VERSION:
        return baseline_policy()
    if name == DEFAULT_POLICY_VERSION:
        return _shipped_v2_fallback()
    raise FileNotFoundError(f"unknown query policy version: {name}")


def write_policy(policy: QueryPolicy, path: Path | None = None) -> Path:
    target = path or (POLICY_DIR / f"{policy.version}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(policy.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _shipped_v2_fallback() -> QueryPolicy:
    """Used only if the versioned artifact is missing. Prefer the JSON on disk."""
    return QueryPolicy(
        version=DEFAULT_POLICY_VERSION,
        family_order=(
            QueryFamily.SITE_PATH,
            QueryFamily.COMPANY,
            QueryFamily.PERSON,
            QueryFamily.DOCUMENT,
            QueryFamily.ROLE,
        ),
        family_budgets={
            QueryFamily.COMPANY: 4,
            QueryFamily.PERSON: 4,
            QueryFamily.ROLE: 1,
            QueryFamily.DOCUMENT: 2,
            QueryFamily.SITE_PATH: 4,
        },
        disabled_families=frozenset(),
    )


def adaptive_mode(*, known_domain: str | None, known_people: list[str]) -> str:
    if known_domain and known_people:
        return KNOWN_PERSON_AND_DOMAIN
    if known_domain:
        return KNOWN_DOMAIN_ONLY
    return UNKNOWN_DOMAIN


def plan_queries(
    context: InvestigationContext,
    *,
    policy: QueryPolicy | None = None,
    known_domain: str | None = None,
    known_people: list[str] | None = None,
    trade_name: str | None = None,
    max_queries: int | None = None,
) -> QueryPlan:
    chosen = policy or default_policy()
    people = [
        name
        for name in (known_people if known_people is not None else list(context.extra.get("known_people") or []))
        if name
    ]
    specs = emit_query_specs(
        context,
        known_domain=known_domain,
        known_people=people,
        trade_name=trade_name,
        policy_version=chosen.version,
    )
    mode = adaptive_mode(known_domain=known_domain, known_people=people)
    selected = select_specs(specs, policy=chosen, mode=mode, max_queries=max_queries)
    return QueryPlan(
        policy_version=chosen.version,
        account_id=str(context.cnpj or ""),
        known_domain=known_domain,
        known_people=tuple(people),
        specs=tuple(selected),
        adaptive_mode=mode,
    )


def select_specs(
    specs: list[QuerySpec],
    *,
    policy: QueryPolicy,
    mode: str,
    max_queries: int | None = None,
) -> list[QuerySpec]:
    allowed = _allowed_families(policy, mode)
    order = {family: index for index, family in enumerate(_family_sequence(policy, mode))}
    usable = [spec for spec in specs if spec.family in allowed and spec.family not in policy.disabled_families]
    usable.sort(key=lambda spec: (order.get(spec.family, 99), spec.shape_id, spec.query))
    budgets = dict(policy.family_budgets)
    used: dict[QueryFamily, int] = {family: 0 for family in QueryFamily}
    selected: list[QuerySpec] = []
    seen: set[str] = set()
    for spec in usable:
        key = normalize_query(spec.query)
        if key in seen:
            continue
        cap = budgets.get(spec.family)
        if cap is not None and used[spec.family] >= cap:
            continue
        selected.append(spec)
        seen.add(key)
        used[spec.family] += 1
        if max_queries is not None and len(selected) >= max_queries:
            break
    return selected


def _family_sequence(policy: QueryPolicy, mode: str) -> tuple[QueryFamily, ...]:
    if mode == KNOWN_PERSON_AND_DOMAIN:
        return policy.known_person_and_domain_families
    if mode == UNKNOWN_DOMAIN:
        return policy.unknown_domain_families
    return policy.family_order


def _allowed_families(policy: QueryPolicy, mode: str) -> set[QueryFamily]:
    if mode == KNOWN_PERSON_AND_DOMAIN:
        return set(policy.known_person_and_domain_families) | {QueryFamily.SITE_PATH}
    if mode == UNKNOWN_DOMAIN:
        return set(policy.unknown_domain_families) | {QueryFamily.COMPANY}
    return {QueryFamily.SITE_PATH, QueryFamily.COMPANY, QueryFamily.DOCUMENT, QueryFamily.ROLE}


def should_early_stop(executions: list[QueryExecution], policy: QueryPolicy) -> bool:
    ran = [row for row in executions if row.executed]
    if not ran:
        return False
    identity = sum(row.identity_associated_count for row in ran)
    observed = sum(row.observed_email_count for row in ran)
    control_eligible = sum(getattr(row, "control_eligible_email_count", 0) for row in ran)
    if identity >= policy.min_identity_associated:
        return True
    if control_eligible >= policy.min_control_eligible_email:
        return True
    if observed >= policy.min_observed_email:
        return True
    streak = 0
    for row in reversed(ran):
        if row.downstream_yield == 0:
            streak += 1
            continue
        break
    return streak >= policy.max_zero_yield_streak


@dataclass
class PlanRun:
    executions: list[QueryExecution]
    hits: list[SearchHit]


def execute_plan(
    plan: QueryPlan,
    backend: SearchBackendLike,
    *,
    policy: QueryPolicy,
    cache: QuerySearchCache | None = None,
    limit: int = 5,
    legal_name: str | None = None,
    known_people: list[str] | None = None,
) -> PlanRun:
    executions: list[QueryExecution] = []
    collected: list[SearchHit] = []
    seen: set[str] = set()
    stopped = False
    for spec in plan.specs:
        key = normalize_query(spec.query)
        if key in seen:
            executions.append(QueryExecution(spec=spec, backend=backend.backend_id, skip_reason="duplicate"))
            continue
        seen.add(key)
        if stopped:
            executions.append(QueryExecution(spec=spec, backend=backend.backend_id, skip_reason="early_stop"))
            continue
        missing = unsupported_operators(spec, backend.backend_id)
        if missing:
            executions.append(
                QueryExecution(
                    spec=spec,
                    backend=backend.backend_id,
                    skip_reason="unsupported_operator",
                    failure=f"unsupported_operator:{','.join(op.value for op in missing)}",
                )
            )
            continue
        row = QueryExecution(spec=spec, backend=backend.backend_id)
        started = perf_counter()
        try:
            hits = None
            if cache is not None:
                hits = cache.get(backend=backend.backend_id, query=spec.query, limit=limit)
                row.cache_hit = hits is not None
            if hits is None:
                hits = backend.search(spec.query, limit=limit)
                if cache is not None:
                    cache.set(backend=backend.backend_id, query=spec.query, limit=limit, hits=hits)
            row.executed = True
            row.result_count = len(hits)
            collected.extend(hits)
            apply_yield(
                row,
                evaluate_serp_yield(
                    hits,
                    legal_name=legal_name,
                    known_domain=plan.known_domain,
                    known_people=list(known_people or plan.known_people),
                ),
            )
        except Exception as exc:
            row.executed = True
            row.failure = f"{type(exc).__name__}:{exc}"
            row.http_status = _status_code(exc)
        row.latency_ms = int((perf_counter() - started) * 1000)
        executions.append(row)
        if should_early_stop(executions, policy):
            stopped = True
    return PlanRun(executions=executions, hits=collected)


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if code:
            return int(code)
    code = getattr(exc, "status_code", None)
    return int(code) if code else None
