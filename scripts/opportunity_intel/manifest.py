"""Coverage manifest generation for Opportunity Intelligence.

Generates:
    output/readiness/opportunity-coverage-manifest.json
    output/readiness/opportunity-coverage-gaps.csv
    output/readiness/opportunity-source-health.csv

Exit codes:
    0 — PASS  (coverage >= threshold)
    2 — below threshold (PARTIAL)
    1 — technical failure
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

import psycopg2
import psycopg2.extras

_logger = logging.getLogger(__name__)

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "output",
    "readiness",
)
THRESHOLD = float(os.getenv("OI_COVERAGE_THRESHOLD", "0.95"))

# Canonical universe: entities within 200 km of Florianópolis.
# Source: seed spreadsheet column "Raio 200km?" = SIM + Haversine <= 200 km.
# The DB flag raio_200km is inconsistent (1448 rows, includes 355 extra).
# Audited in docs/coverage-truth/fase0-audit-2026-07-12.md.
# This constant MUST match the canonical spreadsheet count.
CANONICAL_UNIVERSE_WITHIN_200KM = 1093


def generate(dsn: str | None = None, threshold: float = THRESHOLD) -> dict[str, Any]:
    """Generate all coverage manifest files.

    Returns:
        Dict with exit_code, metrics, files.
    """
    dsn = dsn or DEFAULT_DSN
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = psycopg2.connect(dsn)
    conn.autocommit = True

    try:
        manifest = _build_manifest(conn)
        gaps = _build_gaps(conn)
        source_health = _build_source_health(conn)

        # Write files
        _write_json(os.path.join(OUTPUT_DIR, "opportunity-coverage-manifest.json"), manifest)
        _write_csv(os.path.join(OUTPUT_DIR, "opportunity-coverage-gaps.csv"), gaps)
        _write_csv(os.path.join(OUTPUT_DIR, "opportunity-source-health.csv"), source_health)

        # Determine exit code
        coverage_pct = float(manifest.get("universe", {}).get("pct_entities_with_data", 0))
        exit_code = 0 if coverage_pct >= threshold * 100 else 2

        return {
            "exit_code": exit_code,
            "manifest": manifest,
            "files": [
                "output/readiness/opportunity-coverage-manifest.json",
                "output/readiness/opportunity-coverage-gaps.csv",
                "output/readiness/opportunity-source-health.csv",
            ],
        }
    finally:
        conn.close()


def _build_manifest(conn) -> dict[str, Any]:
    """Build coverage manifest JSON.

    Returns:
        Coverage manifest dict with universe, opportunities, freshness.

    Raises:
        AssertionError: If coverage math is invalid (negative, >100%, etc).
    """
    now = datetime.now(UTC).isoformat()

    # Target universe: canonical 1093 entities within 200 km.
    # The DB flag raio_200km is inconsistent (1448 vs canonical 1093),
    # so we use the audited canonical constant.
    total_entities = CANONICAL_UNIVERSE_WITHIN_200KM

    # Entities with any opportunity data, filtered to within 200 km radius
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT COUNT(DISTINCT oi.orgao_cnpj) AS cnt
        FROM opportunity_intel oi
        INNER JOIN sc_public_entities spe
            ON spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8)
        WHERE oi.is_active = TRUE
          AND oi.orgao_cnpj IS NOT NULL
          AND oi.source != 'test_batch'
          AND spe.raio_200km = TRUE
    """)
    entities_with_data = cur.fetchone()["cnt"]

    # Total opportunities by status (exclude test_batch)
    cur.execute("""
        SELECT status_canonico, COUNT(*) AS cnt
        FROM opportunity_intel
        WHERE is_active = TRUE
          AND source != 'test_batch'
        GROUP BY status_canonico
        ORDER BY cnt DESC
    """)
    by_status = {row["status_canonico"]: row["cnt"] for row in cur.fetchall()}

    # Open opportunities (exclude test_batch)
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM opportunity_intel
        WHERE status_canonico IN ('open', 'upcoming')
          AND is_active = TRUE
          AND source != 'test_batch'
    """)
    open_count = cur.fetchone()["cnt"]

    # By source (exclude test_batch)
    cur.execute("""
        SELECT source, COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE status_canonico IN ('open', 'upcoming')) AS open_cnt
        FROM opportunity_intel
        WHERE is_active = TRUE
          AND source != 'test_batch'
        GROUP BY source
        ORDER BY cnt DESC
    """)
    by_source = {row["source"]: {"total": row["cnt"], "open": row["open_cnt"]} for row in cur.fetchall()}

    # Freshness (exclude test_batch)
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '24 hours') AS fresh_24h,
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '7 days') AS fresh_7d,
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '30 days') AS fresh_30d
        FROM opportunity_intel
        WHERE is_active = TRUE
          AND source != 'test_batch'
    """)
    freshness = cur.fetchone()

    # ------------------------------------------------------------------
    # Validation asserts before computing percentage
    # ------------------------------------------------------------------
    assert entities_with_data >= 0, f"entities_with_data negativo: {entities_with_data}"
    assert total_entities > 0, f"total_entities é zero (canonical universe = {CANONICAL_UNIVERSE_WITHIN_200KM})"
    assert entities_with_data <= total_entities, (
        f"entities_with_data ({entities_with_data}) > total_entities ({total_entities})"
    )

    pct_covered = round(entities_with_data / total_entities * 100, 2) if total_entities > 0 else 0.0
    entities_without_data = total_entities - entities_with_data

    # Sanity checks on output
    assert 0 <= pct_covered <= 100, f"pct_covered inválido: {pct_covered}"
    assert entities_without_data >= 0, f"entities_without_data negativo: {entities_without_data}"

    return {
        "meta": {
            "generated_at": now,
            "tool": "opportunity_intel.manifest",
            "threshold": THRESHOLD,
            "radius_km": 200,
            "reference_city": "Florianópolis",
            "canonical_universe_source": (
                "seed spreadsheet 'Extra - alvos de licitação. R-0.xlsx' "
                "column 'Raio 200km?' = SIM + Haversine <= 200 km"
            ),
        },
        "universe": {
            "total_entities_within_200km": total_entities,
            "total_entities_db_flag": None,  # DB flag is inconsistent (1448 vs 1093)
            "entities_with_opportunity_data": entities_with_data,
            "entities_without_data": entities_without_data,
            "pct_entities_with_data": pct_covered,
        },
        "opportunities": {
            "total": sum(by_status.values()),
            "open": open_count,
            "by_status": by_status,
            "by_source": by_source,
        },
        "freshness": {
            "last_24h": freshness["fresh_24h"] if freshness else 0,
            "last_7d": freshness["fresh_7d"] if freshness else 0,
            "last_30d": freshness["fresh_30d"] if freshness else 0,
        },
        "readiness": {
            "passes_threshold": pct_covered >= THRESHOLD * 100,
            "exit_code": 0 if pct_covered >= THRESHOLD * 100 else 2,
            "gap_to_threshold": round(max(0, THRESHOLD * 100 - pct_covered), 2),
        },
    }


