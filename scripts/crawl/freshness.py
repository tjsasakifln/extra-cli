"""Freshness Evaluator — determines data freshness per source.

Integrates with ``entity_coverage`` table and provenance SLA thresholds.
Provides:
- ``evaluate_freshness()``: Evaluate freshness per source/entity.
- ``refresh_coverage_state()``: Update coverage state after crawl.
- ``format_freshness_report()``: Human-readable report for ``--freshness`` CLI.

SLA thresholds defined in ``scripts.crawl.provenance.SOURCE_SLA``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from scripts.crawl.provenance import DEFAULT_SLA_HOURS, SOURCE_SLA

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

FreshnessLevel = str  # "fresh" | "stale" | "unknown" | "never_crawled"

FRESHNESS_ORDER = {"fresh": 0, "stale": 1, "unknown": 2, "never_crawled": 3}


class SourceFreshness:
    """Freshness status for a single source."""

    def __init__(
        self,
        source: str,
        level: FreshnessLevel = "unknown",
        last_seen: str | None = None,
        sla_hours: int = DEFAULT_SLA_HOURS,
        coverage_pct: float = 0.0,
        total_entities: int = 0,
        covered_entities: int = 0,
    ):
        self.source = source
        self.level = level
        self.last_seen = last_seen
        self.sla_hours = sla_hours
        self.coverage_pct = coverage_pct
        self.total_entities = total_entities
        self.covered_entities = covered_entities

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "level": self.level,
            "last_seen": self.last_seen,
            "sla_hours": self.sla_hours,
            "coverage_pct": round(self.coverage_pct, 1),
            "total_entities": self.total_entities,
            "covered_entities": self.covered_entities,
        }


# ---------------------------------------------------------------------------
# Freshness Evaluation
# ---------------------------------------------------------------------------


def _get_sla(source: str) -> int:
    """Return SLA threshold in hours for a source."""
    return SOURCE_SLA.get(source, DEFAULT_SLA_HOURS)


def evaluate_freshness(conn: Any, source: str | None = None) -> dict[str, SourceFreshness]:
    """Evaluate freshness per source from entity_coverage table.

    Args:
        conn: Database connection.
        source: Optional source filter. If None, evaluates all sources.

    Returns:
        Dict mapping source name to SourceFreshness.
    """
    cur = conn.cursor()
    now = datetime.now(UTC)

    if source:
        cur.execute(
            """SELECT ec.source, MAX(ec.last_seen_at),
                      COUNT(e.id) FILTER (WHERE e.is_active) as total,
                      COUNT(ec.entity_id) as covered
               FROM entity_coverage ec
               JOIN sc_public_entities e ON e.id = ec.entity_id
               WHERE ec.source = %s
               GROUP BY ec.source""",
            (source,),
        )
    else:
        cur.execute(
            """SELECT ec.source, MAX(ec.last_seen_at),
                      COUNT(e.id) FILTER (WHERE e.is_active) as total,
                      COUNT(ec.entity_id) as covered
               FROM entity_coverage ec
               JOIN sc_public_entities e ON e.id = ec.entity_id
               GROUP BY ec.source"""
        )

    results: dict[str, SourceFreshness] = {}
    for row in cur.fetchall():
        src, last_seen, total, covered = row
        sla_h = _get_sla(src)
        level: FreshnessLevel = "unknown"

        if last_seen:
            hours_since = (now - last_seen.replace(tzinfo=UTC)).total_seconds() / 3600
            level = "fresh" if hours_since < sla_h else "stale"
        else:
            level = "never_crawled"

        coverage_pct = (covered / total * 100) if total > 0 else 0.0
        results[src] = SourceFreshness(
            source=src,
            level=level,
            last_seen=last_seen.isoformat() if last_seen else None,
            sla_hours=sla_h,
            coverage_pct=coverage_pct,
            total_entities=total,
            covered_entities=covered,
        )

    cur.close()
    return results


def refresh_coverage_state(conn: Any, source: str, records_fetched: int) -> dict:
    """Update coverage_evidence state after a crawl run.

    This is called after each crawl to update the coverage state machine.
    The entity_coverage table is the source of truth for coverage state.

    Args:
        conn: Database connection.
        source: Source tag that was crawled.
        records_fetched: Number of records fetched in this run.

    Returns:
        Dict with 'source', 'status', 'records_fetched', 'freshness'.
    """
    freshness = evaluate_freshness(conn, source=source)
    src_fresh = freshness.get(source)

    return {
        "source": source,
        "status": "refreshed",
        "records_fetched": records_fetched,
        "freshness": src_fresh.to_dict() if src_fresh else {"level": "unknown"},
    }


def format_freshness_report(conn: Any) -> str:
    """Generate a human-readable freshness report for --freshness CLI.

    Args:
        conn: Database connection.

    Returns:
        Formatted string with per-source freshness status.
    """
    results = evaluate_freshness(conn)
    if not results:
        return "No coverage data found."

    lines = ["Freshness Report", "=" * 60]
    for src in sorted(results.keys(), key=lambda s: FRESHNESS_ORDER.get(results[s].level, 99)):
        f = results[src]
        icon = {"fresh": "OK", "stale": "STALE", "unknown": "?", "never_crawled": "NEVER"}.get(f.level, "?")
        lines.append(
            f"  {icon} {f.source:20s}  {f.level:15s}  "
            f"last={f.last_seen or 'never':25s}  "
            f"coverage={f.coverage_pct:5.1f}%  "
            f"SLA={f.sla_hours}h"
        )

    fresh_count = sum(1 for f in results.values() if f.level == "fresh")
    stale_count = sum(1 for f in results.values() if f.level in ("stale", "never_crawled"))
    lines.append("=" * 60)
    lines.append(f"  {fresh_count} fresh  |  {stale_count} stale/never  |  {len(results)} total sources")
    return "\n".join(lines)
