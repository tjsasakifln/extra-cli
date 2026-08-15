"""Yield-driven public-search query planner.

Consumable by the #393 batch via policy version. SearXNG is primary; DDGS is
an explicit comparison. Fallback is never silent.
"""

from scripts.decision_unit_intelligence.query_planner.planner import (
    ExplicitFallbackBackend,
    PlanRun,
    QueryPlannerError,
    QuerySearchCache,
    adaptive_mode,
    default_policy,
    execute_plan,
    load_policy,
    plan_queries,
    should_early_stop,
    write_policy,
)
from scripts.decision_unit_intelligence.query_planner.spec import (
    DEFAULT_POLICY_VERSION,
    QUERY_PLANNER_SCHEMA,
    QueryExecution,
    QueryFamily,
    QueryPlan,
    QueryPolicy,
    QuerySpec,
    emit_query_specs,
    normalize_query,
    operators_for,
    unsupported_operators,
)
from scripts.decision_unit_intelligence.query_planner.yield_eval import (
    aggregate_executions,
    evaluate_serp_yield,
    rank_families,
    rank_queries,
)

__all__ = [
    "DEFAULT_POLICY_VERSION",
    "QUERY_PLANNER_SCHEMA",
    "ExplicitFallbackBackend",
    "PlanRun",
    "QueryExecution",
    "QueryFamily",
    "QueryPlan",
    "QueryPlannerError",
    "QueryPolicy",
    "QuerySearchCache",
    "QuerySpec",
    "adaptive_mode",
    "aggregate_executions",
    "default_policy",
    "emit_query_specs",
    "evaluate_serp_yield",
    "execute_plan",
    "load_policy",
    "normalize_query",
    "operators_for",
    "plan_queries",
    "rank_families",
    "rank_queries",
    "should_early_stop",
    "unsupported_operators",
    "write_policy",
]
