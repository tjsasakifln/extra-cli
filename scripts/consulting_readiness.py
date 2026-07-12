#!/usr/bin/env python3
"""Consulting Readiness Gate — auditable readiness assessment for consulting coverage.

Prevents the system from claiming coverage, pricing, competition, or commercial
readiness without sufficient evidence.

Usage::

    python scripts/consulting_readiness.py --radius-km 200 --threshold 0.95 --output-dir output/readiness

Generates ``coverage_manifest.json`` and ``coverage_gaps.csv``.

Exit codes:
    0 — readiness proven (coverage >= threshold)
    2 — data does not meet readiness criteria
    1 — technical failure (DB connection, missing seed file, etc.)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLORIANOPOLIS_LAT = -27.5954
FLORIANOPOLIS_LON = -48.5480
EARTH_RADIUS_KM = 6371.0
DEFAULT_RADIUS_KM = 200.0
DEFAULT_THRESHOLD = 0.95
COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = str(PROJECT_ROOT / "Extra - alvos de licitação. R-0.xlsx")
DEFAULT_OUTPUT_DIR = str(PROJECT_ROOT / "output" / "readiness")

# Column mapping for the seed spreadsheet (0-indexed)
COL_RAZAO = 0
COL_CNPJ8 = 1
COL_MUNICIPIO = 2
COL_IBGE = 3
COL_NATUREZA = 4
COL_COD_NATUREZA = 5
COL_LATITUDE = 6
COL_LONGITUDE = 7
COL_DISTANCIA_SEED = 8
COL_RAIO200 = 9

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class TargetEntity:
    """One entity from the seed spreadsheet, with resolution status."""

    razao_social: str
    cnpj8: str
    municipio: str
    codigo_ibge: str
    natureza_juridica: str
    latitude: float | None = None
    longitude: float | None = None
    distancia_km: float | None = None
    within_radius: bool = False
    resolution: str = "resolved"  # resolved | unresolved | duplicate


@dataclass
class TargetUniverse:
    """Auditable target universe derived from the seed spreadsheet."""

    entities: list[TargetEntity] = field(default_factory=list)
    total_seed_rows: int = 0
    total_resolved: int = 0
    total_unresolved: int = 0
    total_duplicates: int = 0
    total_within_radius: int = 0
    total_outside_radius: int = 0
    unresolved_entities: list[dict[str, str]] = field(default_factory=list)
    duplicate_cnpj8_list: list[str] = field(default_factory=list)
    seed_file: str = ""
    radius_km: float = DEFAULT_RADIUS_KM

    @property
    def inclusion_rule(self) -> str:
        return (
            f"Haversine distance from ({FLORIANOPOLIS_LAT:.4f}, {FLORIANOPOLIS_LON:.4f}) "
            f"<= {self.radius_km:.1f} km (Earth radius {EARTH_RADIUS_KM} km). "
            f"Entities without coordinates marked 'unresolved' — NEVER excluded silently."
        )

    @property
    def confirmed_universe_count(self) -> int:
        """Entities with confirmed coordinates (resolved + within radius or outside)."""
        return self.total_resolved

    @property
    def potential_universe_count(self) -> int:
        """Confirmed + unresolved = maximum possible universe."""
        return self.total_resolved + self.total_unresolved

    def summary(self) -> dict[str, Any]:
        return {
            "seed_file": self.seed_file,
            "total_seed_rows": self.total_seed_rows,
            "confirmed_universe": self.total_resolved,
            "potential_universe": self.potential_universe_count,
            "unresolved": self.total_unresolved,
            "duplicates": self.total_duplicates,
            "within_radius": self.total_within_radius,
            "outside_radius": self.total_outside_radius,
            "duplicate_cnpj8_list": self.duplicate_cnpj8_list,
            "unresolved_entities": self.unresolved_entities,
            "inclusion_rule": self.inclusion_rule,
            "center_lat": FLORIANOPOLIS_LAT,
            "center_lon": FLORIANOPOLIS_LON,
            "radius_km": self.radius_km,
        }


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------


def load_target_universe(
    seed_path: str | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> TargetUniverse:
    """Load seed spreadsheet and build auditable target universe.

    Entities without coordinates are marked ``unresolved`` — NEVER excluded.
    """
    if seed_path is None:
        seed_path = DEFAULT_SEED

    if not os.path.exists(seed_path):
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl is required. Install with: pip install openpyxl")

    wb = openpyxl.load_workbook(seed_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    universe = TargetUniverse(
        seed_file=seed_path,
        radius_km=radius_km,
        total_seed_rows=len(rows),
    )

    cnpj8_seen: dict[str, int] = {}

    for row in rows:
        if not row or not row[COL_RAZAO]:
            continue

        razao = str(row[COL_RAZAO]).strip()
        cnpj8 = _normalize_cnpj8(str(row[COL_CNPJ8])) if len(row) > COL_CNPJ8 and row[COL_CNPJ8] else ""
        municipio = str(row[COL_MUNICIPIO]).strip() if len(row) > COL_MUNICIPIO and row[COL_MUNICIPIO] else ""
        ibge = str(int(row[COL_IBGE])) if len(row) > COL_IBGE and row[COL_IBGE] else ""
        natureza = str(row[COL_NATUREZA]).strip() if len(row) > COL_NATUREZA and row[COL_NATUREZA] else ""

        lat_raw = row[COL_LATITUDE] if len(row) > COL_LATITUDE else None
        lon_raw = row[COL_LONGITUDE] if len(row) > COL_LONGITUDE else None

        lat, lon, has_coords = _parse_coords(lat_raw, lon_raw)

        if not has_coords:
            entity = TargetEntity(
                razao_social=razao,
                cnpj8=cnpj8,
                municipio=municipio,
                codigo_ibge=ibge,
                natureza_juridica=natureza,
                resolution="unresolved",
            )
            universe.entities.append(entity)
            universe.total_unresolved += 1
            universe.unresolved_entities.append(
                {
                    "razao_social": razao,
                    "cnpj8": cnpj8,
                    "municipio": municipio,
                    "codigo_ibge": ibge,
                }
            )
            continue

        dist = haversine_km(FLORIANOPOLIS_LAT, FLORIANOPOLIS_LON, lat, lon)
        within = dist <= radius_km
        universe.total_resolved += 1

        entity = TargetEntity(
            razao_social=razao,
            cnpj8=cnpj8,
            municipio=municipio,
            codigo_ibge=ibge,
            natureza_juridica=natureza,
            latitude=lat,
            longitude=lon,
            distancia_km=round(dist, 1),
            within_radius=within,
            resolution="resolved",
        )
        universe.entities.append(entity)

        if within:
            universe.total_within_radius += 1
            cnpj8_seen[cnpj8] = cnpj8_seen.get(cnpj8, 0) + 1
        else:
            universe.total_outside_radius += 1

    # Compute duplicates
    for cnpj8, count in cnpj8_seen.items():
        if count > 1:
            universe.total_duplicates += 1
            universe.duplicate_cnpj8_list.append(cnpj8)

    return universe


def _parse_coords(lat_raw: Any, lon_raw: Any) -> tuple[float | None, float | None, bool]:
    """Parse coordinate pair. Returns (lat, lon, has_coords)."""
    if lat_raw is None or lon_raw is None:
        return None, None, False
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
        return lat, lon, True
    except (ValueError, TypeError):
        return None, None, False


def _normalize_cnpj8(raw: str) -> str:
    """Strip non-digit characters from CNPJ8 string."""
    import re

    return re.sub(r"\D", "", raw)


# ---------------------------------------------------------------------------
# Database helpers (PostgreSQL only — no SQLite fallback)
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    return os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
    )


def _get_conn():
    """Connect to PostgreSQL. Fails closed — NO SQLite fallback."""
    import psycopg2

    dsn = _get_dsn()
    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
        return conn
    except Exception as e:
        # Fail closed: if DSN is explicitly set and PG fails, refuse to continue
        explicit_dsn = os.getenv("LOCAL_DATALAKE_DSN", "")
        if explicit_dsn:
            raise ConnectionError(
                f"PostgreSQL connection failed with explicit LOCAL_DATALAKE_DSN. "
                f"Refusing to fall back to SQLite. Error: {e}"
            ) from e
        raise ConnectionError(f"Cannot connect to database: {e}") from e


def _query(conn, sql: str, params: list | None = None) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


# ---------------------------------------------------------------------------
# Evidence and coverage data loading
# ---------------------------------------------------------------------------


def load_evidence(conn) -> list[dict]:
    """Load latest evidence from v_latest_evidence view."""
    cur = conn.cursor()
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'v_latest_evidence')")
    if not cur.fetchone()[0]:
        cur.close()
        return []
    cur.close()
    return _query(conn, "SELECT * FROM v_latest_evidence")


def load_source_health(conn) -> list[dict]:
    """Load source health from v_source_health view."""
    cur = conn.cursor()
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'v_source_health')")
    if not cur.fetchone()[0]:
        cur.close()
        return []
    cur.close()
    return _query(conn, "SELECT * FROM v_source_health ORDER BY source")


def load_entity_coverage(conn) -> list[dict]:
    """Load entity_coverage for active entities."""
    return _query(
        conn,
        """SELECT ec.entity_id, ec.source, ec.last_seen_at, ec.total_bids,
                  ec.is_covered, ec.within_200km, ec.match_method
           FROM entity_coverage ec
           JOIN sc_public_entities e ON e.id = ec.entity_id
           WHERE e.is_active = TRUE""",
    )


def load_entity_data(conn, cnpj8_list: list[str]) -> dict[str, dict]:
    """Load sc_public_entities data keyed by cnpj_8."""
    if not cnpj8_list:
        return {}
    cur = conn.cursor()
    cur.execute(
        """SELECT id, razao_social, cnpj_8, municipio, codigo_ibge,
                  natureza_juridica, latitude, longitude
           FROM sc_public_entities
           WHERE cnpj_8 = ANY(%s) AND is_active = TRUE""",
        (cnpj8_list,),
    )
    result = {}
    for row in cur.fetchall():
        cnpj8 = row[2]
        result[cnpj8] = {
            "id": row[0],
            "razao_social": row[1],
            "cnpj_8": row[2],
            "municipio": row[3],
            "codigo_ibge": row[4],
            "natureza_juridica": row[5],
            "latitude": row[6],
            "longitude": row[7],
        }
    cur.close()
    return result


# ---------------------------------------------------------------------------
# SQL queries for open_tenders and contracts
# ---------------------------------------------------------------------------


def count_open_tenders(conn, entity_ids: list[int]) -> dict[int, int]:
    """Count open tenders (pncp_raw_bids) per entity_id."""
    if not entity_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        """SELECT matched_entity_id, COUNT(*)
           FROM pncp_raw_bids
           WHERE matched_entity_id = ANY(%s)
             AND is_active = TRUE
             AND data_encerramento >= CURRENT_DATE
           GROUP BY matched_entity_id""",
        (entity_ids,),
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return result


def count_contracts(conn, entity_cnpj8_list: list[str]) -> dict[str, int]:
    """Count contracts (pncp_supplier_contracts) per organ CNPJ8."""
    if not entity_cnpj8_list:
        return {}
    cur = conn.cursor()
    # Match by first 8 digits of orgao_cnpj (cnpj8 prefix)
    patterns = [(cnpj8 + "%",) for cnpj8 in entity_cnpj8_list if cnpj8]
    if not patterns:
        return {}

    # Use LEFT(orgao_cnpj, 8) matching
    cur.execute(
        """SELECT LEFT(orgao_cnpj, 8) AS cnpj8, COUNT(*)
           FROM pncp_supplier_contracts
           WHERE LEFT(orgao_cnpj, 8) = ANY(%s)
             AND is_active = TRUE
           GROUP BY LEFT(orgao_cnpj, 8)""",
        (entity_cnpj8_list,),
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return result


# ---------------------------------------------------------------------------
# Freshness from entity_coverage
# ---------------------------------------------------------------------------


def compute_freshness(
    coverage_rows: list[dict],
    entity_ids: set[int],
) -> dict[str, Any]:
    """Compute freshness from entity_coverage last_seen_at dates."""
    freshness: dict[int, date] = {}
    for row in coverage_rows:
        eid = row["entity_id"]
        if eid not in entity_ids:
            continue
        dt = row["last_seen_at"]
        if dt:
            if isinstance(dt, datetime):
                dt = dt.date()
            if eid not in freshness or dt > freshness[eid]:
                freshness[eid] = dt

    today = date.today()
    fresh_count = 0
    stale_count = 0
    for eid in entity_ids:
        if eid in freshness:
            delta = (today - freshness[eid]).days
            if delta <= COVERAGE_WINDOW_DAYS:
                fresh_count += 1
            else:
                stale_count += 1

    unknown_count = len(entity_ids) - fresh_count - stale_count

    return {
        "fresh_count": fresh_count,
        "stale_count": stale_count,
        "unknown_count": unknown_count,
        "window_days": COVERAGE_WINDOW_DAYS,
    }


# ---------------------------------------------------------------------------
# Main readiness computation
# ---------------------------------------------------------------------------


def compute_readiness(
    universe: TargetUniverse,
    evidence: list[dict],
    source_health: list[dict],
    coverage_rows: list[dict],
    entity_data: dict[str, dict],
    conn,
    threshold: float,
) -> dict[str, Any]:
    """Compute the readiness assessment from all data sources."""

    # ── Build entity ID sets ─────────────────────────────────────────────
    resolved_within = [e for e in universe.entities if e.resolution == "resolved" and e.within_radius]
    unresolved = [e for e in universe.entities if e.resolution == "unresolved"]

    # Map CNPJ8 → entity data
    cnpj8_to_entity = entity_data

    # Build entity ID list for resolved within-radius entities that have DB records
    entity_id_to_cnpj8: dict[int, str] = {}
    cnpj8_to_entity_id: dict[str, int] = {}
    for e in resolved_within:
        if e.cnpj8 in cnpj8_to_entity:
            eid = cnpj8_to_entity[e.cnpj8]["id"]
            entity_id_to_cnpj8[eid] = e.cnpj8
            cnpj8_to_entity_id[e.cnpj8] = eid

    entity_ids = set(entity_id_to_cnpj8.keys())

    # ── Conservative denominator ─────────────────────────────────────────
    # Denominator = confirmed within-radius entities in DB + unresolved entities
    # Unresolved entities count against coverage because we can't prove
    # they're covered → they represent uncertainty
    denominator_conservative = len(resolved_within) + len(unresolved)
    denominator_confirmed = len(resolved_within)

    # ── Evidence-based monitoring coverage ───────────────────────────────
    evidence_success_states = {"success_with_data", "success_zero"}

    # Entity-level evidence lookup
    entity_evidence: dict[tuple[int, str], dict] = {}
    for ev in evidence:
        eid = ev.get("entity_id")
        src = ev["source"]
        if eid is not None and eid in entity_ids:
            entity_evidence[(eid, src)] = ev

    entities_monitored: set[int] = set()
    entities_checked: set[int] = set()
    for (eid, src), ev in entity_evidence.items():
        entities_checked.add(eid)
        if ev["state"] in evidence_success_states:
            entities_monitored.add(eid)

    # ── Per-source breakdown ─────────────────────────────────────────────
    all_sources = set()
    for ev in evidence:
        all_sources.add(ev["source"])

    per_source: dict[str, dict[str, Any]] = {}
    for src in sorted(all_sources):
        checked = 0
        covered = 0
        for eid in entity_ids:
            ev = entity_evidence.get((eid, src))
            if ev is not None:
                checked += 1
                if ev["state"] in evidence_success_states:
                    covered += 1
        per_source[src] = {
            "checked": checked,
            "covered": covered,
            "pct": round(covered / checked * 100, 1) if checked > 0 else None,
        }

    # ── Evidence state breakdown ─────────────────────────────────────────
    state_counts: dict[str, int] = {
        "success_with_data": 0,
        "success_zero": 0,
        "partial": 0,
        "failed": 0,
        "not_investigated": 0,
    }
    for eid in entity_ids:
        has_any_evidence = False
        has_success = False
        has_partial = False
        has_failed = False
        for (ev_eid, _), ev in entity_evidence.items():
            if ev_eid != eid:
                continue
            has_any_evidence = True
            state = ev["state"]
            if state in evidence_success_states:
                has_success = True
            elif state == "partial":
                has_partial = True
            elif state and "failed" in state:
                has_failed = True

        if has_success:
            state_counts["success_with_data"] += 1
        elif has_partial:
            state_counts["partial"] += 1
        elif has_failed:
            state_counts["failed"] += 1
        elif has_any_evidence:
            state_counts["not_investigated"] += 1
        else:
            state_counts["not_investigated"] += 1

    # ── Open tenders and contracts ───────────────────────────────────────
    open_tenders_count = count_open_tenders(conn, list(entity_ids))
    entities_with_open_tenders = len(open_tenders_count)
    total_open_tenders = sum(open_tenders_count.values())

    cnpj8_list = [e.cnpj8 for e in resolved_within if e.cnpj8]
    contracts_count = count_contracts(conn, cnpj8_list)
    entities_with_contracts = len(contracts_count)
    total_contracts = sum(contracts_count.values())

    # ── Freshness ────────────────────────────────────────────────────────
    freshness = compute_freshness(coverage_rows, entity_ids)

    # ── Coverage numerator ───────────────────────────────────────────────
    # Entities that are monitored (have evidence success) AND have data
    numerator = len(entities_monitored)

    # Coverage % based on conservative denominator
    if denominator_conservative > 0:
        coverage_pct = numerator / denominator_conservative
    else:
        coverage_pct = 0.0

    # ── Gap analysis ─────────────────────────────────────────────────────
    gaps: list[dict[str, Any]] = []
    for e in resolved_within:
        if e.cnpj8 not in cnpj8_to_entity_id:
            # Entity not in DB → gap
            gaps.append(
                {
                    "razao_social": e.razao_social,
                    "cnpj8": e.cnpj8,
                    "municipio": e.municipio,
                    "type": "not_in_db",
                    "detail": "Entity from seed file not found in sc_public_entities",
                }
            )
            continue
        eid = cnpj8_to_entity_id[e.cnpj8]
        if eid not in entities_monitored:
            gap_state = "not_investigated"
            for (ev_eid, _), ev in entity_evidence.items():
                if ev_eid == eid:
                    gap_state = ev["state"]
                    break
            gaps.append(
                {
                    "razao_social": e.razao_social,
                    "cnpj8": e.cnpj8,
                    "municipio": e.municipio,
                    "entity_id": eid,
                    "type": "not_monitored",
                    "state": gap_state,
                }
            )

    # Unresolved entities are always gaps
    for e in unresolved:
        gaps.append(
            {
                "razao_social": e.razao_social,
                "cnpj8": e.cnpj8,
                "municipio": e.municipio,
                "type": "unresolved",
                "detail": "Entity lacks coordinates — cannot determine if within radius",
            }
        )

    # ── Source health aggregation ────────────────────────────────────────
    health: dict[str, dict[str, Any]] = {}
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
            "successful": success,
            "failed": failed,
            "health_pct": round(success / total * 100, 1) if total > 0 else None,
            "last_check": (sh["last_check_at"].isoformat() if sh.get("last_check_at") else None),
        }

    # ── Commercial metrics gating ────────────────────────────────────────
    commercial_metrics = {
        "contract_total_value": {
            "status": "not_ready",
            "reason": (
                "Valor global de contrato não é 'preço praticado'. "
                "Preço praticado requer comparação com propostas homologadas "
                "item a item — dados não disponíveis no evidence ledger atual."
            ),
        },
        "desagio": {
            "status": "not_ready",
            "reason": (
                "Deságio requer dados relacionais entre valor estimado do edital "
                "e valor homologado por item/lote — tabelas de itens de proposta "
                "não populadas no escopo atual."
            ),
        },
        "win_rate": {
            "status": "not_ready",
            "reason": (
                "Win rate requer tracking de propostas enviadas vs vencidas "
                "por CNPJ — dados de outcomes de propostas não disponíveis "
                "no evidence ledger."
            ),
        },
        "relicitacao_probability": {
            "status": "not_ready",
            "reason": (
                "Probabilidade de relicitação requer série histórica de "
                "contratos por órgão com datas de término e renovações — "
                "modelo não calibrado com dados suficientes."
            ),
        },
    }

    # ── Readiness decision ───────────────────────────────────────────────
    readiness_passed = coverage_pct >= threshold and len(unresolved) == 0

    # If there are unresolved entities, coverage is uncertain
    if len(unresolved) > 0:
        unresolved_block = (
            f"{len(unresolved)} unresolved entities prevent confirming "
            f"coverage >= {threshold:.0%}. Resolve coordinates or mark "
            f"as out-of-radius with evidence."
        )
    else:
        unresolved_block = None

    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "radius_km": universe.radius_km,
            "threshold": threshold,
            "coverage_window_days": COVERAGE_WINDOW_DAYS,
            "florianopolis": {"lat": FLORIANOPOLIS_LAT, "lon": FLORIANOPOLIS_LON},
            "exit_code": 0 if readiness_passed else 2,
        },
        "universe": universe.summary(),
        "coverage": {
            "numerator": numerator,
            "denominator_conservative": denominator_conservative,
            "denominator_confirmed": denominator_confirmed,
            "percent": round(coverage_pct * 100, 1),
            "threshold": round(threshold * 100, 1),
            "passed": readiness_passed,
            "unresolved_block": unresolved_block,
            "entities_monitored": len(entities_monitored),
            "entities_unmonitored": denominator_confirmed - len(entities_monitored),
            "stale": freshness["stale_count"],
            "partial": state_counts["partial"],
            "failed": state_counts["failed"],
            "not_investigated": state_counts["not_investigated"],
            "unresolved": len(unresolved),
        },
        "open_tenders": {
            "entities_with_open_tenders": entities_with_open_tenders,
            "total_open_tenders": total_open_tenders,
            "pct_of_confirmed": (
                round(entities_with_open_tenders / denominator_confirmed * 100, 1) if denominator_confirmed > 0 else 0.0
            ),
        },
        "contracts": {
            "entities_with_contracts": entities_with_contracts,
            "total_contracts": total_contracts,
            "pct_of_confirmed": (
                round(entities_with_contracts / denominator_confirmed * 100, 1) if denominator_confirmed > 0 else 0.0
            ),
        },
        "freshness": freshness,
        "per_source": per_source,
        "source_health": health,
        "commercial_metrics": commercial_metrics,
        "gaps": {
            "total": len(gaps),
            "by_type": _count_by_key(gaps, "type"),
        },
        "gaps_detail": gaps,
    }


def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        k = item.get(key, "unknown")
        counts[k] = counts.get(k, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def write_manifest(metrics: dict[str, Any], output_dir: str) -> str:
    """Write coverage_manifest.json."""
    path = os.path.join(output_dir, "coverage_manifest.json")
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False, default=str)
    return path


def write_gaps_csv(metrics: dict[str, Any], output_dir: str) -> str:
    """Write coverage_gaps.csv."""
    path = os.path.join(output_dir, "coverage_gaps.csv")
    gaps = metrics.get("gaps_detail", [])
    if not gaps:
        with open(path, "w", newline="") as f:
            f.write("razao_social,cnpj8,municipio,type,state,detail\n")
        return path

    fieldnames = ["razao_social", "cnpj8", "municipio", "type", "state", "detail"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for g in gaps:
            row = {k: g.get(k, "") for k in fieldnames}
            writer.writerow(row)
    return path


def print_summary(metrics: dict[str, Any]) -> None:
    """Print readiness summary to stdout."""
    u = metrics["universe"]
    c = metrics["coverage"]
    m = metrics["meta"]
    ot = metrics["open_tenders"]
    ct = metrics["contracts"]
    fh = metrics["freshness"]

    print("=" * 68)
    print("  CONSULTING READINESS GATE")
    print("=" * 68)
    print(f"  Generated:    {m['generated_at']}")
    print(f"  Radius:        {m['radius_km']} km from Florianópolis")
    print(f"  Threshold:     {m['threshold']:.0%}")
    print(f"  Window:        {m['coverage_window_days']} days")
    print()
    print("  UNIVERSE:")
    print(f"    Confirmed:     {u['confirmed_universe']} entities (with coordinates)")
    print(f"    Unresolved:    {u['unresolved']} entities (no coordinates)")
    print(f"    Potential:     {u['potential_universe']} entities (max)")
    print(f"    Within radius: {u['within_radius']}")
    print(f"    Outside radius:{u['outside_radius']}")
    print(f"    Duplicates:    {u['duplicates']}")
    print()
    print("  COVERAGE:")
    print(f"    Numerator:     {c['numerator']}")
    print(f"    Denominator:   {c['denominator_conservative']} (conservative)")
    print(f"    Percent:       {c['percent']}%")
    print(f"    Threshold:     {c['threshold']}%")
    print(f"    PASS:          {c['passed']}")
    if c.get("unresolved_block"):
        print(f"    ⚠️  BLOCKED:   {c['unresolved_block']}")
    print(f"    Stale:         {c['stale']}")
    print(f"    Partial:       {c['partial']}")
    print(f"    Failed:        {c['failed']}")
    print(f"    Not investig.: {c['not_investigated']}")
    print(f"    Unresolved:    {c['unresolved']}")
    print()
    print(f"  OPEN TENDERS:    {ot['entities_with_open_tenders']} entities ({ot['total_open_tenders']} total)")
    print(f"  CONTRACTS:       {ct['entities_with_contracts']} entities ({ct['total_contracts']} total)")
    print()
    print(f"  FRESHNESS (≤{fh['window_days']}d):")
    print(f"    Fresh:   {fh['fresh_count']}")
    print(f"    Stale:   {fh['stale_count']}")
    print(f"    Unknown: {fh['unknown_count']}")
    print()
    print("  COMMERCIAL METRICS:")
    for name, info in metrics.get("commercial_metrics", {}).items():
        print(f"    {name}: {info['status']} — {info['reason'][:80]}...")
    print()
    print(f"  GAPS: {metrics['gaps']['total']} total")
    for typ, count in sorted(metrics["gaps"].get("by_type", {}).items()):
        print(f"    {typ}: {count}")
    print()
    unresolved_block = c.get("unresolved_block")
    if c["passed"] and not unresolved_block:
        print("  ✅ READINESS PROVEN — coverage meets threshold")
    elif unresolved_block:
        print("  ❌ READINESS NOT PROVEN — unresolved entities block confirmation")
    else:
        print(f"  ❌ READINESS NOT PROVEN — coverage {c['percent']}% < threshold {c['threshold']}%")
    print("=" * 68)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulting Readiness Gate — auditable coverage readiness assessment",
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        default=DEFAULT_RADIUS_KM,
        help=f"Radius from Florianópolis in km (default: {DEFAULT_RADIUS_KM})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Coverage threshold for PASS (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--seed",
        type=str,
        default=None,
        help=f"Path to seed Excel file (default: {DEFAULT_SEED})",
    )

    args = parser.parse_args()

    # ── 1. Load target universe ──────────────────────────────────────────
    try:
        print("Loading target universe from seed file...")
        universe = load_target_universe(args.seed, args.radius_km)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(
        f"   Universe: {universe.total_resolved} resolved, "
        f"{universe.total_unresolved} unresolved, "
        f"{universe.total_within_radius} within radius"
    )

    if universe.total_resolved == 0 and universe.total_unresolved == 0:
        print("❌ No entities found in seed file.", file=sys.stderr)
        return 1

    # ── 2. Connect to PostgreSQL ─────────────────────────────────────────
    try:
        conn = _get_conn()
    except ConnectionError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    try:
        # ── 3. Load DB data ──────────────────────────────────────────────
        print("Loading evidence ledger...")
        evidence = load_evidence(conn)
        print(f"   Evidence rows: {len(evidence)}")

        print("Loading source health...")
        source_health = load_source_health(conn)
        print(f"   Source health entries: {len(source_health)}")

        print("Loading entity coverage...")
        coverage_rows = load_entity_coverage(conn)
        print(f"   Entity coverage rows: {len(coverage_rows)}")

        cnpj8_list = [e.cnpj8 for e in universe.entities if e.cnpj8]
        print(f"Loading entity data for {len(cnpj8_list)} CNPJ8 roots...")
        entity_data = load_entity_data(conn, cnpj8_list)
        print(f"   Matched entities in DB: {len(entity_data)}")

        # ── 4. Compute readiness ─────────────────────────────────────────
        print("Computing readiness metrics...")
        metrics = compute_readiness(
            universe,
            evidence,
            source_health,
            coverage_rows,
            entity_data,
            conn,
            args.threshold,
        )

        conn.close()
    except Exception as e:
        print(f"❌ Data loading/computation failed: {e}", file=sys.stderr)
        try:
            conn.close()
        except Exception:
            pass
        return 1

    # ── 5. Generate output artifacts ─────────────────────────────────────
    os.makedirs(args.output_dir, exist_ok=True)

    manifest_path = write_manifest(metrics, args.output_dir)
    print(f"\n📄 Manifest: {manifest_path}")

    gaps_path = write_gaps_csv(metrics, args.output_dir)
    print(f"📄 Gaps CSV: {gaps_path}")

    # ── 6. Print summary ─────────────────────────────────────────────────
    print()
    print_summary(metrics)

    # ── 7. Determine exit code ───────────────────────────────────────────
    if metrics["coverage"]["passed"]:
        return 0
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())
