"""Durable fail-closed crawl/pipeline factory spine.

Public contracts for discovery, coverage, jobs, raw archive, portal
adaptation, freshness enqueue, leased workers, domain resilience,
document versions and structured failures.

Refs #235 #236 #246 #247 #256 #268 #269 #270 #272 #279
"""

from scripts.factory_spine.contracts import (
    CANONICAL_UNIVERSE_SIZE,
    COVERAGE_TERMINALS,
    DISCOVERY_TERMINALS,
    JOB_TERMINALS,
    apply_surface_revalidation,
    assert_publishable_coverage,
    build_pncp_consulta_envelope,
    canonical_entity_ids,
    classify_discovery_surface,
    decide_resilience,
    plan_freshness_enqueue,
    publish_coverage_cell,
    rank_claim_candidates,
    reconcile_coverage_artifacts,
    seal_discovery_run,
    window_is_complete,
)
from scripts.factory_spine.portal import interpret_portal_fetch
from scripts.factory_spine.runtime import FactoryStore, launch_spine
from scripts.factory_spine.store import persist_document_metadata

__all__ = [
    "CANONICAL_UNIVERSE_SIZE",
    "COVERAGE_TERMINALS",
    "DISCOVERY_TERMINALS",
    "JOB_TERMINALS",
    "FactoryStore",
    "apply_surface_revalidation",
    "assert_publishable_coverage",
    "build_pncp_consulta_envelope",
    "canonical_entity_ids",
    "classify_discovery_surface",
    "decide_resilience",
    "interpret_portal_fetch",
    "launch_spine",
    "persist_document_metadata",
    "plan_freshness_enqueue",
    "publish_coverage_cell",
    "rank_claim_candidates",
    "reconcile_coverage_artifacts",
    "seal_discovery_run",
    "window_is_complete",
]