def _build_gaps(conn) -> list[dict[str, Any]]:
    """Build coverage gaps CSV data.

    Lists entities within 200 km radius, flagging whether they have
    opportunity data. Excludes test_batch records.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            spe.id,
            spe.razao_social,
            spe.cnpj_8,
            spe.municipio,
            spe.codigo_ibge,
            spe.distancia_fk,
            spe.raio_200km,
            CASE WHEN oi.orgao_cnpj IS NOT NULL THEN TRUE ELSE FALSE END AS has_opportunity_data
        FROM sc_public_entities spe
        LEFT JOIN opportunity_intel oi
            ON spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8)
            AND oi.is_active = TRUE
            AND oi.source != 'test_batch'
        WHERE spe.raio_200km = TRUE
        GROUP BY spe.id, spe.razao_social, spe.cnpj_8, spe.municipio,
                 spe.codigo_ibge, spe.distancia_fk, spe.raio_200km,
                 CASE WHEN oi.orgao_cnpj IS NOT NULL THEN TRUE ELSE FALSE END
        ORDER BY has_opportunity_data ASC, spe.distancia_fk ASC NULLS LAST
    """)

    return list(cur.fetchall())


def _build_source_health(conn) -> list[dict[str, Any]]:
    """Build source health CSV data.

    Excludes test_batch from production metrics.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            source,
            COUNT(*) AS total_records,
            COUNT(*) FILTER (WHERE status_canonico = 'open') AS open_count,
            COUNT(*) FILTER (WHERE status_canonico = 'upcoming') AS upcoming_count,
            COUNT(*) FILTER (WHERE status_canonico = 'closed') AS closed_count,
            COUNT(*) FILTER (WHERE status_canonico = 'unknown') AS unknown_count,
            COUNT(*) FILTER (WHERE ranking = 'GO') AS go_count,
            COUNT(*) FILTER (WHERE ranking = 'REVIEW') AS review_count,
            COUNT(*) FILTER (WHERE ranking = 'NO_GO') AS no_go_count,
            MIN(data_abertura) AS earliest_abertura,
            MAX(data_encerramento) AS latest_encerramento,
            MIN(ingested_at) AS first_seen,
            MAX(ingested_at) AS last_seen,
            CASE
                WHEN MAX(ingested_at) >= NOW() - INTERVAL '1 day' THEN 'fresh'
                WHEN MAX(ingested_at) >= NOW() - INTERVAL '7 days' THEN 'stale'
                WHEN MAX(ingested_at) IS NOT NULL THEN 'old'
                ELSE 'never'
            END AS freshness
        FROM opportunity_intel
        WHERE is_active = TRUE
          AND source != 'test_batch'
        GROUP BY source
        ORDER BY total_records DESC
    """)

    return list(cur.fetchall())


def _write_json(path: str, data: Any):
    with open(path, "w") as f:
        json.dump(data, f, default=str, indent=2, ensure_ascii=False)
    _logger.info("Wrote %s", path)


def _write_csv(path: str, rows: list[dict[str, Any]]):
    if not rows:
        _logger.warning("No data for %s", path)
        with open(path, "w", newline="") as f:
            f.write("")
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _logger.info("Wrote %s (%d rows)", path, len(rows))


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        result = generate()
        print(f"Exit code: {result['exit_code']}")
        print(f"Coverage: {result['manifest']['universe']['pct_entities_with_data']}%")
        print(f"Threshold: {THRESHOLD * 100}%")
        print(f"Files: {', '.join(result['files'])}")
        sys.exit(result["exit_code"])
    except Exception as e:
        _logger.error("Manifest generation failed: %s", e, exc_info=True)
        print(f"FALHA TÉCNICA: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
