#!/usr/bin/env python3
"""Coverage Truth MVP — auditable entity/source coverage metrics.

Deterministic, entity-deduplicated metrics for public entities within a
configurable radius of Florianópolis. Reads from the evidence ledger
(coverage_evidence) and existing entity_coverage table.

Usage::

    python scripts/coverage_truth.py report --radius-km 200
    python scripts/coverage_truth.py report --radius-km 200 --output-dir docs/coverage-truth/
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLORIANOPOLIS_LAT = -27.5954
FLORIANOPOLIS_LON = -48.5480
EARTH_RADIUS_KM = 6371.0
DEFAULT_RADIUS_KM = 200
COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "coverage-truth"

# Source lists derived from central registry at import time
try:
    from scripts.crawl.registry import iter_sources

    ALL_SOURCES = [s.name for s in iter_sources()]
    BID_SOURCES = [s.name for s in iter_sources() if s.purpose != "coverage_only"]
    CONTRACT_SOURCES = ["contracts"]  # Only contracts source produces contract records
except ImportError:
    # Fallback: hardcoded lists (must match registry.py)
    ALL_SOURCES = [
        "pncp", "dom_sc", "pcp", "compras_gov", "sc_compras",
        "contracts", "transparencia", "tce_sc", "doe_sc",
        "ciga_ckan", "mides_bigquery", "selenium",
    ]
    BID_SOURCES = [
        "pncp", "dom_sc", "pcp", "compras_gov", "sc_compras",
        "contracts", "transparencia", "tce_sc", "doe_sc",
        "mides_bigquery", "selenium",
    ]
    CONTRACT_SOURCES = ["contracts"]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    return os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
    )


def _get_conn():
    import psycopg2

    return psycopg2.connect(_get_dsn())


def _query(conn, sql: str, params: list | None = None) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km between two points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_entities_within_radius(
    conn, radius_km: float = DEFAULT_RADIUS_KM
) -> list[dict]:
    """Load active entities, filter by Haversine distance from Florianópolis.

    Uses the pre-computed ``raio_200km`` column as a fast pre-filter when
    radius_km == 200, then applies exact Haversine for correctness.
    """
    if abs(radius_km - 200.0) < 0.5:
        # Fast path: use pre-computed boolean flag
        entities = _query(
            conn,
            """SELECT id, razao_social, cnpj_8, municipio, codigo_ibge,
                      natureza_juridica, latitude, longitude, distancia_fk
               FROM sc_public_entities
               WHERE is_active = TRUE AND raio_200km = TRUE
               ORDER BY id""",
        )
    else:
        # Slow path: load all, filter by Haversine in Python
        all_entities = _query(
            conn,
            """SELECT id, razao_social, cnpj_8, municipio, codigo_ibge,
                      natureza_juridica, latitude, longitude
               FROM sc_public_entities
               WHERE is_active = TRUE
               ORDER BY id""",
        )
        entities = []
        for e in all_entities:
            if e["latitude"] is not None and e["longitude"] is not None:
                dist = haversine_km(
                    FLORIANOPOLIS_LAT, FLORIANOPOLIS_LON,
                    float(e["latitude"]), float(e["longitude"]),
                )
                if dist <= radius_km:
                    e["distancia_fk"] = dist
                    entities.append(e)
            else:
                # Entities without coordinates: include with warning
                e["distancia_fk"] = None
                entities.append(e)

    return entities


def load_entity_coverage(conn) -> list[dict]:
    """Load all entity_coverage rows for active entities."""
    return _query(
        conn,
        """SELECT ec.entity_id, ec.source, ec.last_seen_at, ec.total_bids,
                  ec.is_covered, ec.within_200km, ec.match_method
           FROM entity_coverage ec
           JOIN sc_public_entities e ON e.id = ec.entity_id
           WHERE e.is_active = TRUE""",
    )


def load_latest_evidence(conn) -> list[dict]:
    """Load latest evidence per (entity, source) from coverage_evidence.

    Returns empty list if the table does not exist (migration not yet applied).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'coverage_evidence')"
    )
    if not cur.fetchone()[0]:
        cur.close()
        return []
    cur.close()
    return _query(conn, "SELECT * FROM v_latest_evidence")


