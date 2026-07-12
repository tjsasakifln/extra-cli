"""Coverage manifest generation for Opportunity Intelligence.

Generates:
    output/readiness/opportunity-coverage-manifest.json
    output/readiness/opportunity-coverage-gaps.csv
    output/readiness/opportunity-source-health.csv

Exit codes:
    0 — PASS  (coverage ≥ threshold)
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
        coverage_pct = manifest.get("coverage", {}).get("pct_entities_with_data", 0)
        exit_code = 0 if coverage_pct >= threshold else 2

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
    """Build coverage manifest JSON."""
    now = datetime.now(UTC).isoformat()

    # Target universe: entities within 200km
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*) AS cnt FROM sc_public_entities WHERE raio_200km = TRUE")
    total_entities = cur.fetchone()["cnt"]

    # Entities with any opportunity data
    cur.execute("""
        SELECT COUNT(DISTINCT orgao_cnpj) AS cnt
        FROM opportunity_intel
        WHERE is_active = TRUE
          AND orgao_cnpj IS NOT NULL
    """)
    entities_with_data = cur.fetchone()["cnt"]

    # Total opportunities by status
    cur.execute("""
        SELECT status_canonico, COUNT(*) AS cnt
        FROM opportunity_intel
        WHERE is_active = TRUE
        GROUP BY status_canonico
        ORDER BY cnt DESC
    """)
    by_status = {row["status_canonico"]: row["cnt"] for row in cur.fetchall()}

    # Open opportunities
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM opportunity_intel
        WHERE status_canonico IN ('open', 'upcoming')
          AND is_active = TRUE
    """)
    open_count = cur.fetchone()["cnt"]

    # By source
    cur.execute("""
        SELECT source, COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE status_canonico IN ('open', 'upcoming')) AS open_cnt
        FROM opportunity_intel
        WHERE is_active = TRUE
        GROUP BY source
        ORDER BY cnt DESC
    """)
    by_source = {row["source"]: {"total": row["cnt"], "open": row["open_cnt"]} for row in cur.fetchall()}

    # Freshness
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '24 hours') AS fresh_24h,
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '7 days') AS fresh_7d,
            COUNT(*) FILTER (WHERE ingested_at >= NOW() - INTERVAL '30 days') AS fresh_30d
        FROM opportunity_intel
        WHERE is_active = TRUE
    """)
    freshness = cur.fetchone()

    pct_covered = round(entities_with_data / total_entities * 100, 2) if total_entities > 0 else 0.0

    return {
        "meta": {
            "generated_at": now,
            "tool": "opportunity_intel.manifest",
            "threshold": THRESHOLD,
            "radius_km": 200,
            "reference_city": "Florianópolis",
        },
        "universe": {
            "total_entities_within_200km": total_entities,
            "entities_with_opportunity_data": entities_with_data,
            "entities_without_data": total_entities - entities_with_data,
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
            "passes_threshold": pct_covered >= THRESHOLD,
            "exit_code": 0 if pct_covered >= THRESHOLD else 2,
            "gap_to_threshold": round(max(0, THRESHOLD - pct_covered / 100), 2),
        },
    }


def _build_gaps(conn) -> list[dict[str, Any]]:
    """Build coverage gaps CSV data."""
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
        LEFT JOIN opportunity_intel oi ON spe.cnpj_8 = oi.orgao_cnpj AND oi.is_active = TRUE
        WHERE spe.raio_200km = TRUE
        GROUP BY spe.id, spe.razao_social, spe.cnpj_8, spe.municipio,
                 spe.codigo_ibge, spe.distancia_fk, spe.raio_200km,
                 CASE WHEN oi.orgao_cnpj IS NOT NULL THEN TRUE ELSE FALSE END
        ORDER BY has_opportunity_data ASC, spe.distancia_fk ASC NULLS LAST
    """)

    return list(cur.fetchall())


def _build_source_health(conn) -> list[dict[str, Any]]:
    """Build source health CSV data."""
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
