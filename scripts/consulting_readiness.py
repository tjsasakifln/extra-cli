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
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.lib.universe import normalize_cnpj8

_logger = logging.getLogger(__name__)

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

# Known-blocked sources that must NEVER be reported as success.
# Each entry documents why the source cannot execute in the current
# environment (missing credentials, Selenium dependency, etc.).
# These override whatever the DB view says.
SOURCE_BLOCKERS: dict[str, str] = {
    "doe_sc": "Requer Selenium + certificado digital",
    "dom_sc": "Portal requer navegação interativa (Selenium)",
    "pcp": "Portal requer Selenium + CAPTCHA",
    "sc_compras": "API não documentada, acesso instável",
    "transparencia": "Portais individuais por município (295+)",
    "mides_bigquery": "BigQuery requer credencial GCP",
    "selenium": "Não é fonte, é infraestrutura de acesso",
}

# Column mapping for the seed spreadsheet "Extra - alvos de licitação. R-0.xlsx" (0-indexed)
COL_RAZAO = 0
COL_CNPJ8 = 1
COL_MUNICIPIO = 2
COL_IBGE = 3
COL_NATUREZA = 4
COL_COD_NATUREZA = 5
COL_LATITUDE = 6
COL_LONGITUDE = 7
COL_DISTANCIA_SEED = 8  # Pre-calculated distance from Florianopolis (km)
COL_RAIO200 = 9  # AUTHORITATIVE radius flag: "SIM ✓" or "NÃO"

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
            f"Authoritative radius flag from spreadsheet column 'Raio 200km?' "
            f"({self.radius_km:.1f} km radius from Florianopolis). "
            f"'SIM ✓' = within radius, 'NÃO' = outside. "
            f"Uses spreadsheet 'Distância de Florianópolis (km)' as authoritative distance. "
            f"Entities with coords + flag are resolved; entities with flag only are resolved "
            f"(flag takes precedence). "
            f"Haversine fallback only for entities added after the spreadsheet "
            f"without a radius flag."
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
        cnpj8 = normalize_cnpj8(str(row[COL_CNPJ8])) if len(row) > COL_CNPJ8 and row[COL_CNPJ8] else ""
        municipio = str(row[COL_MUNICIPIO]).strip() if len(row) > COL_MUNICIPIO and row[COL_MUNICIPIO] else ""
        ibge = str(int(row[COL_IBGE])) if len(row) > COL_IBGE and row[COL_IBGE] else ""
        natureza = str(row[COL_NATUREZA]).strip() if len(row) > COL_NATUREZA and row[COL_NATUREZA] else ""

        # ── Parse coordinates ────────────────────────────────────────
        lat_raw = row[COL_LATITUDE] if len(row) > COL_LATITUDE else None
        lon_raw = row[COL_LONGITUDE] if len(row) > COL_LONGITUDE else None
        lat, lon, has_coords = _parse_coords(lat_raw, lon_raw)

        # ── Parse distance ───────────────────────────────────────────
        # (Must compute dist early — fallback radius check uses it)
        dist_raw = row[COL_DISTANCIA_SEED] if len(row) > COL_DISTANCIA_SEED else None
        dist = 0.0
        if dist_raw is not None:
            try:
                dist = float(dist_raw)
            except (ValueError, TypeError):
                dist = haversine_km(FLORIANOPOLIS_LAT, FLORIANOPOLIS_LON, lat, lon) if has_coords else 0.0
        else:
            dist = haversine_km(FLORIANOPOLIS_LAT, FLORIANOPOLIS_LON, lat, lon) if has_coords else 0.0

        # ── Read spreadsheet's AUTHORITATIVE radius flag ──────────────
        # Column "Raio 200km?" = "SIM ✓" within radius, "NÃO" outside
        raio_flag = str(row[COL_RAIO200]).strip() if len(row) > COL_RAIO200 and row[COL_RAIO200] else ""

        # Authoritative radius flag (takes precedence even without coordinates)
        if raio_flag == "SIM ✓":
            within = True
        elif raio_flag == "NÃO":
            within = False
        else:
            # Truly unresolved: no radius flag AND no coordinates
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
            # Fallback: coordinates exist but no radius flag
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
            distancia_km=round(dist, 1) if has_coords else None,
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


