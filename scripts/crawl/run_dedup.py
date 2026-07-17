#!/usr/bin/env python3
"""CLI to wire DedupEngine into the operational pipeline (C2.8 / NEXT-30D).

Runs cross-source deduplication on active opportunity_intel rows and persists
groups into dedup_cross_source. Produces a before/after JSON report.

Usage:
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --dry-run
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --dsn postgresql://...
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --output output/dedup/run.json
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --seed-synthetic
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Prefix for synthetic proof rows (NOT production coverage).
SYNTH_SOURCE_ID_PREFIX = "SYNTH-DEDUP-NEXT30D-"
SYNTH_CONTENT_HASH_PREFIX = "synth-dedup-next30d-"


def _resolve_dsn(explicit: str | None) -> str:
    if explicit:
        return explicit
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if dsn:
        return dsn
    try:
        from config.settings import LOCAL_DATALAKE_DSN

        return LOCAL_DATALAKE_DSN
    except ImportError:
        return "postgresql://test:test@127.0.0.1:5433/pncp_datalake"


def _count_dedup(conn: Any) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM dedup_cross_source")
    total = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(DISTINCT dedup_group_id) FROM dedup_cross_source
        """
    )
    groups = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(*) FROM opportunity_intel WHERE is_active IS TRUE
        """
    )
    active_ops = cur.fetchone()[0]
    cur.execute(
        """
        SELECT source, count(*) FROM opportunity_intel
        WHERE is_active IS TRUE
        GROUP BY source ORDER BY 2 DESC
        """
    )
    by_source = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return {
        "dedup_rows": total,
        "dedup_groups": groups,
        "active_opportunities": active_ops,
        "opportunities_by_source": by_source,
    }


def seed_synthetic_fixtures(conn: Any) -> list[dict[str, Any]]:
    """Insert controlled multi-source rows that share a canonical hash.

    These rows are **synthetic proof only** — they do not represent production
    crawl coverage. Identifiers use SYNTH-DEDUP-NEXT30D- / synth-dedup-next30d-
    prefixes for easy cleanup and honest documentation.
    """
    cur = conn.cursor()
    # Cleanup prior synthetic proof rows + their dedup links
    cur.execute(
        """
        DELETE FROM dedup_cross_source
        WHERE opportunity_id IN (
            SELECT id FROM opportunity_intel
            WHERE source_id LIKE %s OR content_hash LIKE %s
        )
        """,
        (f"{SYNTH_SOURCE_ID_PREFIX}%", f"{SYNTH_CONTENT_HASH_PREFIX}%"),
    )
    cur.execute(
        """
        DELETE FROM opportunity_intel
        WHERE source_id LIKE %s OR content_hash LIKE %s
        """,
        (f"{SYNTH_SOURCE_ID_PREFIX}%", f"{SYNTH_CONTENT_HASH_PREFIX}%"),
    )

    canon = {
        "orgao_cnpj": "82892324",
        "orgao_nome": "PREFEITURA MUNICIPAL DE SANTO AMARO DA IMPERATRIZ",
        "objeto_base": ("Aquisição de material de escritório para unidades administrativas — SYNTH DEDUP NEXT30D"),
        "data_publicacao": "2026-07-01T12:00:00+00",
        "valor_estimado": 150000.00,
        "uf": "SC",
        "municipio": "SANTO AMARO DA IMPERATRIZ",
        "status_canonico": "open",
        "ranking": "REVIEW",
        "ranking_confianca": "LOW",
        "is_active": True,
        "crawl_batch_id": "synth-dedup-next30d",
    }
    meta = json.dumps(
        {
            "synthetic": True,
            "purpose": "NEXT-30D C2.8 dedup cross-source proof",
            "not_production": True,
            "agent": "A6-dedup",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    # Two sources; second uses accent/case variance to prove normalization.
    rows_spec = [
        {
            "source": "pncp",
            "source_id": f"{SYNTH_SOURCE_ID_PREFIX}PNCP-001",
            "content_hash": f"{SYNTH_CONTENT_HASH_PREFIX}pncp-001",
            "source_url": "https://example.local/synth/pncp/001",
            "numero_controle_pncp": "SYNTH-PNCP-001",
            "modalidade": "Pregão Eletrônico",
            "objeto": canon["objeto_base"],
        },
        {
            "source": "transparencia_sc",
            "source_id": f"{SYNTH_SOURCE_ID_PREFIX}TRANS-001",
            "content_hash": f"{SYNTH_CONTENT_HASH_PREFIX}trans-001",
            "source_url": "https://example.local/synth/transparencia/001",
            "numero_controle_pncp": None,
            "modalidade": "pregao eletronico",
            "objeto": ("Aquisicao de material de escritorio para unidades administrativas — SYNTH DEDUP NEXT30D"),
        },
    ]

    insert_sql = """
        INSERT INTO opportunity_intel (
            source, source_id, source_url, content_hash, numero_controle_pncp,
            crawl_batch_id, orgao_cnpj, orgao_nome, modalidade, objeto,
            data_publicacao, valor_estimado, uf, municipio, status_canonico,
            ranking, ranking_confianca, is_active, metadata
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb
        )
        RETURNING id, source, source_id
    """
    inserted: list[dict[str, Any]] = []
    for spec in rows_spec:
        cur.execute(
            insert_sql,
            (
                spec["source"],
                spec["source_id"],
                spec["source_url"],
                spec["content_hash"],
                spec["numero_controle_pncp"],
                canon["crawl_batch_id"],
                canon["orgao_cnpj"],
                canon["orgao_nome"],
                spec["modalidade"],
                spec["objeto"],
                canon["data_publicacao"],
                canon["valor_estimado"],
                canon["uf"],
                canon["municipio"],
                canon["status_canonico"],
                canon["ranking"],
                canon["ranking_confianca"],
                canon["is_active"],
                meta,
            ),
        )
        row = cur.fetchone()
        inserted.append({"id": row[0], "source": row[1], "source_id": row[2]})

    conn.commit()
    cur.close()
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cross-source DedupEngine")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute groups without writing dedup_cross_source",
    )
    parser.add_argument(
        "--seed-synthetic",
        action="store_true",
        help=(
            "Insert synthetic multi-source fixtures (SYNTH-DEDUP-NEXT30D-*) "
            "before running — proof only, not production coverage"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON report path (default: output/dedup/dedup-<ts>.json)",
    )
    args = parser.parse_args()

    dsn = _resolve_dsn(args.dsn)
    import psycopg2

    from scripts.lib.dedup import DedupEngine

    run_id = f"dedup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": bool(args.dry_run),
        "seed_synthetic": bool(args.seed_synthetic),
        "dsn_host": dsn.split("@")[-1] if "@" in dsn else "local",
    }

    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        before = _count_dedup(conn)
        report["before"] = before

        if args.seed_synthetic:
            seeded = seed_synthetic_fixtures(conn)
            report["synthetic_fixtures"] = {
                "note": "SYNTHETIC PROOF ONLY — not production coverage",
                "rows": seeded,
            }
            report["after_seed"] = _count_dedup(conn)

        engine = DedupEngine(conn)
        stats = engine.dedup_opportunities(dry_run=bool(args.dry_run))
        report["engine_stats"] = stats
        if not args.dry_run:
            after = _count_dedup(conn)
        else:
            after = _count_dedup(conn) if args.seed_synthetic else before
            if args.dry_run and args.seed_synthetic:
                # dry-run does not write dedup rows; counts reflect seed only
                pass
        report["after"] = after
        report["delta_dedup_rows"] = after["dedup_rows"] - before["dedup_rows"]
        report["delta_dedup_groups"] = after["dedup_groups"] - before["dedup_groups"]

        # Honest classification
        if before["active_opportunities"] == 0 and not args.seed_synthetic:
            report["outcome"] = "success_zero"
            report["note"] = "No active opportunities; nothing to dedup"
            exit_code = 0
        elif stats.get("groups_found", 0) == 0:
            sources = (
                (report.get("after_seed") or after).get("opportunities_by_source")
                or before.get("opportunities_by_source")
                or {}
            )
            multi = len(sources) >= 2
            if multi:
                report["outcome"] = "success_zero"
                report["note"] = (
                    "Multi-source data present but no cross-source hash groups; "
                    "not a failure — may indicate no true duplicates"
                )
                exit_code = 0
            else:
                report["outcome"] = "partial"
                report["note"] = "Only single-source opportunities; cannot prove cross-source dedup"
                exit_code = 0
        else:
            report["outcome"] = "success"
            report["note"] = "Cross-source groups written or detected"
            if args.seed_synthetic:
                report["note"] += " (includes synthetic fixtures — not production)"
            exit_code = 0

        out = Path(args.output) if args.output else _PROJECT_ROOT / "output" / "dedup" / f"{run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        report["report_path"] = str(out)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return exit_code
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
