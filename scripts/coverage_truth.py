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

    Monitoring coverage is derived from the evidence ledger (coverage_evidence),
    NOT from entity_coverage. Bid presence is a separate metric sourced from
    persisted records and is clearly labeled as such.

    When the evidence ledger is empty, monitoring coverage is ``unverified``,
    never a legacy percentage.
    """
    entity_ids = {e["id"] for e in entities}
    entity_by_id = {e["id"]: e for e in entities}
    n_entities = len(entities)

    evidence_success_states = {"success_with_data", "success_zero"}

    # ── Build evidence lookup: entity-level rows ────────────────────────

    # (entity_id, source) → latest evidence row
    entity_source_evidence: dict[tuple[int, str], dict] = {}
    source_aggregate_evidence: dict[str, dict] = {}
    has_any_entity_evidence = False
    has_any_aggregate_evidence = False

    for ev in evidence:
        eid = ev.get("entity_id")
        src = ev["source"]
        if eid is None:
            source_aggregate_evidence[src] = ev
            has_any_aggregate_evidence = True
        elif eid in entity_ids:
            key = (eid, src)
            entity_source_evidence[key] = ev
            has_any_entity_evidence = True

    # ── Monitoring coverage (from evidence ledger) ──────────────────────

    # Entity is "monitored" by a source if v_latest_evidence has a row
    # with state in {success_with_data, success_zero} for that entity+source.
    entities_monitored: set[int] = set()
    entities_checked: set[int] = set()
    monitored_sources: dict[int, set[str]] = {}

    for (eid, src), ev in entity_source_evidence.items():
        entities_checked.add(eid)
        if ev["state"] in evidence_success_states:
            entities_monitored.add(eid)
            monitored_sources.setdefault(eid, set()).add(src)

    entities_never_checked = n_entities - len(entities_checked)

    if n_entities == 0:
        monitoring_coverage_pct: float | None = 0.0  # trivial: no entities
    elif has_any_entity_evidence:
        monitoring_coverage_pct = round(
            len(entities_monitored) / n_entities * 100, 1
        )
    else:
        monitoring_coverage_pct = None  # unverified

    # ── Per-source coverage from evidence ───────────────────────────────

    per_source_coverage: dict[str, dict[str, Any]] = {}
    for src in ALL_SOURCES:
        checked = 0
        covered = 0
        for eid in entity_ids:
            ev = entity_source_evidence.get((eid, src))
            if ev is not None:
                checked += 1
                if ev["state"] in evidence_success_states:
                    covered += 1
        per_source_coverage[src] = {
            "entities_checked": checked,
            "entities_covered": covered,
            "pct_covered": (
                round(covered / checked * 100, 1) if checked > 0 else None
            ),
            "_source": "coverage_evidence",
        }

    # ── Bid presence (from persisted records — separate metric) ─────────

    bid_count: dict[int, int] = {}
    freshness: dict[int, date] = {}

    for row in coverage:
        eid = row["entity_id"]
        if eid not in entity_ids:
            continue
        bid_count[eid] = bid_count.get(eid, 0) + row["total_bids"]
        if row["last_seen_at"]:
            dt = row["last_seen_at"]
            if isinstance(dt, datetime):
                dt = dt.date()
            if eid not in freshness or dt > freshness[eid]:
                freshness[eid] = dt

    entities_with_bids = len({eid for eid in entity_ids if bid_count.get(eid, 0) > 0})
    bid_presence_pct = (
        round(entities_with_bids / n_entities * 100, 1) if n_entities > 0 else 0.0
    )

    # ── Freshness (from persisted records) ──────────────────────────────

    today = date.today()
    freshness_days: dict[int, int] = {}
    for eid in entity_ids:
        if eid in freshness:
            delta = (today - freshness[eid]).days
            freshness_days[eid] = delta

    fresh_count = sum(1 for d in freshness_days.values() if d <= COVERAGE_WINDOW_DAYS)
    stale_count = sum(1 for d in freshness_days.values() if d > COVERAGE_WINDOW_DAYS)
    unknown_freshness = n_entities - len(freshness_days)
    freshness_pct = (
        round(fresh_count / n_entities * 100, 1) if n_entities > 0 else 0.0
    )

    # ── Contract presence ───────────────────────────────────────────────

    entities_with_contracts = sum(
        1 for eid in entity_ids if contract_presence.get(eid, False)
    )
    contract_presence_pct = (
        round(entities_with_contracts / n_entities * 100, 1)
        if n_entities > 0
        else 0.0
    )

    # ── Source health (from evidence ledger) ────────────────────────────

    health: dict[str, dict[str, Any]] = {}
    if source_health:
        for sh in source_health:
            src = sh["source"]
            total = sh.get("total_entity_rows", 0)
            success = sh.get("success_with_data", 0) + sh.get("success_zero", 0)
            failed = (
                sh.get("connection_failed", 0)
                + sh.get("auth_failed", 0)
                + sh.get("parse_failed", 0)
                + sh.get("transform_failed", 0)
                + sh.get("persist_failed", 0)
            )
            health[src] = {
                "entity_rows": total,
                "successful_rows": success,
                "failed_rows": failed,
                "health_pct": (
                    round(success / total * 100, 1) if total > 0 else None
                ),
                "last_check": (
                    sh["last_check_at"].isoformat()
                    if sh.get("last_check_at")
                    else None
                ),
            }
    else:
        # No evidence ledger rows at all → unverified for every source
        for src in ALL_SOURCES:
            health[src] = {
                "entity_rows": None,
                "successful_rows": None,
                "failed_rows": None,
                "health_pct": None,
                "last_check": None,
                "_note": "Evidence ledger empty — source health unverified",
            }

    # ── Entity/source gaps (from evidence state) ────────────────────────
    # A gap exists when an entity+source pair has no success evidence.
    # Gaps are entity/source states, NOT "no bid found".

    gaps: list[dict[str, Any]] = []
    for eid in sorted(entity_ids):
        for src in BID_SOURCES:
            ev = entity_source_evidence.get((eid, src))
            if ev is None:
                gaps.append({
                    "entity_id": eid,
                    "razao_social": (
                        entity_by_id[eid]["razao_social"]
                        if eid in entity_by_id
                        else "?"
                    ),
                    "municipio": entity_by_id.get(eid, {}).get("municipio", ""),
                    "source": src,
                    "state": "not_investigated",
                })
            elif ev["state"] not in evidence_success_states:
                gaps.append({
                    "entity_id": eid,
                    "razao_social": (
                        entity_by_id[eid]["razao_social"]
                        if eid in entity_by_id
                        else "?"
                    ),
                    "municipio": entity_by_id.get(eid, {}).get("municipio", ""),
                    "source": src,
                    "state": ev["state"],
                })

    # Marginal gap impact per source — only for sources WITH evidence
    source_gap_counts: dict[str, int] = {}
    for g in gaps:
        src = g["source"]
        source_gap_counts[src] = source_gap_counts.get(src, 0) + 1

    # Only rank sources that actually have entity-level evidence
    sources_with_evidence = {
        src for (eid, src) in entity_source_evidence.keys()
    }
    ranked_candidates = [
        (src, count)
        for src, count in source_gap_counts.items()
        if src in sources_with_evidence
    ]
    ranked_candidates.sort(key=lambda x: -x[1])

    next_best: dict[str, Any] | None = None
    if ranked_candidates:
        src, count = ranked_candidates[0]
        next_best = {
            "source": src,
            "uncovered_entities_resolved": count,
            "rationale": (
                f"Evidence exists for '{src}' and {count} entities still "
                f"lack success coverage — the highest verified marginal "
                f"impact among sources with observed evidence."
            ),
        }
    elif source_gap_counts:
        # Gaps exist but NO source has evidence → all unverified
        biggest_untouched = max(source_gap_counts.items(), key=lambda x: x[1])
        next_best = {
            "source": biggest_untouched[0],
            "uncovered_entities_resolved": biggest_untouched[1],
            "rationale": (
                f"NO source has entity-level evidence. "
                f"'{biggest_untouched[0]}' has {biggest_untouched[1]} uncovered "
                f"entities but marginal gain is unverified — no observed evidence "
                f"exists for any source."
            ),
            "unverified": True,
        }

    # ── Assemble result ─────────────────────────────────────────────────

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "radius_km": radius_km,
            "florianopolis": {"lat": FLORIANOPOLIS_LAT, "lon": FLORIANOPOLIS_LON},
            "coverage_window_days": COVERAGE_WINDOW_DAYS,
            "evidence_ledger_available": has_any_entity_evidence or has_any_aggregate_evidence,
            "entity_evidence_available": has_any_entity_evidence,
        },
        "denominator": {
            "total_entities_within_radius": n_entities,
            "total_entities_statewide": "[unverified — query scoped to radius]",
        },
        "monitoring_coverage": {
            "pct": monitoring_coverage_pct,
            "pct_display": (
                f"{monitoring_coverage_pct}%"
                if monitoring_coverage_pct is not None
                else "unverified"
            ),
            "entities_monitored": len(entities_monitored),
            "entities_checked_no_coverage": len(entities_checked - entities_monitored),
            "entities_never_checked": entities_never_checked,
            "_source": "coverage_evidence (v_latest_evidence)",
            "_note": (
                "Monitoring coverage from evidence ledger — entity-level "
                "observations only. Bid presence is a separate metric."
            ),
            "by_source": per_source_coverage,
        },
        "freshness": {
            "pct_fresh": freshness_pct,
            "fresh_count": fresh_count,
            "stale_count": stale_count,
            "unknown_count": unknown_freshness,
            "window_days": COVERAGE_WINDOW_DAYS,
            "_source": "entity_coverage.last_seen_at (persisted records)",
        },
        "bid_presence": {
            "pct": bid_presence_pct,
            "entities_with_bids": entities_with_bids,
            "entities_without_bids": n_entities - entities_with_bids,
            "_source": "entity_coverage.total_bids (persisted records)",
            "_note": (
                "Bid presence counts entities with ≥1 persisted bid record. "
                "This is NOT monitoring coverage — an entity may have bids "
                "without an evidence-backed monitoring observation."
            ),
        },
        "contract_presence": {
            "pct": contract_presence_pct,
            "entities_with_contracts": entities_with_contracts,
            "entities_without_contracts": n_entities - entities_with_contracts,
        },
        "source_health": health,
        "gaps": {
            "total_gap_combinations": len(gaps),
            "by_source": {
                src: count
                for src, count in sorted(
                    source_gap_counts.items(), key=lambda x: -x[1]
                )
            },
            "next_best_source": next_best,
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

    mc_pct_display = mc.get("pct_display", f"{mc.get('pct', '?')}%")
    print("=" * 64)
    print("  COVERAGE TRUTH — Entities within", meta["radius_km"], "km of Florianópolis")
    print("=" * 64)
    print(f"  Generated:    {meta['generated_at']}")
    print(f"  Window:       {meta['coverage_window_days']} days")
    print(f"  Evidence:     {'available' if meta['evidence_ledger_available'] else 'unverified (ledger empty)'}")
    print()
    print(f"  DENOMINATOR:  {denom['total_entities_within_radius']} active entities within radius")
    print()
    print(f"  MONITORING COVERAGE:  {mc_pct_display} ({mc.get('entities_monitored', '?')}/{denom['total_entities_within_radius']})")
    print(f"    Source: {mc.get('_source', '?')}")
    print(f"    Checked (no success): {mc.get('entities_checked_no_coverage', '?')}")
    print(f"    Never checked:        {mc.get('entities_never_checked', '?')}")
    print()
    print(f"  FRESHNESS (≤{fh['window_days']}d, from persisted records):  {fh['pct_fresh']}%")
    print(f"    Fresh:  {fh['fresh_count']}")
    print(f"    Stale:  {fh['stale_count']}")
    print(f"    Unknown:{fh['unknown_count']}")
    print()
    print(f"  BID PRESENCE (persisted records): {bp['pct']}% ({bp['entities_with_bids']}/{denom['total_entities_within_radius']})")
    print(f"    ⚠️  Bid presence ≠ monitoring coverage. See report for details.")
    print(f"  CONTRACT PRESENCE:                {cp['pct']}% ({cp['entities_with_contracts']}/{denom['total_entities_within_radius']})")
    print()
    print("  SOURCE HEALTH (from evidence ledger):")
    for src, h in sorted(metrics["source_health"].items()):
        hp = h.get("health_pct")
        hp_str = f"{hp}%" if hp is not None else "unverified"
        last = h.get("last_check") or "never"
        note = f" [{h.get('_note', '')}]" if h.get("_note") else ""
        print(f"    {src:<20s}  health={hp_str:>10s}  last_check={last}{note}")
    print()
    print(f"  GAPS: {gaps['total_gap_combinations']} entity+source pairs without success evidence")
    print(f"  Top gap sources (by entity count):")
    for src, count in list(gaps.get("by_source", {}).items())[:5]:
        print(f"    {src:<20s}  {count} entities")
    next_src = gaps.get("next_best_source")
    if next_src:
        unverified_tag = " [UNVERIFIED — no source has entity evidence]" if next_src.get("unverified") else ""
        print(f"\n  → Next best action: '{next_src['source']}'{unverified_tag}")
        print(f"    {next_src['rationale']}")
    print()
    print("  ⚠️  Monitoring coverage ≠ completeness. One record ≠ full coverage.")
    print("  ⚠️  Bid presence is a separate metric — not interchangeable with monitoring coverage.")
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
    lines.append("| Metric | Definition | Source |")
    lines.append("|--------|-----------|--------|")
    lines.append("| Monitoring Coverage | % of entities with ≥1 source having evidence state `success_*` | `coverage_evidence` (v_latest_evidence) |")
    lines.append(f"| Freshness | % of entities with `last_seen_at` within {COVERAGE_WINDOW_DAYS} days | `entity_coverage.last_seen_at` |")
    lines.append("| Bid Presence | % of entities with ≥1 persisted bid record | `entity_coverage.total_bids` |")
    lines.append("| Contract Presence | % of entities with a contract record | `entity_coverage` (source='contracts') |")
    lines.append("| Source Health | % of successful entity-level evidence rows per source | `coverage_evidence` (v_source_health) |")
    lines.append("| Entity/Source Gaps | Entity+source pairs without `success_*` evidence | `coverage_evidence` |")
    lines.append("")
    lines.append("## Monitoring Coverage")
    lines.append("")
    mc_pct_display = mc.get("pct_display", f"{mc.get('pct', '?')}%")
    mc_note = mc.get("_note", "")
    mc_source = mc.get("_source", "?")
    lines.append(f"- **Coverage:** {mc_pct_display} ({mc.get('entities_monitored', '?')}/{denom['total_entities_within_radius']})")
    lines.append(f"- Source: `{mc_source}`")
    if mc_note:
        lines.append(f"- ⚠️  {mc_note}")
    lines.append(f"- Checked (no success): {mc.get('entities_checked_no_coverage', '?')}")
    lines.append(f"- Never checked: {mc.get('entities_never_checked', '?')}")
    lines.append("")
    lines.append("### By Source (from evidence ledger)")
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
    lines.append("## Bid Presence (persisted records)")
    lines.append("")
    bp_note = bp.get("_note", "")
    lines.append(f"- **Entities with bids:** {bp['entities_with_bids']} ({bp['pct']}%)")
    lines.append(f"- **Entities without bids:** {bp['entities_without_bids']}")
    if bp_note:
        lines.append(f"- ⚠️  {bp_note}")
    lines.append("")
    lines.append("## Contract Presence")
    lines.append("")
    lines.append(f"- **Entities with contracts:** {cp['entities_with_contracts']} ({cp['pct']}%)")
    lines.append(f"- **Entities without contracts:** {cp['entities_without_contracts']}")
    lines.append("")
    lines.append("## Source Health (from evidence ledger)")
    lines.append("")
    lines.append("| Source | Entity Rows | Successful | Failed | Health % | Last Check |")
    lines.append("|--------|------------|------------|--------|----------|------------|")
    for src in ALL_SOURCES:
        h = metrics["source_health"].get(src, {})
        total = h.get("entity_rows")
        success = h.get("successful_rows")
        failed = h.get("failed_rows")
        hp = h.get("health_pct")
        last = h.get("last_check") or "never"
        note = h.get("_note", "")

        total_s = str(total) if total is not None else "?"
        success_s = str(success) if success is not None else "?"
        failed_s = str(failed) if failed is not None else "?"
        hp_s = f"{hp}%" if hp is not None else "unverified"

        lines.append(f"| {src} | {total_s} | {success_s} | {failed_s} | {hp_s} | {last} |")
        if note:
            lines.append(f"| | _{note}_ | | | | |")
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
        unverified_tag = " ⚠️ UNVERIFIED" if next_src.get("unverified") else ""
        lines.append("### Next Best Action" + unverified_tag)
        lines.append("")
        lines.append(f"**Source:** `{next_src['source']}`")
        lines.append(f"**Impact:** {next_src['uncovered_entities_resolved']} uncovered entities")
        lines.append(f"**Rationale:** {next_src['rationale']}")
        if next_src.get("unverified"):
            lines.append("")
            lines.append("⚠️  **Marginal gain is unverified.** No source has entity-level evidence in the ledger. This ranking reflects only the count of uncovered entity+source combinations — it does NOT reflect observed source effectiveness.")
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
    lines.append("- Monitoring coverage (from evidence ledger) ≠ bid presence (from persisted records).")
    lines.append("- These metrics do **NOT** imply completeness or ≥95% recall.")
    lines.append("- One record ≠ full coverage; absence of evidence ≠ evidence of absence.")
    lines.append("- Statewide entity count is reported separately from the radius-filtered denominator.")
    lines.append("- Sources not yet checked are marked `not_investigated`.")
    lines.append("- Measurements marked `unverified` reflect missing evidence ledger data — never fabricated.")
    lines.append("- When no entity-level evidence exists, monitoring coverage is `unverified`, not 0%.")
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
    mc = metrics["monitoring_coverage"]
    print(f"\n📊 BASELINE ({today_str}):")
    print(f"   denominator={metrics['denominator']['total_entities_within_radius']}")
    print(f"   monitoring_coverage_pct={mc.get('pct_display', 'unverified')}")
    print(f"   entities_monitored={mc.get('entities_monitored', 0)}")
    print(f"   freshness_pct={metrics['freshness']['pct_fresh']}")
    print(f"   bid_presence_pct={metrics['bid_presence']['pct']}")
    print(f"   contract_presence_pct={metrics['contract_presence']['pct']}")
    print(f"   total_gaps={metrics['gaps']['total_gap_combinations']}")
    print(f"   entity_evidence_available={metrics['meta']['entity_evidence_available']}")

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
