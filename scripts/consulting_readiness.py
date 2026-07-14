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
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.lib.universe import (
    CanonicalUniverse,
    load_canonical_universe,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLORIANOPOLIS_LAT = -27.5954
FLORIANOPOLIS_LON = -48.5480
DEFAULT_RADIUS_KM = 200.0
DEFAULT_THRESHOLD = 0.95
COVERAGE_WINDOW_DAYS = int(os.getenv("COVERAGE_WINDOW_DAYS", "90"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = str(PROJECT_ROOT / "Extra - alvos de licitação. R-0.xlsx")
DEFAULT_OUTPUT_DIR = str(PROJECT_ROOT / "output" / "readiness")

# Backward compatibility: exported for tests that import from consulting_readiness
# (Story 1.3 refactored to CanonicalUniverse; these aliases preserve test compatibility)
from scripts.lib.universe import (  # noqa: E402 — import after sys.path hacks for project root
    CanonicalEntity,
)


class TargetEntity(CanonicalEntity):
    """Backward-compatible alias (Story 1.3)."""


class TargetUniverse:
    """Backward-compatible wrapper around CanonicalUniverse (Story 1.3).

    Legacy tests may pass ``total_seed_rows``, ``total_resolved``,
    ``total_unresolved``, ``total_within_radius``, etc. as keyword
    arguments. These are stored as attributes for backward compatibility.
    """

    inclusion_rule = (
        "Circle (200 km radius from Florianopolis using haversine). "
        "Only the spreadsheet is the authority — database radius flags "
        "are diagnostic data, never a denominator."
    )

    def __init__(self, entities=None, radius_km=None, **kwargs):
        if radius_km is not None:
            kwargs.setdefault("radius_km", radius_km)
        for key, value in kwargs.items():
            setattr(self, key, value)
        if entities is None:
            self._canonical = None  # empty state for tests
        else:
            self._canonical = CanonicalUniverse(
                seed_path=DEFAULT_SEED,
                seed_sha256="",
                radius_km=radius_km or DEFAULT_RADIUS_KM,
            )
        self.entities = entities or {}

    def __getattr__(self, name):
        if self._canonical is not None and hasattr(self._canonical, name):
            return getattr(self._canonical, name)
        # Backward compat: compute properties from self.entities when
        # _canonical is None (legacy test mode with **kwargs construction).
        if name == "included":
            return [e for e in self.entities if getattr(e, "within_radius", None) is True]
        if name == "excluded":
            return [e for e in self.entities if getattr(e, "within_radius", None) is False]
        if name == "unresolved":
            return [e for e in self.entities if getattr(e, "within_radius", None) is None]
        if name == "conservative_monitoring_population":
            return [e for e in self.entities if getattr(e, "within_radius", None) is not False]
        if name == "radius_km":
            return getattr(self, "_radius_km", DEFAULT_RADIUS_KM)
        if name == "seed_path":
            return ""
        if name == "seed_sha256":
            return ""
        if name == "summary":
            _total = len(self.entities)
            _resolved = _total - len(self.unresolved)
            _den = max(_total, 1)
            _pct = round(min(100.0, max(0.0, _resolved / _den * 100.0)), 2)
            return lambda: {
                "seed_path": "",
                "seed_sha256": "",
                "radius_km": getattr(self, "radius_km", DEFAULT_RADIUS_KM),
                "total_seed_rows": _total,
                "resolved_rows": _resolved,
                "unresolved_rows": len(self.unresolved),
                "within_radius": len(self.included),
                "outside_radius": len(self.excluded),
                "conservative_monitoring_denominator": len(self.conservative_monitoring_population),
                "universe_resolution_coverage_percent": _pct,
                "duplicate_cnpj_roots": [],
                "suspicious_duplicate_keys": [],
                "db_matched_rows": 0,
                "identity_formula": "",
                "radius_formula": "",
            }
        raise AttributeError(name)

    def __len__(self):
        return len(self.entities)

    def __iter__(self):
        return iter(self.entities.values())


import math  # noqa: E402 — module-level import after class definitions with backward compat

EARTH_RADIUS_KM = 6371.0  # noqa: N816


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two points using Haversine formula."""
    R = 6371.0  # noqa: N806
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def load_target_universe(path=None, radius_km=None):
    """Backward-compatible wrapper around CanonicalUniverse (Story 1.3)."""
    from scripts.lib.universe import CanonicalUniverse

    return CanonicalUniverse(path or DEFAULT_SEED, radius_km or DEFAULT_RADIUS_KM)


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

# ---------------------------------------------------------------------------
# Universe adapter
# ---------------------------------------------------------------------------


def _make_summary(universe) -> dict:
    """CanonicalUniverse.summary() to legacy dict for print_summary compat."""
    s = universe.summary()
    return {
        "seed_file": universe.seed_path,
        "total_seed_rows": s["total_seed_rows"],
        "confirmed_universe": s["resolved_rows"],
        "potential_universe": s["total_seed_rows"],
        "unresolved": s["unresolved_rows"],
        "duplicates": len(s["duplicate_cnpj_roots"]),
        "within_radius": s["within_radius"],
        "outside_radius": s["outside_radius"],
        "duplicate_cnpj8_list": s["duplicate_cnpj_roots"],
        "unresolved_entities": [],
        "inclusion_rule": s["radius_formula"],
        "center_lat": FLORIANOPOLIS_LAT,
        "center_lon": FLORIANOPOLIS_LON,
        "radius_km": universe.radius_km,
    }


# ---------------------------------------------------------------------------
# Database helpers (PostgreSQL only — no SQLite fallback)
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    return os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://postgres@127.0.0.1:5433/pncp_datalake",
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
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
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
                "reason": "Entity price differential query failed (timeout or connection error)",
                "available_metric": "entity_price_differential",
                "price_differential": None,
                "desagio_readiness_requirements": {
                    "bid_contract_linkage": False,
                    "item_level_tracking": False,
                    "proposal_tracking": False,
                    "minimum_viable": "entity_price_differential",
                },
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
                "status": "not_ready",
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
            "status": "not_ready",
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
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
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
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
            pass
        _logger.error("relicitacao_stats failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "reason": f"Falha ao computar estatisticas de relicitacao: {exc}",
            "value": None,
        }


# ---------------------------------------------------------------------------
# Competitive Intelligence (Regra #9) — market share, award share, HHI, ranking
# ---------------------------------------------------------------------------
# Regra #9: "Contratos vencidos/total de licitações não é win rate. Sem
# participações, publicar market share, award share, ranking e HHI. Win rate
# real exige proposal_tracking."
# ---------------------------------------------------------------------------


def _compute_market_share(conn, entity_cnpj8_list: list[str]) -> dict[str, Any]:
    """Compute supplier market share within the canonical universe.

    Market share = supplier's contracts (or value) as % of total universe
    contracts and value.

    Returns:
        dict with ``status``, ``reason``, and ``value`` containing top
        suppliers with contract_share_pct and value_share_pct.
    """
    try:
        # ── Universe totals (denominator) ───────────────────────────────
        universe_rows = _safe_metric_query(
            conn,
            "market_share_universe",
            """SELECT
                  COUNT(DISTINCT c.contrato_id) AS total_contracts,
                  SUM(c.valor_global) AS total_value
               FROM pncp_supplier_contracts c
               INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
               WHERE e.raio_200km IS TRUE
                 AND c.fornecedor_cnpj IS NOT NULL
                 AND c.is_active IS TRUE""",
            timeout="60s",
        )
        if universe_rows is None:
            return {"status": "error", "reason": "Market share universe query failed", "value": None}

        universe_row = universe_rows[0] if universe_rows else {}
        total_contracts = float(universe_row.get("total_contracts", 0) or 0)
        total_value = float(universe_row.get("total_value", 0) or 0)

        if total_contracts == 0:
            return {"status": "no_data", "reason": "No contracts found in universe", "value": None}

        # ── Per-supplier stats ─────────────────────────────────────────
        supplier_rows = _safe_metric_query(
            conn,
            "market_share_suppliers",
            """SELECT
                  c.fornecedor_cnpj,
                  c.fornecedor_nome,
                  COUNT(DISTINCT c.contrato_id) AS total_contracts,
                  SUM(c.valor_global) AS total_value,
                  COUNT(DISTINCT c.orgao_cnpj) AS entities_served
               FROM pncp_supplier_contracts c
               INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
               WHERE e.raio_200km IS TRUE
                 AND c.fornecedor_cnpj IS NOT NULL
                 AND c.is_active IS TRUE
               GROUP BY c.fornecedor_cnpj, c.fornecedor_nome
               ORDER BY total_value DESC""",
            timeout="60s",
        )
        if supplier_rows is None:
            return {"status": "error", "reason": "Market share supplier query failed", "value": None}

        top_suppliers: list[dict[str, Any]] = []
        for row in supplier_rows:
            supplier_contracts = float(row.get("total_contracts", 0) or 0)
            supplier_value = float(row.get("total_value", 0) or 0)
            top_suppliers.append(
                {
                    "fornecedor_cnpj": row.get("fornecedor_cnpj"),
                    "fornecedor_nome": row.get("fornecedor_nome"),
                    "total_contracts": int(supplier_contracts),
                    "total_value_brl": round(supplier_value, 2),
                    "contract_share_pct": round(supplier_contracts / total_contracts * 100, 2)
                    if total_contracts > 0
                    else 0.0,
                    "value_share_pct": round(supplier_value / total_value * 100, 2) if total_value > 0 else 0.0,
                    "entities_served": int(row.get("entities_served", 0) or 0),
                }
            )

        return {
            "status": "ready",
            "reason": (
                f"Market share computed for {len(top_suppliers)} suppliers "
                f"in the {int(total_contracts):,}-contract universe. "
                f"Total universe value: R$ {total_value:,.2f}."
            ),
            "value": {
                "total_suppliers": len(top_suppliers),
                "total_contracts_in_universe": int(total_contracts),
                "total_value_in_universe_brl": round(total_value, 2),
                "top_suppliers": top_suppliers[:100],
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
            pass
        _logger.error("market_share computation failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": f"Market share computation failed: {exc}", "value": None}


def _compute_award_share(conn, entity_cnpj8_list: list[str]) -> dict[str, Any]:
    """Compute award concentration per entity.

    For each public entity in the 200km radius, lists the top suppliers
    by both contract count and contract value, along with their share
    of the entity's total awards.

    Returns:
        dict with ``by_entity`` list showing each entity's top suppliers.
    """
    try:
        rows = _safe_metric_query(
            conn,
            "award_share",
            """WITH entity_supplier_stats AS (
                  SELECT
                    e.cnpj_8 AS entity_cnpj8,
                    e.razao_social AS entity_name,
                    c.fornecedor_cnpj,
                    c.fornecedor_nome,
                    COUNT(DISTINCT c.contrato_id) AS contract_count,
                    SUM(c.valor_global) AS contract_value
                  FROM pncp_supplier_contracts c
                  INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
                  WHERE e.raio_200km IS TRUE
                    AND c.fornecedor_cnpj IS NOT NULL
                    AND c.is_active IS TRUE
                  GROUP BY e.cnpj_8, e.razao_social, c.fornecedor_cnpj, c.fornecedor_nome
                ),
                entity_totals AS (
                  SELECT entity_cnpj8,
                    SUM(contract_count) AS total_contracts,
                    SUM(contract_value) AS total_value
                  FROM entity_supplier_stats
                  GROUP BY entity_cnpj8
                )
                SELECT
                  ess.entity_cnpj8,
                  ess.entity_name,
                  ess.fornecedor_cnpj,
                  ess.fornecedor_nome,
                  ess.contract_count,
                  ess.contract_value,
                  et.total_contracts,
                  et.total_value,
                  ROUND(ess.contract_count::numeric / NULLIF(et.total_contracts, 0) * 100, 2) AS contract_share_pct,
                  ROUND(ess.contract_value::numeric / NULLIF(et.total_value, 0) * 100, 2) AS value_share_pct
                FROM entity_supplier_stats ess
                JOIN entity_totals et ON ess.entity_cnpj8 = et.entity_cnpj8
                ORDER BY ess.entity_cnpj8, ess.contract_count DESC""",
            timeout="60s",
        )
        if rows is None:
            return {"status": "error", "reason": "Award share query failed", "value": None}

        by_entity: dict[str, dict[str, Any]] = {}
        for row in rows:
            eid = str(row.get("entity_cnpj8") or "")
            if eid not in by_entity:
                by_entity[eid] = {
                    "entity_cnpj8": eid,
                    "entity_name": row.get("entity_name"),
                    "total_contracts": int(row.get("total_contracts", 0) or 0),
                    "total_value_brl": round(float(row.get("total_value", 0) or 0), 2),
                    "top_suppliers": [],
                }
            by_entity[eid]["top_suppliers"].append(
                {
                    "fornecedor_cnpj": row.get("fornecedor_cnpj"),
                    "fornecedor_nome": row.get("fornecedor_nome"),
                    "contract_count": int(row.get("contract_count", 0) or 0),
                    "contract_value_brl": round(float(row.get("contract_value", 0) or 0), 2),
                    "contract_share_pct": float(row.get("contract_share_pct", 0) or 0),
                    "value_share_pct": float(row.get("value_share_pct", 0) or 0),
                }
            )

        return {
            "status": "ready",
            "reason": f"Award share computed for {len(by_entity)} entities in the target universe.",
            "value": {
                "by_entity": list(by_entity.values()),
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
            pass
        _logger.error("award_share computation failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": f"Award share computation failed: {exc}", "value": None}


def _classify_hhi(hhi_value: float) -> str:
    """Classify HHI value per U.S. DOJ/FTC Horizontal Merger Guidelines."""
    if hhi_value < 1500:
        return "nao concentrado"
    elif hhi_value <= 2500:
        return "moderadamente concentrado"
    else:
        return "altamente concentrado"


def _compute_hhi(conn, entity_cnpj8_list: list[str]) -> dict[str, Any]:
    """Compute Herfindahl-Hirschman Index per entity and globally.

    HHI = sum of squared market shares (as percentages, 0-100 scale).
    Classification per U.S. DOJ/FTC guidelines:
        <1500  = nao concentrado
        1500-2500 = moderadamente concentrado
        >2500  = altamente concentrado

    Returns:
        dict with global HHI and per-entity HHI breakdown.
    """
    try:
        # ── Global HHI ─────────────────────────────────────────────────
        global_rows = _safe_metric_query(
            conn,
            "hhi_global",
            """WITH supplier_stats AS (
                  SELECT
                    c.fornecedor_cnpj,
                    SUM(c.valor_global) AS total_value
                  FROM pncp_supplier_contracts c
                  INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
                  WHERE e.raio_200km IS TRUE
                    AND c.fornecedor_cnpj IS NOT NULL
                    AND c.is_active IS TRUE
                  GROUP BY c.fornecedor_cnpj
                ),
                grand_total AS (
                  SELECT SUM(total_value) AS gt FROM supplier_stats
                )
                SELECT
                  ROUND(
                    SUM(POWER(s.total_value::numeric / NULLIF(gt.gt, 0) * 100, 2))::numeric,
                    2
                  ) AS hhi
                FROM supplier_stats s, grand_total gt
                WHERE gt.gt > 0""",
            timeout="60s",
        )
        if global_rows is None:
            return {"status": "error", "reason": "Global HHI query failed", "value": None}

        global_hhi = float(global_rows[0].get("hhi", 0) or 0) if global_rows else 0.0

        # ── Per-entity HHI ─────────────────────────────────────────────
        entity_rows = _safe_metric_query(
            conn,
            "hhi_per_entity",
            """WITH entity_supplier_stats AS (
                  SELECT
                    e.cnpj_8 AS entity_cnpj8,
                    e.razao_social AS entity_name,
                    c.fornecedor_cnpj,
                    SUM(c.valor_global) AS contract_value
                  FROM pncp_supplier_contracts c
                  INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
                  WHERE e.raio_200km IS TRUE
                    AND c.fornecedor_cnpj IS NOT NULL
                    AND c.is_active IS TRUE
                  GROUP BY e.cnpj_8, e.razao_social, c.fornecedor_cnpj
                ),
                entity_total AS (
                  SELECT entity_cnpj8, SUM(contract_value) AS et
                  FROM entity_supplier_stats
                  GROUP BY entity_cnpj8
                )
                SELECT
                  ess.entity_cnpj8,
                  ess.entity_name,
                  ROUND(
                    SUM(POWER(ess.contract_value::numeric / NULLIF(et.et, 0) * 100, 2))::numeric,
                    2
                  ) AS hhi
                FROM entity_supplier_stats ess
                JOIN entity_total et ON ess.entity_cnpj8 = et.entity_cnpj8
                WHERE et.et > 0
                GROUP BY ess.entity_cnpj8, ess.entity_name
                ORDER BY hhi DESC""",
            timeout="60s",
        )

        per_entity: list[dict[str, Any]] = []
        if entity_rows:
            for row in entity_rows:
                hhi_val = float(row.get("hhi", 0) or 0)
                per_entity.append(
                    {
                        "entity_cnpj8": row.get("entity_cnpj8"),
                        "entity_name": row.get("entity_name"),
                        "hhi": hhi_val,
                        "classification": _classify_hhi(hhi_val),
                    }
                )

        return {
            "status": "ready",
            "reason": (
                f"HHI global: {global_hhi:.1f} ({_classify_hhi(global_hhi)}). "
                f"HHI por entidade computado para {len(per_entity)} entidades."
            ),
            "value": {
                "global_hhi": round(global_hhi, 2),
                "global_classification": _classify_hhi(global_hhi),
                "by_entity": per_entity,
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
            pass
        _logger.error("HHI computation failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": f"HHI computation failed: {exc}", "value": None}


def _compute_supplier_ranking(
    conn,
    entity_cnpj8_list: list[str],
    top_n: int = 20,
) -> dict[str, Any]:
    """Rank suppliers by contracts, value, and entities served.

    Produces three ranked lists:
        - ``by_contracts``: top suppliers by number of contracts
        - ``by_value``: top suppliers by total contract value
        - ``by_entities_served``: top suppliers by distinct entities served

    Returns:
        dict with three ranked lists of up to ``top_n`` suppliers each.
    """
    try:
        rows = _safe_metric_query(
            conn,
            "supplier_ranking",
            """SELECT
                  c.fornecedor_cnpj,
                  c.fornecedor_nome,
                  COUNT(DISTINCT c.contrato_id) AS total_contracts,
                  SUM(c.valor_global) AS total_value,
                  COUNT(DISTINCT c.orgao_cnpj) AS entities_served
               FROM pncp_supplier_contracts c
               INNER JOIN sc_public_entities e ON e.cnpj_8 = LEFT(c.orgao_cnpj, 8)
               WHERE e.raio_200km IS TRUE
                 AND c.fornecedor_cnpj IS NOT NULL
                 AND c.is_active IS TRUE
               GROUP BY c.fornecedor_cnpj, c.fornecedor_nome""",
            timeout="60s",
        )
        if rows is None:
            return {"status": "error", "reason": "Supplier ranking query failed", "value": None}

        ranked_by_contracts = sorted(
            rows,
            key=lambda r: float(r.get("total_contracts", 0) or 0),
            reverse=True,
        )
        ranked_by_value = sorted(
            rows,
            key=lambda r: float(r.get("total_value", 0) or 0),
            reverse=True,
        )
        ranked_by_entities = sorted(
            rows,
            key=lambda r: float(r.get("entities_served", 0) or 0),
            reverse=True,
        )

        def _build_ranked_list(
            source: list[dict],
            limit: int,
        ) -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for i, row in enumerate(source[:limit], 1):
                result.append(
                    {
                        "rank": i,
                        "fornecedor_cnpj": row.get("fornecedor_cnpj"),
                        "fornecedor_nome": row.get("fornecedor_nome"),
                        "total_contracts": int(row.get("total_contracts", 0) or 0),
                        "total_value_brl": round(float(row.get("total_value", 0) or 0), 2),
                        "entities_served": int(row.get("entities_served", 0) or 0),
                    }
                )
            return result

        return {
            "status": "ready",
            "reason": (f"Supplier ranking computed: top {top_n} por contratos, valor, e entidades atendidas."),
            "value": {
                "by_contracts": _build_ranked_list(ranked_by_contracts, top_n),
                "by_value": _build_ranked_list(ranked_by_value, top_n),
                "by_entities_served": _build_ranked_list(ranked_by_entities, top_n),
            },
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:  # noqa: S110  # Best-effort rollback in error handler
            pass
        _logger.error("supplier_ranking computation failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": f"Supplier ranking computation failed: {exc}", "value": None}


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
    universe: CanonicalUniverse,
    evidence: list[dict],
    source_health: list[dict],
    coverage_rows: list[dict],
    entity_data: dict[str, dict],
    conn,
    threshold: float,
) -> dict[str, Any]:
    """Compute the readiness assessment from all data sources."""

    # ── Build entity ID sets ─────────────────────────────────────────────
    resolved_within = universe.included
    unresolved = universe.unresolved

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

    _commercial_dsn = _os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake")
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
        try:
            market_share = _compute_market_share(_commercial_conn, cnpj8_list)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after market share query failure")
            market_share = {"status": "error", "reason": f"Market share query failed: {exc}", "value": None}
        try:
            award_share = _compute_award_share(_commercial_conn, cnpj8_list)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after award share query failure")
            award_share = {"status": "error", "reason": f"Award share query failed: {exc}", "value": None}
        try:
            hhi = _compute_hhi(_commercial_conn, cnpj8_list)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after HHI query failure")
            hhi = {"status": "error", "reason": f"HHI query failed: {exc}", "value": None}
        try:
            supplier_ranking = _compute_supplier_ranking(_commercial_conn, cnpj8_list)
        except Exception as exc:
            try:
                _commercial_conn.rollback()
            except Exception:
                _logger.exception("Failed to rollback commercial connection after supplier ranking query failure")
            supplier_ranking = {"status": "error", "reason": f"Supplier ranking query failed: {exc}", "value": None}
        _commercial_conn.close()
    except Exception as exc:
        contract_value_agg = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}
        desagio_stats = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}
        relicitacao_stats = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}
        market_share = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}  # noqa: F841
        award_share = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}  # noqa: F841
        hhi = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}  # noqa: F841
        supplier_ranking = {"status": "error", "reason": f"Commercial connection failed: {exc}", "value": None}  # noqa: F841

    win_rate_metric = {
        "status": "not_ready",
        "reason": (
            "Win rate real exige proposal_tracking (propostas enviadas vs vencidas "
            "por CNPJ). PNCP não expõe propostas perdedoras."
        ),
        "alternative_metrics_available": ["market_share", "award_share", "hhi", "supplier_ranking"],
    }

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
        "relicitacao_probability": {
            "status": relicitacao_stats["status"],
            "reason": relicitacao_stats["reason"],
            "value": relicitacao_stats["value"],
        },
        "win_rate": win_rate_metric,
        "competitive_intelligence": {
            "win_rate": win_rate_metric,
            "market_share": {
                "status": market_share["status"],
                "reason": market_share["reason"],
                "value": market_share["value"],
            },
            "award_share": {
                "status": award_share["status"],
                "reason": award_share["reason"],
                "value": award_share["value"],
            },
            "hhi": {
                "status": hhi["status"],
                "reason": hhi["reason"],
                "value": hhi["value"],
            },
            "supplier_ranking": {
                "status": supplier_ranking["status"],
                "reason": supplier_ranking["reason"],
                "value": supplier_ranking["value"],
            },
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
        "universe": _make_summary(universe),
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
        if name == "competitive_intelligence":
            continue
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
    # ── Competitive Intelligence section ─────────────────────────────────
    ci = metrics.get("commercial_metrics", {}).get("competitive_intelligence", {})
    if ci:
        print()
        print("  COMPETITIVE INTELLIGENCE (Regra #9):")
        wr = ci.get("win_rate", {})
        print(f"    win_rate: [{wr.get('status', 'unknown')}]")
        print(f"      → {wr.get('reason', '')[:120]}")
        print(f"      alternative_metrics: {wr.get('alternative_metrics_available', [])}")

        ms = ci.get("market_share", {})
        print(f"    market_share: [{ms.get('status', 'unknown')}]")
        ms_val = ms.get("value")
        if ms_val:
            print(f"      Fornecedores:          {ms_val.get('total_suppliers', 'N/A')}")
            print(f"      Total contratos:       {ms_val.get('total_contracts_in_universe', 'N/A')}")
            print(f"      Valor total (R$):      {ms_val.get('total_value_in_universe_brl', 'N/A'):>15,.2f}")
            top3 = ms_val.get("top_suppliers", [])[:3]
            for s in top3:
                print(
                    f"      Top: {s.get('fornecedor_nome', 'N/A'):<40s}  "
                    f"contratos={s.get('total_contracts', 0)}  "
                    f"share={s.get('contract_share_pct', 0):.1f}%"
                )

        aw = ci.get("award_share", {})
        print(f"    award_share: [{aw.get('status', 'unknown')}]")
        aw_val = aw.get("value")
        if aw_val:
            by_entity = aw_val.get("by_entity", [])
            print(f"      Entidades analisadas: {len(by_entity)}")

        h = ci.get("hhi", {})
        print(f"    hhi: [{h.get('status', 'unknown')}]")
        h_val = h.get("value")
        if h_val:
            print(f"      HHI global:            {h_val.get('global_hhi', 'N/A'):>10.1f}")
            print(f"      Classificacao global:  {h_val.get('global_classification', 'N/A')}")
            print(f"      Entidades com HHI:     {len(h_val.get('by_entity', []))}")

        sr = ci.get("supplier_ranking", {})
        print(f"    supplier_ranking: [{sr.get('status', 'unknown')}]")
        sr_val = sr.get("value")
        if sr_val:
            by_val = sr_val.get("by_value", [])
            if by_val:
                print("      Top 3 por valor:")
                for s in by_val[:3]:
                    print(
                        f"        #{s.get('rank')}: {s.get('fornecedor_nome', 'N/A'):<40s}  "
                        f"R$ {s.get('total_value_brl', 0):>12,.2f}"
                    )
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
        universe = load_canonical_universe(args.seed or DEFAULT_SEED, args.radius_km)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(
        f"   Universe: {len(universe.included) + len(universe.excluded)} resolved, "
        f"{len(universe.unresolved)} unresolved, "
        f"{len(universe.included)} within radius"
    )

    if len(universe.included) == 0 and len(universe.unresolved) == 0 and len(universe.excluded) == 0:
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
