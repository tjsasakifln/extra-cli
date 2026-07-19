"""Canonical indicator catalog — fail-closed metric claims.

Any metric name not registered here must not be used for consultive claims.
Definitions separate presence, success_zero, coverage, freshness, recall,
commercial signal, completeness, and quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class IndicatorDefinition:
    name: str
    formula: str
    numerator: str
    denominator: str
    source: str
    time_window: str
    sla: str
    exclusions: str
    state: str  # ACTIVE | DRAFT | DEPRECATED
    evidence: str
    claims_allowed: tuple[str, ...]
    claims_forbidden: tuple[str, ...]


INDICATOR_CATALOG: dict[str, IndicatorDefinition] = {
    "universe_denominator": IndicatorDefinition(
        name="universe_denominator",
        formula="COUNT(sc_public_entities WHERE raio_200km AND is_active)",
        numerator="n/a (count is the measure)",
        denominator="fixed strategic universe from Extra spreadsheet",
        source="sc_public_entities",
        time_window="point-in-time",
        sla="must equal 1093 unless formal scope change by Tiago",
        exclusions="entities outside 200km radius",
        state="ACTIVE",
        evidence="SQL count on active raio_200km entities",
        claims_allowed=("universe size for Extra targets",),
        claims_forbidden=("coverage %", "recall %"),
    ),
    "presence": IndicatorDefinition(
        name="presence",
        formula="entities with ≥1 record in source table",
        numerator="entities with any matching row",
        denominator="universe_denominator",
        source="per-source tables",
        time_window="all history unless filtered",
        sla="not a freshness SLA",
        exclusions="success_zero alone is NOT presence",
        state="ACTIVE",
        evidence="entity keys joined to source rows",
        claims_allowed=("entity has at least one historical record",),
        claims_forbidden=(
            "operational coverage",
            "freshness",
            "95% ready",
        ),
    ),
    "success_zero": IndicatorDefinition(
        name="success_zero",
        formula="official query executed, scope complete, zero results, verifiable",
        numerator="entities/scopes with audited empty official response",
        denominator="scopes attempted",
        source="collection run evidence",
        time_window="run period",
        sla="only valid when request_completed AND scope_complete",
        exclusions="timeout, interrupt, cache-only, missing query",
        state="ACTIVE",
        evidence="CollectionRun.terminal_status=success_zero + raw proof",
        claims_allowed=("official API returned zero for this scope",),
        claims_forbidden=("entity has contracts", "coverage complete"),
    ),
    "contracts_ops_proxy": IndicatorDefinition(
        name="contracts_ops_proxy",
        formula="presence ∪ entity success_zero (contracts sources only)",
        numerator="entities with presence OR audited success_zero",
        denominator="universe_denominator",
        source="pncp contracts + success_zero probes",
        time_window="campaign-defined",
        sla="proxy only — not 7-stage coverage",
        exclusions="editais, acts, payments stages",
        state="ACTIVE",
        evidence="EXTRA-OPS-95 measurement artifacts",
        claims_allowed=("contracts operational proxy under stated definition",),
        claims_forbidden=(
            "full operational coverage",
            "cobertura operacional completa",
            "cobertura operacional de 95%",
            "editais 95%",
            "LOCAL_READY",
        ),
    ),
    "freshness_source": IndicatorDefinition(
        name="freshness_source",
        formula="last successful collection age ≤ SLA hours",
        numerator="sources with last success within SLA",
        denominator="critical sources for the product",
        source="pipeline_runs / opportunity_runs / ingestion_runs",
        time_window="SLA hours per source",
        sla="pncp opportunities default 48h; contracts default 168h",
        exclusions="failed runs; fixture runs; incomplete scope",
        state="ACTIVE",
        evidence="weekly_cycle source_health block",
        claims_allowed=("source data age relative to SLA",),
        claims_forbidden=("recall", "coverage %"),
    ),
    "open_opportunities_count": IndicatorDefinition(
        name="open_opportunities_count",
        formula="COUNT(opportunity_intel WHERE is_active AND status_canonico IN open,upcoming)",
        numerator="active open/upcoming rows",
        denominator="n/a",
        source="opportunity_intel",
        time_window="current snapshot",
        sla="refresh via weekly collect or reuse_fresh",
        exclusions="closed/revoked; inactive rows",
        state="ACTIVE",
        evidence="SQL on opportunity_intel",
        claims_allowed=("count of tracked open opportunities in lake",),
        claims_forbidden=("all market opportunities", "complete recall"),
    ),
    "ranking_distribution": IndicatorDefinition(
        name="ranking_distribution",
        formula="COUNT by ranking IN (GO, REVIEW, NO_GO)",
        numerator="opportunities per bucket",
        denominator="active opportunities in scope",
        source="opportunity_intel.ranking",
        time_window="current snapshot",
        sla="GO requires complete Extra profile factors",
        exclusions="scores as probabilities",
        state="ACTIVE",
        evidence="ranking columns + ranking_confianca",
        claims_allowed=("triage buckets for Extra review",),
        claims_forbidden=(
            "probability of win",
            "calibrated confidence without calibration study",
        ),
    ),
    "commercial_signal": IndicatorDefinition(
        name="commercial_signal",
        formula="entities_with_recent_commercial_signal",
        numerator="entities with recent opp/contract signal",
        denominator="universe_denominator",
        source="opportunity_intel + contracts",
        time_window="recent window (e.g. 90d)",
        sla="signal only",
        exclusions="must not be labeled coverage",
        state="ACTIVE",
        evidence="coverage_truth commercial signal path",
        claims_allowed=("recent commercial activity signal",),
        claims_forbidden=("operational coverage", "95% coverage"),
    ),
    "recall_independent": IndicatorDefinition(
        name="recall_independent",
        formula="hits on independent gold sample / gold sample size",
        numerator="gold items found by system",
        denominator="independent stratified gold sample",
        source="manual gold + system match",
        time_window="sample period",
        sla="blocked until gold sample exists",
        exclusions="self-derived samples from the same crawl",
        state="DRAFT",
        evidence="not proven in this campaign",
        claims_allowed=(),
        claims_forbidden=("recall ≥95%", "complete capture"),
    ),
}


def get_indicator(name: str) -> IndicatorDefinition:
    if name not in INDICATOR_CATALOG:
        raise KeyError(
            f"Unknown indicator {name!r}. Metrics without catalog entry fail closed."
        )
    return INDICATOR_CATALOG[name]


def validate_metric_claim(metric_name: str, claim: str) -> dict[str, Any]:
    """Return pass/fail for a claim against the catalog."""
    try:
        ind = get_indicator(metric_name)
    except KeyError as exc:
        return {
            "ok": False,
            "metric": metric_name,
            "claim": claim,
            "reason": str(exc),
        }
    forbidden = any(f.lower() in claim.lower() for f in ind.claims_forbidden)
    if forbidden:
        return {
            "ok": False,
            "metric": metric_name,
            "claim": claim,
            "reason": "claim matches forbidden language for this indicator",
            "definition": asdict(ind),
        }
    return {
        "ok": True,
        "metric": metric_name,
        "claim": claim,
        "definition": asdict(ind),
    }


def catalog_as_list() -> list[dict[str, Any]]:
    return [asdict(v) for v in INDICATOR_CATALOG.values()]