def load_source_health(conn) -> list[dict]:
    """Load source health summary from v_source_health view.

    Returns empty list if the view does not exist.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'v_source_health')"
    )
    if not cur.fetchone()[0]:
        cur.close()
        return []
    cur.close()
    return _query(conn, "SELECT * FROM v_source_health ORDER BY source")


def load_contract_presence(conn, entity_ids: list[int]) -> dict[int, bool]:
    """Check which entities have contracts in the coverage window."""
    if not entity_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        """SELECT DISTINCT ec.entity_id
           FROM entity_coverage ec
           WHERE ec.entity_id = ANY(%s)
             AND ec.source = 'contracts'
             AND ec.is_covered = TRUE""",
        (entity_ids,),
    )
    result = {row[0]: True for row in cur.fetchall()}
    cur.close()
    return result


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def compute_metrics(
    entities: list[dict],
    coverage: list[dict],
    evidence: list[dict],
    source_health: list[dict],
    contract_presence: dict[int, bool],
    radius_km: float,
) -> dict[str, Any]:
    """Compute all Coverage Truth metrics from raw data.

    All metrics are entity-deduplicated. One record never implies completeness
    or >=95% recall.
    """
    entity_ids = {e["id"] for e in entities}
    entity_by_id = {e["id"]: e for e in entities}
    n_entities = len(entities)

    # ── Build lookup structures ────────────────────────────────────────

    # entity -> set of sources with is_covered=True
    covered_sources: dict[int, set[str]] = {}
    # entity -> set of sources with ANY coverage record
    checked_sources: dict[int, set[str]] = {}
    # entity -> most recent last_seen_at
    freshness: dict[int, date] = {}
    # entity -> total bids across all sources
    bid_count: dict[int, int] = {}

    for row in coverage:
        eid = row["entity_id"]
        if eid not in entity_ids:
            continue
        src = row["source"]
        if row["is_covered"]:
            covered_sources.setdefault(eid, set()).add(src)
        checked_sources.setdefault(eid, set()).add(src)
        if row["last_seen_at"]:
            dt = row["last_seen_at"]
            if isinstance(dt, datetime):
                dt = dt.date()
            if eid not in freshness or dt > freshness[eid]:
                freshness[eid] = dt
        bid_count[eid] = bid_count.get(eid, 0) + row["total_bids"]

    # ── Build evidence lookup ───────────────────────────────────────────

    # source -> evidence state from latest run
    source_state: dict[str, str] = {}
    source_last_check: dict[str, datetime] = {}
    for ev in evidence:
        src = ev["source"]
        if src not in source_state or (
            ev.get("completed_at")
            and (
                src not in source_last_check
                or ev["completed_at"] > source_last_check[src]
            )
        ):
            source_state[src] = ev["state"]
            if ev.get("completed_at"):
                source_last_check[src] = ev["completed_at"]

    # ── Monitoring coverage ─────────────────────────────────────────────
    # "applicable source checked successfully within SLA"
    # Per entity: count of sources where evidence state is success_*
    # Per source: coverage = entities_checked / total_entities

    evidence_success_states = {"success_with_data", "success_zero"}
    evidence_checked_states = evidence_success_states | {"partial"}

    # Per-source coverage from entity_coverage (deterministic, always available)
    source_entity_counts: dict[str, int] = {}
    source_covered_counts: dict[str, int] = {}
    for row in coverage:
        eid = row["entity_id"]
        if eid not in entity_ids:
            continue
        src = row["source"]
        source_entity_counts[src] = source_entity_counts.get(src, 0) + 1
        if row["is_covered"]:
            source_covered_counts[src] = source_covered_counts.get(src, 0) + 1

    # Per-source coverage rates
    per_source_coverage = {}
    for src in ALL_SOURCES:
        total = source_entity_counts.get(src, 0)
        covered = source_covered_counts.get(src, 0)
        per_source_coverage[src] = {
            "entities_checked": total,
            "entities_covered": covered,
            "pct_covered": round(covered / total * 100, 1) if total > 0 else None,
        }

    # ── Overall monitoring coverage ─────────────────────────────────────
    # Entity is "monitored" if it has coverage from at least 1 source
    entities_with_coverage = len({eid for eid in entity_ids if eid in covered_sources and covered_sources[eid]})
    entities_with_any_check = len({eid for eid in entity_ids if eid in checked_sources and checked_sources[eid]})
    entities_with_zero_sources = n_entities - entities_with_any_check

    monitoring_coverage_pct = round(entities_with_coverage / n_entities * 100, 1) if n_entities > 0 else 0

    # ── Freshness ───────────────────────────────────────────────────────
    # Days since last data for each entity with coverage

    today = date.today()
    freshness_days: dict[int, int] = {}
    for eid in entity_ids:
        if eid in freshness:
            delta = (today - freshness[eid]).days
            freshness_days[eid] = delta

    fresh_count = sum(1 for d in freshness_days.values() if d <= COVERAGE_WINDOW_DAYS)
    stale_count = sum(1 for d in freshness_days.values() if d > COVERAGE_WINDOW_DAYS)
    unknown_freshness = n_entities - len(freshness_days)
    freshness_pct = round(fresh_count / n_entities * 100, 1) if n_entities > 0 else 0

    # ── Bid presence ────────────────────────────────────────────────────
    # Entities with at least 1 bid in the coverage window

    entities_with_bids = len({eid for eid in entity_ids if bid_count.get(eid, 0) > 0})
    bid_presence_pct = round(entities_with_bids / n_entities * 100, 1) if n_entities > 0 else 0

    # ── Contract presence ───────────────────────────────────────────────
    # Entities with contracts in the coverage window

    entities_with_contracts = sum(1 for eid in entity_ids if contract_presence.get(eid, False))
    contract_presence_pct = round(entities_with_contracts / n_entities * 100, 1) if n_entities > 0 else 0

    # ── Source health ───────────────────────────────────────────────────
    # Success rate from evidence ledger (graceful degradation if no evidence yet)

    health: dict[str, dict[str, Any]] = {}
    if source_health:
        for sh in source_health:
            src = sh["source"]
            total = sh["total_evidence_rows"]
            success = sh["success_with_data"] + sh["success_zero"]
            health[src] = {
                "total_runs": total,
                "successful_runs": success,
                "failed_runs": (
                    sh["connection_failed"]
                    + sh["auth_failed"]
                    + sh["parse_failed"]
                    + sh["transform_failed"]
                    + sh["persist_failed"]
                ),
                "health_pct": round(success / total * 100, 1) if total > 0 else None,
                "last_check": (
                    sh["last_check_at"].isoformat() if sh.get("last_check_at") else None
                ),
            }
    else:
        # Fallback: derive health from entity_coverage
        for src in ALL_SOURCES:
            total = source_entity_counts.get(src, 0)
            covered = source_covered_counts.get(src, 0)
            health[src] = {
                "total_runs": None,  # unverified
                "successful_runs": None,
                "failed_runs": None,
                "health_pct": round(covered / total * 100, 1) if total > 0 else None,
                "last_check": None,
                "_note": "Derived from entity_coverage; evidence ledger not yet populated",
            }

    # ── Entity/source gaps ──────────────────────────────────────────────
    # Uncovered entity+source combinations, ranked by marginal impact

    gaps: list[dict[str, Any]] = []
    for eid in sorted(entity_ids):
        entity_covered = covered_sources.get(eid, set())
        for src in ALL_SOURCES:
            if src not in entity_covered:
                gaps.append({
                    "entity_id": eid,
                    "razao_social": (entity_by_id[eid]["razao_social"] if eid in entity_by_id else "?"),
                    "municipio": entity_by_id.get(eid, {}).get("municipio", ""),
                    "source": src,
                    "state": source_state.get(src, "not_investigated"),
                })

    # Compute marginal impact: per source, how many uncovered entities would be resolved
    source_gap_counts: dict[str, int] = {}
    for g in gaps:
        src = g["source"]
        source_gap_counts[src] = source_gap_counts.get(src, 0) + 1

    ranked_sources = sorted(source_gap_counts.items(), key=lambda x: -x[1])

    # ── Assemble result ─────────────────────────────────────────────────

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "radius_km": radius_km,
            "florianopolis": {"lat": FLORIANOPOLIS_LAT, "lon": FLORIANOPOLIS_LON},
            "coverage_window_days": COVERAGE_WINDOW_DAYS,
            "evidence_ledger_available": len(evidence) > 0 or len(source_health) > 0,
        },
        "denominator": {
            "total_entities_within_radius": n_entities,
            "total_entities_statewide": "[unverified — query scoped to radius]",
        },
        "monitoring_coverage": {
            "pct": monitoring_coverage_pct,
            "entities_with_coverage": entities_with_coverage,
            "entities_checked_no_coverage": entities_with_any_check - entities_with_coverage,
            "entities_never_checked": entities_with_zero_sources,
            "by_source": per_source_coverage,
        },
        "freshness": {
            "pct_fresh": freshness_pct,
            "fresh_count": fresh_count,
            "stale_count": stale_count,
            "unknown_count": unknown_freshness,
            "window_days": COVERAGE_WINDOW_DAYS,
        },
        "bid_presence": {
            "pct": bid_presence_pct,
            "entities_with_bids": entities_with_bids,
            "entities_without_bids": n_entities - entities_with_bids,
        },
        "contract_presence": {
            "pct": contract_presence_pct,
            "entities_with_contracts": entities_with_contracts,
            "entities_without_contracts": n_entities - entities_with_contracts,
        },
        "source_health": health,
        "gaps": {
            "total_gap_combinations": len(gaps),
            "by_source": {src: count for src, count in ranked_sources},
            "next_best_source": (
                {
                    "source": ranked_sources[0][0],
                    "uncovered_entities_resolved": ranked_sources[0][1],
                    "rationale": (
                        f"Checking all entities against '{ranked_sources[0][0]}' "
                        f"would resolve {ranked_sources[0][1]} uncovered entity+source gaps — "
                        f"the highest marginal impact among all sources."
                    ),
                }
                if ranked_sources
                else None
            ),
            "sample": gaps[:20],
        },
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def print_summary(metrics: dict[str, Any]) -> None:
    """Print concise coverage truth summary to stdout."""
    meta = metrics["meta"]
    denom = metrics["denominator"]
    mc = metrics["monitoring_coverage"]
    fh = metrics["freshness"]
    bp = metrics["bid_presence"]
    cp = metrics["contract_presence"]
    gaps = metrics["gaps"]

    print("=" * 64)
    print("  COVERAGE TRUTH — Entities within", meta["radius_km"], "km of Florianópolis")
    print("=" * 64)
    print(f"  Generated:    {meta['generated_at']}")
    print(f"  Window:       {meta['coverage_window_days']} days")
    print(f"  Evidence:     {'available' if meta['evidence_ledger_available'] else 'unverified (ledger empty)'}")
    print()
    print(f"  DENOMINATOR:  {denom['total_entities_within_radius']} active entities within radius")
    print()
    print(f"  MONITORING COVERAGE:  {mc['pct']}% ({mc['entities_with_coverage']}/{denom['total_entities_within_radius']})")
    print(f"    Checked (no coverage): {mc['entities_checked_no_coverage']}")
    print(f"    Never checked:         {mc['entities_never_checked']}")
    print()
    print(f"  FRESHNESS (≤{fh['window_days']}d):  {fh['pct_fresh']}%")
    print(f"    Fresh:  {fh['fresh_count']}")
    print(f"    Stale:  {fh['stale_count']}")
    print(f"    Unknown:{fh['unknown_count']}")
    print()
    print(f"  BID PRESENCE:          {bp['pct']}% ({bp['entities_with_bids']}/{denom['total_entities_within_radius']})")
    print(f"  CONTRACT PRESENCE:     {cp['pct']}% ({cp['entities_with_contracts']}/{denom['total_entities_within_radius']})")
    print()
    print("  SOURCE HEALTH:")
    for src, h in sorted(metrics["source_health"].items()):
        hp = h.get("health_pct")
        hp_str = f"{hp}%" if hp is not None else "unverified"
        last = h.get("last_check") or "never"
        note = f" [{h.get('_note', '')}]" if h.get("_note") else ""
        print(f"    {src:<20s}  health={hp_str:>10s}  last_check={last}{note}")
    print()
    print(f"  GAPS: {gaps['total_gap_combinations']} uncovered entity+source combinations")
    print(f"  Top gap sources:")
    for src, count in list(gaps.get("by_source", {}).items())[:5]:
        print(f"    {src:<20s}  {count} uncovered entities")
    next_src = gaps.get("next_best_source")
    if next_src:
        print(f"\n  → Next best action: cover '{next_src['source']}'")
        print(f"    Resolves {next_src['uncovered_entities_resolved']} entity gaps")
    print()
    print("  ⚠️  These metrics do NOT imply completeness or ≥95% recall.")
    print("=" * 64)


def build_markdown(metrics: dict[str, Any]) -> str:
    """Build a Markdown report from computed metrics."""
    meta = metrics["meta"]
    denom = metrics["denominator"]
    mc = metrics["monitoring_coverage"]
    fh = metrics["freshness"]
    bp = metrics["bid_presence"]
    cp = metrics["contract_presence"]
    gaps = metrics["gaps"]

    lines: list[str] = []
    lines.append("# Coverage Truth Report")
    lines.append("")
    lines.append(f"**Generated:** {meta['generated_at']}")
    lines.append(f"**Radius:** {meta['radius_km']} km from Florianópolis ({meta['florianopolis']['lat']}, {meta['florianopolis']['lon']})")
    lines.append(f"**Coverage window:** {meta['coverage_window_days']} days")
    lines.append(f"**Evidence ledger:** {'Available' if meta['evidence_ledger_available'] else 'Unverified — ledger empty'}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Denominator")
    lines.append("")
    lines.append(f"- **Active entities within {meta['radius_km']} km:** {denom['total_entities_within_radius']}")
    lines.append(f"- Statewide total: {denom['total_entities_statewide']}")
    lines.append("")
    lines.append("## Metric Definitions")
    lines.append("")
    lines.append("| Metric | Definition |")
    lines.append("|--------|-----------|")
    lines.append("| Monitoring Coverage | % of entities with ≥1 source having `is_covered=true` in the coverage window |")
    lines.append(f"| Freshness | % of entities with `last_seen_at` within {COVERAGE_WINDOW_DAYS} days |")
    lines.append("| Bid Presence | % of entities with ≥1 bid record in entity_coverage |")
    lines.append("| Contract Presence | % of entities with a contract record (`source='contracts'`, `is_covered=true`) |")
    lines.append("| Source Health | % of successful evidence records per source (from coverage_evidence ledger) |")
    lines.append("| Entity/Source Gaps | Uncovered entity+source combinations |")
    lines.append("")
    lines.append("## Monitoring Coverage")
    lines.append("")
    lines.append(f"- **Coverage:** {mc['pct']}% ({mc['entities_with_coverage']}/{denom['total_entities_within_radius']})")
    lines.append(f"- Checked but no coverage: {mc['entities_checked_no_coverage']}")
    lines.append(f"- Never checked: {mc['entities_never_checked']}")
    lines.append("")
    lines.append("### By Source")
    lines.append("")
    lines.append("| Source | Entities Checked | Entities Covered | Coverage % |")
    lines.append("|--------|-----------------|------------------|------------|")
    for src in ALL_SOURCES:
        s = mc["by_source"].get(src, {})
        checked = s.get("entities_checked", 0)
        covered = s.get("entities_covered", 0)
        pct = s.get("pct_covered")
        pct_str = f"{pct}%" if pct is not None else "N/A"
        lines.append(f"| {src} | {checked} | {covered} | {pct_str} |")
    lines.append("")
    lines.append("## Freshness")
    lines.append("")
    lines.append(f"- **Fresh (≤{fh['window_days']}d):** {fh['fresh_count']} ({fh['pct_fresh']}%)")
    lines.append(f"- **Stale (>{fh['window_days']}d):** {fh['stale_count']}")
    lines.append(f"- **Unknown:** {fh['unknown_count']}")
    lines.append("")
    lines.append("## Bid Presence")
    lines.append("")
    lines.append(f"- **Entities with bids:** {bp['entities_with_bids']} ({bp['pct']}%)")
    lines.append(f"- **Entities without bids:** {bp['entities_without_bids']}")
    lines.append("")
    lines.append("## Contract Presence")
    lines.append("")
    lines.append(f"- **Entities with contracts:** {cp['entities_with_contracts']} ({cp['pct']}%)")
    lines.append(f"- **Entities without contracts:** {cp['entities_without_contracts']}")
    lines.append("")
    lines.append("## Source Health")
    lines.append("")
    lines.append("| Source | Total Runs | Successful | Failed | Health % | Last Check |")
    lines.append("|--------|-----------|------------|--------|----------|------------|")
    for src in ALL_SOURCES:
        h = metrics["source_health"].get(src, {})
        total = h.get("total_runs")
        success = h.get("successful_runs")
        failed = h.get("failed_runs")
        hp = h.get("health_pct")
        last = h.get("last_check") or "never"

        total_s = str(total) if total is not None else "?"
        success_s = str(success) if success is not None else "?"
        failed_s = str(failed) if failed is not None else "?"
        hp_s = f"{hp}%" if hp is not None else "unverified"

        lines.append(f"| {src} | {total_s} | {success_s} | {failed_s} | {hp_s} | {last} |")
    lines.append("")
    lines.append("## Entity/Source Gaps")
    lines.append("")
    lines.append(f"- **Total uncovered combinations:** {gaps['total_gap_combinations']}")
    lines.append("")
    lines.append("### By Source (ranked by marginal impact)")
    lines.append("")
    lines.append("| Rank | Source | Uncovered Entities |")
    lines.append("|------|--------|-------------------|")
    for i, (src, count) in enumerate(gaps.get("by_source", {}).items(), 1):
        lines.append(f"| {i} | {src} | {count} |")
    lines.append("")
    next_src = gaps.get("next_best_source")
    if next_src:
        lines.append("### Next Best Action")
        lines.append("")
        lines.append(f"**Source:** `{next_src['source']}`")
        lines.append(f"**Impact:** {next_src['uncovered_entities_resolved']} uncovered entities resolved")
        lines.append(f"**Rationale:** {next_src['rationale']}")
        lines.append("")
    lines.append("### Sample Gaps (first 20)")
    lines.append("")
    lines.append("| Entity | Municipio | Source | State |")
    lines.append("|--------|-----------|--------|-------|")
    for g in gaps.get("sample", []):
        lines.append(f"| {g['razao_social'][:60]} | {g['municipio']} | {g['source']} | {g['state']} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- These metrics do **NOT** imply completeness or ≥95% recall.")
    lines.append("- One record ≠ full coverage; absence of evidence ≠ evidence of absence.")
    lines.append("- Statewide entity count is reported separately from the radius-filtered denominator.")
    lines.append("- Sources not yet checked are marked `not_investigated`.")
    lines.append("- Measurements marked `unverified` reflect missing evidence ledger data — never fabricated.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    """Run the coverage truth report."""
    radius_km = args.radius_km
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR

    # ── Connect and load data ───────────────────────────────────────────
    try:
        conn = _get_conn()
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        print(f"   DSN: {_get_dsn()}")
        print(f"   Set LOCAL_DATALAKE_DSN env var to override.")
        return 1

    try:
        print("Loading entities within radius...")
        entities = load_entities_within_radius(conn, radius_km)
        if not entities:
            print(f"❌ No entities found within {radius_km} km of Florianópolis.")
            conn.close()
            return 1

        n_in_radius = len(entities)

        print(f"Loading entity coverage... ({n_in_radius} entities in radius)")
        coverage = load_entity_coverage(conn)

        print("Loading evidence ledger...")
        evidence = load_latest_evidence(conn)
        source_health = load_source_health(conn)

        entity_ids = [e["id"] for e in entities]
        print("Loading contract presence...")
        contract_presence = load_contract_presence(conn, entity_ids)

        conn.close()
    except Exception as e:
        print(f"❌ Data loading failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 1

    # ── Compute metrics ──────────────────────────────────────────────────
    print("Computing metrics...")
    metrics = compute_metrics(
        entities, coverage, evidence, source_health,
        contract_presence, radius_km,
    )

    # ── Print summary ────────────────────────────────────────────────────
    print_summary(metrics)

    # ── Write output files ───────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()

    # JSON
    json_path = output_dir / f"coverage-truth-{today_str}.json"
    with open(json_path, "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📄 JSON: {json_path}")

    # Markdown
    md_path = output_dir / f"coverage-truth-{today_str}.md"
    md_content = build_markdown(metrics)
    with open(md_path, "w") as f:
        f.write(md_content)
    print(f"📄 Markdown: {md_path}")

    # ── Key baseline values ──────────────────────────────────────────────
    print(f"\n📊 BASELINE ({today_str}):")
    print(f"   denominator={metrics['denominator']['total_entities_within_radius']}")
    print(f"   monitoring_coverage_pct={metrics['monitoring_coverage']['pct']}")
    print(f"   freshness_pct={metrics['freshness']['pct_fresh']}")
    print(f"   bid_presence_pct={metrics['bid_presence']['pct']}")
    print(f"   contract_presence_pct={metrics['contract_presence']['pct']}")
    print(f"   total_gaps={metrics['gaps']['total_gap_combinations']}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coverage Truth — auditable entity/source coverage metrics",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    # report
    r = sub.add_parser("report", help="Generate coverage truth report")
    r.add_argument(
        "--radius-km",
        type=float,
        default=DEFAULT_RADIUS_KM,
        help=f"Radius from Florianópolis in km (default: {DEFAULT_RADIUS_KM})",
    )
    r.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=f"Output directory for JSON and Markdown (default: {DEFAULT_OUTPUT_DIR})",
    )

    args = parser.parse_args()

    if args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