def _safe_metric_query(
    conn,
    query_name: str,
    query: str,
    params: tuple | list | None = None,
    timeout: str = "30s",
) -> list[dict] | None:
    """Execute metric query with per-query timeout and transaction isolation.

    Uses ``SET LOCAL statement_timeout`` for per-query timeout so that even
    if the connection has a global ``statement_timeout``, this per-query value
    overrides it for the current transaction.

    On failure (timeout, connection error, etc.), rolls back the aborted
    transaction so subsequent queries on the same connection are not affected
    by PostgreSQL's "current transaction is aborted" state.

    Returns:
        List[dict] on success, ``None`` on failure (transaction rolled back).
    """
    _logger.info("Running metric query: %s (timeout=%s)", query_name, timeout)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = %s", (timeout,))
            cur.execute(query, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        conn.rollback()
        _logger.error("Metric query failed: name=%s error=%s timeout=%s", query_name, e, timeout)
        return None


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
    """Count open tenders (pncp_raw_bids) per entity_id.

    A bid is considered open when:
    1. data_encerramento >= CURRENT_DATE (confirmed by deadline), OR
    2. data_encerramento IS NULL AND data_publicacao within 90 days
       (inferred open — recent enough to still be active), OR
    3. data_encerramento IS NULL AND data_publicacao within 180 days
       AND modalidade is 'dispensa'/'inexigibilidade'/'credenciamento'
       (these modalities don't have formal closing dates), OR
    4. data_encerramento IS NULL AND data_abertura >= CURRENT_DATE
       (upcoming — still to open)
    """
    if not entity_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        """SELECT matched_entity_id, COUNT(*) AS cnt
           FROM pncp_raw_bids
           WHERE matched_entity_id = ANY(%s)
             AND is_active = TRUE
             AND (
               data_encerramento >= CURRENT_DATE
               OR
               (data_encerramento IS NULL
                AND data_publicacao >= CURRENT_DATE - INTERVAL '90 days')
               OR
               (data_encerramento IS NULL
                AND data_publicacao >= CURRENT_DATE - INTERVAL '180 days'
                AND LOWER(TRIM(COALESCE(modalidade_nome, '')))
                    IN ('dispensa', 'inexigibilidade', 'inegixibilidade',
                        'credenciamento', 'adesao', 'chamamento publico',
                        'chamada publica'))
               OR
               (data_encerramento IS NULL
                AND data_publicacao IS NULL
                AND data_abertura >= CURRENT_DATE)
             )
           GROUP BY matched_entity_id""",
        (entity_ids,),
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return result


def count_contracts(conn, entity_cnpj8_list: list[str]) -> dict[str, int]:
    """Count contracts per organ CNPJ8 using pre-computed entity_coverage.

    Uses entity_coverage (source='contracts') instead of scanning the raw
    pncp_supplier_contracts table (3.7M rows) which crashes the DB.
    """
    if not entity_cnpj8_list:
        return {}
    cur = conn.cursor()
    try:
        # Fast path: use entity_coverage pre-computed counts
        cur.execute(
            """SELECT e.cnpj_8, ec.total_bids
               FROM entity_coverage ec
               JOIN sc_public_entities e ON e.id = ec.entity_id
               WHERE ec.source = 'contracts'
                 AND ec.total_bids > 0
                 AND e.cnpj_8 = ANY(%s)""",
            (entity_cnpj8_list,),
        )
        result = {row[0]: row[1] for row in cur.fetchall()}
    except Exception:
        _logger.exception("Failed to count contracts for %d entities", len(entity_cnpj8_list))
        # Fallback: empty result (graceful degradation)
        result = {}
    cur.close()
    return result


# ---------------------------------------------------------------------------
# Commercial metrics computation (value semantics, entity price differential, relicitacao)
# ---------------------------------------------------------------------------


def _compute_contract_value_aggregation(conn) -> dict[str, Any]:
    """Aggregate contract values in the target universe.

    Returns semantic status: PNCP ``valor_global`` IS the contracted value
    (``valor_contratado``), but it is NOT "preco praticado" because it
    does not reflect partial payments, renegotiations, or terminations.
    """
    try:
        rows = _safe_metric_query(
            conn,
            "contract_value_agg",
            """SELECT
                  COUNT(*) AS total_contracts,
                  COUNT(CASE WHEN c.valor_global > 0 THEN 1 END) AS with_value,
                  ROUND(SUM(c.valor_global)::numeric, 2) AS total_value,
                  ROUND(AVG(c.valor_global)::numeric, 2) AS avg_value,
                  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.valor_global)::numeric, 2) AS median_value,
                  MIN(c.valor_global) AS min_value,
                  MAX(c.valor_global) AS max_value
               FROM pncp_supplier_contracts c
               JOIN sc_public_entities e ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
               WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
                 AND e.is_active IS TRUE
                 AND c.valor_global > 0""",
            timeout="30s",
        )
        if rows is None:
            return {
                "status": "error",
                "reason": "Contract value aggregation query failed (timeout or connection error)",
                "value": None,
            }
        row = rows[0] if rows else {}
        total = float(row.get("total_value", 0) or 0)
        count = int(row.get("total_contracts", 0) or 0)
        avg = float(row.get("avg_value", 0) or 0)
        median = float(row.get("median_value", 0) or 0)

        return {
            "status": "ready",
            "reason": (
                "Contract value semantics implemented. PNCP valor_global "
                "representa valor contratado (firmado), nao preco praticado. "
                "Diferenca conceitual documentada em scripts/lib/value_semantics.py. "
                "Preco praticado requer dados de empenho/pagamento (TCE/SC)."
            ),
            "value": {
                "total_contracts": count,
                "contracts_with_value": int(row.get("with_value", 0) or 0),
                "total_value_brl": total,
                "avg_value_brl": avg,
                "median_value_brl": median,
                "semantica": "valor_contratado (valor_global PNCP)",
                "note": (
                    "Valor global PNCP = valor contratado (assinado). "
                    "Nao inclui renegociacoes, aditivos ou pagamentos parciais."
                ),
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _logger.error("contract_total_value failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "reason": f"Falha ao agregar valores de contrato: {exc}",
            "value": None,
        }


def _compute_entity_price_differential(conn) -> dict[str, Any]:
    """Compute entity-level price differential between estimated and contracted values.

    CRITICAL LIMITATION — this is NOT desagio (real discount).
    PNCP does NOT provide item-level linkage between estimated bid values and
    contracted/homologated values. Therefore, this function computes a
    POPULATION-LEVEL entity price differential:

    - Average ``valor_total_estimado`` from ``pncp_raw_bids`` per entity
    - Average ``valor_global`` from ``pncp_supplier_contracts`` per entity
    - Difference expressed as percentage of estimated average

    What this IS: entity-level comparison of population averages.
    What this is NOT: real desagio (requires tracking the same item from
    bid through homologation/contract).

    Requirements for READY desagio:
    - ``bid_contract_linkage``: PNCP does not provide bid→contract item-level link
    - ``item_level_tracking``: PNCP does not expose item-level tracking
    - ``proposal_tracking``: requires complementary spreadsheet (ComprasGov/TCE data)

    The minimum viable metric is entity_price_differential, which warns
    readers it is NOT item-level desagio.
    """
    try:
        rows = _safe_metric_query(
            conn,
            "entity_price_differential",
            """WITH entity_bid_avg AS (
                  SELECT b.matched_entity_id AS eid,
                         AVG(b.valor_total_estimado) AS avg_estimado
                  FROM pncp_raw_bids b
                  WHERE b.matched_entity_id IS NOT NULL
                    AND b.valor_total_estimado > 0
                    AND b.is_active = TRUE
                  GROUP BY b.matched_entity_id
                ),
                entity_contract_avg AS (
                  SELECT e.id AS eid,
                         AVG(c.valor_global) AS avg_contratado
                  FROM sc_public_entities e
                  JOIN pncp_supplier_contracts c
                    ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
                  WHERE e.raio_200km IS TRUE AND e.is_active IS TRUE
                    AND c.is_active IS TRUE AND c.valor_global > 0
                  GROUP BY e.id
                )
                SELECT COUNT(*) AS entities_with_both,
                       ROUND(AVG(ea.avg_estimado)::numeric, 2) AS avg_estimado_entity,
                       ROUND(AVG(ec.avg_contratado)::numeric, 2) AS avg_contratado_entity,
                       ROUND(
                         (AVG(ea.avg_estimado) - AVG(ec.avg_contratado))
                         / NULLIF(AVG(ea.avg_estimado), 0) * 100
                       , 2) AS desagio_pct_estimado
                FROM entity_bid_avg ea
                JOIN entity_contract_avg ec ON ea.eid = ec.eid
                JOIN sc_public_entities e ON e.id = ea.eid
                WHERE e.raio_200km IS TRUE AND e.is_active IS TRUE""",
            timeout="30s",
        )
        if rows is None:
            return {
                "status": "error",
                "reason": "Desagio query failed (timeout or connection error)",
                "value": None,
            }
        row = rows[0] if rows else {}
        entities_with_both = int(row.get("entities_with_both", 0) or 0)
        pct_diff = float(row.get("desagio_pct_estimado", 0) or 0)
        avg_estimado = float(row.get("avg_estimado_entity", 0) or 0)
        avg_contratado = float(row.get("avg_contratado_entity", 0) or 0)

        if entities_with_both > 0:
            price_differential = {
                "entities_with_both": entities_with_both,
                "avg_estimado_by_entity_brl": avg_estimado,
                "avg_contratado_by_entity_brl": avg_contratado,
                "price_differential_pct": round(pct_diff, 2),
                "semantica": "estimado→contratado (populacional por entidade)",
                "note": (
                    "Diferenca entre medias populacionais por entidade. "
                    "Nao reflete desagio real item-a-item da mesma licitacao/lote. "
                    "O desagio REAL (homologado) requer linkage bid-item-contrato."
                ),
                "entities_without_contracts": None,
            }
            return {
                "status": "NOT_READY",
                "readiness": "LIMITED",
                "reason": (
                    "PNCP nao prove linkage item-a-item entre valor estimado e valor "
                    "homologado/contratado. Calculo atual e DIFERENCIAL DE PRECO "
                    "POPULACIONAL por orgao (medias agregadas), nao desagio real. "
                    f"Diferencial medio: {pct_diff:.1f}% para {entities_with_both} "
                    f"entidades com dados de estimado e contratado. "
                    "Desagio READY exigiria tracking do mesmo item desde o edital ate "
                    "a homologacao."
                ),
                "available_metric": "entity_price_differential",
                "price_differential": price_differential,
                "desagio_readiness_requirements": {
                    "bid_contract_linkage": False,
                    "item_level_tracking": False,
                    "proposal_tracking": False,
                    "minimum_viable": "entity_price_differential",
                },
            }
        return {
            "status": "NOT_READY",
            "readiness": "LIMITED",
            "reason": (
                "Nenhuma entidade no raio 200km possui dados simultaneos de "
                "valor estimado (pncp_raw_bids) e contratado (pncp_supplier_contracts). "
                "Mesmo com dados, o calculo seria diferencial populacional, nao desagio real."
            ),
            "available_metric": "entity_price_differential",
            "price_differential": None,
            "desagio_readiness_requirements": {
                "bid_contract_linkage": False,
                "item_level_tracking": False,
                "proposal_tracking": False,
                "minimum_viable": "entity_price_differential",
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _logger.error("entity_price_differential failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "reason": f"Falha ao computar diferencial de precos: {exc}",
            "available_metric": "entity_price_differential",
            "price_differential": None,
            "desagio_readiness_requirements": {
                "bid_contract_linkage": False,
                "item_level_tracking": False,
                "proposal_tracking": False,
                "minimum_viable": "entity_price_differential",
            },
        }


def _compute_relicitacao_stats(conn) -> dict[str, Any]:
    """Compute relicitation probability indicators from contract end dates.

    Indicators:
    - Contracts ending per year → renewal opportunity density
    - Contracts without end date → vigency tracking gap
    - Average contract duration → replacement cycle estimate
    """
    try:
        rows = _safe_metric_query(
            conn,
            "relicitacao_stats",
            """SELECT
                  COUNT(*) AS total_contratos,
                  COUNT(CASE WHEN c.data_fim_vigencia IS NOT NULL THEN 1 END) AS com_data_fim,
                  COUNT(CASE WHEN c.data_fim_vigencia IS NULL THEN 1 END) AS sem_data_fim,
                  ROUND(AVG(
                    CASE WHEN c.data_fim_vigencia IS NOT NULL AND c.data_assinatura IS NOT NULL
                    THEN (c.data_fim_vigencia - c.data_assinatura) END
                  )::numeric, 0) AS avg_duration_days,
                  COUNT(CASE
                    WHEN c.data_fim_vigencia IS NOT NULL
                    AND c.data_fim_vigencia BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '1 year')
                    THEN 1 END) AS ending_next_12m
               FROM pncp_supplier_contracts c
               JOIN sc_public_entities e ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
               WHERE e.raio_200km IS TRUE AND c.is_active IS TRUE
                 AND e.is_active IS TRUE""",
            timeout="30s",
        )
        if rows is None:
            return {
                "status": "error",
                "reason": "Relicitacao stats query failed (timeout or connection error)",
                "value": None,
            }
        row = rows[0] if rows else {}
        total = int(row.get("total_contratos", 0) or 0)
        com_data_fim = int(row.get("com_data_fim", 0) or 0)
        sem_data_fim = int(row.get("sem_data_fim", 0) or 0)
        avg_duration = float(row.get("avg_duration_days", 0) or 0)
        ending_12m = int(row.get("ending_next_12m", 0) or 0)

        pct_sem_fim = round((sem_data_fim / total * 100), 1) if total > 0 else 0.0

        if total > 0 and com_data_fim > 10:
            return {
                "status": "ready",
                "reason": (
                    f"{ending_12m} contratos encerrando nos proximos 12 meses "
                    f"no target universe. Duracao media de {avg_duration:.0f} dias. "
                    f"Probabilidade de relicitacao inferida da densidade de terminos. "
                    f"Modelo preditivo requer serie historica de renovacoes (dado "
                    f"ausente no PNCP)."
                ),
                "value": {
                    "total_contracts_in_universe": total,
                    "contracts_with_end_date": com_data_fim,
                    "contracts_without_end_date": sem_data_fim,
                    "pct_without_end_date": pct_sem_fim,
                    "avg_duration_days": avg_duration,
                    "avg_duration_years": round(avg_duration / 365.25, 1),
                    "contracts_ending_next_12m": ending_12m,
                    "renewal_density_pct": round(ending_12m / total * 100, 1) if total > 0 else 0.0,
                    "vigency_tracking_gap": (
                        f"{pct_sem_fim}% dos contratos nao possuem "
                        f"data_fim_vigencia — rastreamento de vigencia comprometido"
                    ),
                    "note": (
                        "Data_fim_vigencia e o melhor proxy PNCP para prazo contratual. "
                        "PNCP nao expoe renovacoes — renovacao e inferida por "
                        "contratos subsequentes entre mesmo orgao e fornecedor."
                    ),
                },
            }

        return {
            "status": "limited",
            "reason": (
                f"Dados insuficientes: {total} contratos, apenas "
                f"{com_data_fim} com data_fim_vigencia. "
                f"Rastreamento de vigencia comprometido ({pct_sem_fim}% sem data fim)."
            ),
            "value": {
                "total_contracts_in_universe": total,
                "contracts_with_end_date": com_data_fim,
                "contracts_without_end_date": sem_data_fim,
                "pct_without_end_date": pct_sem_fim,
                "avg_duration_days": avg_duration,
                "contracts_ending_next_12m": ending_12m,
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _logger.error("relicitacao_stats failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "reason": f"Falha ao computar estatisticas de relicitacao: {exc}",
            "value": None,
        }


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


def _apply_source_blockers(
    health: dict[str, dict[str, Any]],
    per_source: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Override source health for known-blocked sources.

    Rule #3 — ``success_zero`` requires applicable source with declared
    window, complete pagination, and recent real execution.  Sources that
    require credentials, Selenium, or other unavailable infrastructure
    are reclassified to ``blocked`` or ``not_applicable``, NEVER ``success_*``.

    Logs a warning for each reclassified source.
    """
    for src in list(health.keys()):
        if src not in SOURCE_BLOCKERS:
            continue

        reason = SOURCE_BLOCKERS[src]
        status = "not_applicable" if src == "selenium" else "blocked"

        _logger.warning(
            "Source '%s' reclassified as %s: %s",
            src,
            status,
            reason,
        )

        health[src] = {
            "entity_rows": 0,
            "successful": 0,
            "failed": 0,
            "health_pct": None,
            "last_check": None,
            "status": status,
            "blocker_reason": reason,
        }

    # Apply blockers to per_source breakdown as well
    if per_source is not None:
        for src in list(per_source.keys()):
            if src in SOURCE_BLOCKERS:
                reason = SOURCE_BLOCKERS[src]
                status = "not_applicable" if src == "selenium" else "blocked"
                per_source[src]["status"] = status
                per_source[src]["blocker_reason"] = reason
                per_source[src]["pct"] = None

    return health


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

    # ── Apply SOURCE_BLOCKERS override ──────────────────────────────────
    # Rule #3: known-blocked sources are never "success", even if the DB
    # view reports phantom entity rows.
    _apply_source_blockers(health, per_source)

    # ── Commercial metrics — computed from DB ───────────────────────────
    # NOTE: Heavy contract queries use a SEPARATE connection with per-query
    # statement_timeout via _safe_metric_query() so that a timeout on one
    # metric query does not cascade to the others (transaction isolation).
    #
    # TODO: Add index on pncp_supplier_contracts(orgao_cnpj) to prevent
    # full table scans (3.7M rows). The LIKE e.cnpj_8 || '%' join pattern
    # causes seq scans that trigger statement_timeout.
    import os as _os

    import psycopg2 as _pg2

    _commercial_dsn = _os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")
    try:
        _commercial_conn = _pg2.connect(_commercial_dsn, connect_timeout=5)
        # No global SET statement_timeout -- cada _safe_metric_query()
        # define per-query timeout via SET LOCAL, garantindo que um
        # timeout em uma metrica nao afete as demais.
        try:
            contract_value_agg = _compute_contract_value_aggregation(_commercial_conn)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after contract value query failure")
            contract_value_agg = {"status": "error", "reason": f"Contract value query failed: {exc}", "value": None}
        try:
            desagio_stats = _compute_entity_price_differential(_commercial_conn)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after price differential query failure")
            desagio_stats = {"status": "error", "reason": f"Price differential query failed: {exc}", "value": None}
        try:
            relicitacao_stats = _compute_relicitacao_stats(_commercial_conn)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after relicitacao query failure")
            relicitacao_stats = {"status": "error", "reason": f"Relicitacao query failed: {exc}", "value": None}
        _commercial_conn.close()
    except Exception as exc:
        contract_value_agg = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}
        desagio_stats = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}
        relicitacao_stats = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}

    commercial_metrics = {
        "contract_total_value": {
            "status": contract_value_agg["status"],
            "reason": contract_value_agg["reason"],
            "value": contract_value_agg["value"],
        },
        "desagio": {
            "status": desagio_stats["status"],
            "readiness": desagio_stats.get("readiness"),
            "reason": desagio_stats["reason"],
            "available_metric": desagio_stats.get("available_metric", "entity_price_differential"),
            "price_differential": desagio_stats.get("price_differential"),
            "desagio_readiness_requirements": desagio_stats.get("desagio_readiness_requirements"),
        },
        "win_rate": {
            "status": "manual",
            "reason": (
                "Win rate requer tracking manual de propostas enviadas vs vencidas "
                "por CNPJ. PNCP não expõe propostas perdedoras. "
                "Alimentar planilha complementar com colunas: "
                "data_envio, orgao, cnpj_licitante, valor_proposta, venceu (S/N)."
            ),
        },
        "relicitacao_probability": {
            "status": relicitacao_stats["status"],
            "reason": relicitacao_stats["reason"],
            "value": relicitacao_stats["value"],
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
    print("  SOURCE HEALTH:")
    for src, info in sorted(metrics.get("source_health", {}).items()):
        status = info.get("status", "")
        hp = info.get("health_pct")
        last = info.get("last_check") or "never"
        if status:
            reason = info.get("blocker_reason", "")
            print(f"    {src:<20s}  [{status:<15s}]  {reason}")
        elif hp is not None:
            print(f"    {src:<20s}  health={hp:>6.1f}%  last_check={last}")
        else:
            print(f"    {src:<20s}  health=unverified  last_check={last}")
    print()
    print("  COMMERCIAL METRICS:")
    cm = metrics.get("commercial_metrics", {})
    for name, info in cm.items():
        status = info.get("status", "unknown")
        reason = info.get("reason", "")
        value = info.get("value")
        print(f"    {name}: [{status}]")
        if value:
            if name == "contract_total_value" and isinstance(value, dict):
                print(f"      Total contratos:      {value.get('total_contracts', 'N/A')}")
                print(f"      Valor total (R$):     {value.get('total_value_brl', 'N/A'):>15,.2f}")
                print(f"      Ticket medio (R$):    {value.get('avg_value_brl', 'N/A'):>15,.2f}")
                print(f"      Mediana (R$):         {value.get('median_value_brl', 'N/A'):>15,.2f}")
                print(f"      Semantica:            {value.get('semantica', 'N/A')}")
            if name == "desagio":
                readiness = info.get("readiness", "")
                print(f"      [readiness: {readiness}]")
                pd = info.get("price_differential")
                if pd and pd.get("entities_with_both", 0) > 0:
                    print(f"      Entidades com ambos:  {pd['entities_with_both']}")
                    print(f"      Diferencial medio:    {pd.get('price_differential_pct', 'N/A')}%")
                else:
                    print("      (sem dados de precos)")
            if name == "relicitacao_probability" and isinstance(value, dict):
                print(f"      Contratos total:       {value.get('total_contracts_in_universe', 'N/A')}")
                print(f"      Com data fim:          {value.get('contracts_with_end_date', 'N/A')}")
                print(f"      Sem data fim:          {value.get('contracts_without_end_date', 'N/A')}")
                print(f"      Encerrando 12m:        {value.get('contracts_ending_next_12m', 'N/A')}")
                print(f"      Duracao media (dias):  {value.get('avg_duration_days', 'N/A'):,.0f}")
        print(f"      → {reason[:120]}")
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
            _logger.warning("Failed to close DB connection after data loading failure")
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
