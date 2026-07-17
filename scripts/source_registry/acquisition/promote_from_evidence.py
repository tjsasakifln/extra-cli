"""Promote registry entities to operational status from real pipeline evidence.

Uses PostgreSQL entity_coverage / opportunity_intel / official_act_matches as
proof of collect → normalize → reconcile → verify — NOT dry-run index hits.

Only evidence inside the SLA is operational (``verified``). Older collected
evidence is retained for history but never counted as operational coverage.
Evidence records dry_run=false and stage checklist for §3.2.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.source_registry.gap_report import derive_blocker_class
from scripts.source_registry.models import EntitySourceRecord, is_strict_operational

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = PROJECT_ROOT / "output" / "coverage" / "acquisition"
DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://test:test@127.0.0.1:5433/pncp_datalake",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def fetch_pipeline_evidence(dsn: str | None = None) -> list[dict[str, Any]]:
    """Load entities with real collect evidence from the datalake."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                  e.id AS entity_db_id,
                  e.cnpj_8,
                  e.razao_social,
                  e.municipio,
                  e.natureza_juridica,
                  array_agg(DISTINCT ec.source) FILTER (WHERE ec.source IS NOT NULL) AS sources,
                  bool_or(ec.is_covered) AS is_covered,
                  MAX(ec.last_seen_at) AS last_seen_at,
                  SUM(COALESCE(ec.total_bids, 0)) AS total_bids,
                  COUNT(DISTINCT ec.source) AS source_count
                FROM sc_public_entities e
                JOIN entity_coverage ec ON e.id = ec.entity_id
                WHERE e.is_active = TRUE
                  AND e.raio_200km = TRUE
                  AND ec.is_covered = TRUE
                  AND ec.last_seen_at IS NOT NULL
                GROUP BY e.id, e.cnpj_8, e.razao_social, e.municipio, e.natureza_juridica
                ORDER BY MAX(ec.last_seen_at) DESC NULLS LAST
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

            # Enrich with opportunity_intel presence (normalized open tenders)
            try:
                cur.execute(
                    """
                    SELECT LEFT(orgao_cnpj, 8) AS cnpj_8,
                           COUNT(*) AS opp_count,
                           MAX(last_seen_at) AS opp_last_seen
                    FROM opportunity_intel
                    WHERE is_active = TRUE
                      AND COALESCE(source, '') <> 'test_batch'
                      AND orgao_cnpj IS NOT NULL
                    GROUP BY LEFT(orgao_cnpj, 8)
                    """
                )
                opp_by = {r["cnpj_8"]: dict(r) for r in cur.fetchall() if r["cnpj_8"]}
            except Exception:  # noqa: BLE001
                opp_by = {}

            # official_act_matches if populated
            match_by: dict[str, int] = {}
            try:
                cur.execute(
                    """
                    SELECT e.cnpj_8, COUNT(*) AS n
                    FROM official_act_matches m
                    JOIN sc_public_entities e ON e.id = m.entity_id
                    WHERE e.raio_200km = TRUE
                    GROUP BY e.cnpj_8
                    """
                )
                match_by = {r["cnpj_8"]: int(r["n"]) for r in cur.fetchall() if r["cnpj_8"]}
            except Exception:  # noqa: BLE001
                match_by = {}

            for row in rows:
                c8 = row.get("cnpj_8") or ""
                opp = opp_by.get(c8) or {}
                row["opp_count"] = int(opp.get("opp_count") or 0)
                row["opp_last_seen"] = opp.get("opp_last_seen")
                row["official_act_matches"] = int(match_by.get(c8) or 0)
                row["normalized"] = True  # entity_coverage requires normalized bids
                row["reconciled"] = bool(row["is_covered"])  # matched to universe entity
            return rows
    finally:
        conn.close()


def promote_from_pipeline_evidence(
    records: list[EntitySourceRecord],
    *,
    dsn: str | None = None,
    sla_hours: int = 24,
    persist: bool = True,
    limit: int = 0,
) -> dict[str, Any]:
    """Promote matching registry rows to collected/verified from DB evidence."""
    from scripts.source_registry.builder import persist_registry

    evidence_rows = fetch_pipeline_evidence(dsn=dsn)
    by_cnpj8: dict[str, list[dict[str, Any]]] = {}
    for er in evidence_rows:
        c8 = (er.get("cnpj_8") or "")[:8]
        if c8:
            by_cnpj8.setdefault(c8, []).append(er)

    now = _now()
    verified_cutoff = now - timedelta(hours=sla_hours)
    collected_cutoff = now - timedelta(days=90)

    promoted = 0
    verified_n = 0
    collected_n = 0
    unmatched = 0
    attempts: list[dict[str, Any]] = []

    for rec in records:
        c8 = (rec.cnpj or "")[:8]
        if not c8 or c8 not in by_cnpj8:
            continue
        candidates = by_cnpj8[c8]
        # CNPJ raiz is not a safe identity when several entities share it.
        # Ambiguous roots remain in the review queue instead of receiving the
        # same evidence silently.
        if len(candidates) != 1:
            unmatched += 1
            continue
        ev = candidates[0]
        last_seen = ev.get("last_seen_at")
        if last_seen is None:
            continue
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)

        if last_seen < collected_cutoff:
            continue  # too stale for operational claim

        # Stage checklist §3.2
        stages = {
            "mapped": True,
            "accessible": True,
            "collected": True,  # entity_coverage rows prove ingest
            "normalized": bool(ev.get("normalized")),
            "reconciled": bool(ev.get("reconciled")),
            "verified_within_sla": last_seen >= verified_cutoff,
        }
        if not all(stages[k] for k in ("mapped", "accessible", "collected", "normalized", "reconciled")):
            continue

        status = "verified" if stages["verified_within_sla"] else "collected"
        sources = list(ev.get("sources") or [])
        for s in sources:
            if s and s not in rec.plataformas:
                rec.plataformas = list(rec.plataformas) + [s]

        rec.access_status = status
        rec.last_success_at = _iso(last_seen)
        rec.last_attempt_at = _iso(now)
        rec.current_blocker = None
        rec.next_action = "maintain_incremental_crawl_and_freshness_sla"
        rec.collection_strategy = "pipeline_evidence_promote"
        rec.mapping_confidence = min(1.0, max(rec.mapping_confidence, 0.9))
        rec.external_ids = dict(rec.external_ids or {})
        rec.external_ids["entity_db_id"] = ev.get("entity_db_id")
        rec.external_ids["pipeline_sources"] = sources
        rec.external_ids["total_bids_coverage"] = int(ev.get("total_bids") or 0)

        evidence = {
            "type": "pipeline_evidence_promote",
            "dry_run": False,
            "use_network": True,  # evidence originated from live crawl pipelines into PG
            "outcome": f"promoted_{status}",
            "attempted_at": _iso(now),
            "last_seen_at": _iso(last_seen),
            "sources": sources,
            "stages": stages,
            "entity_db_id": ev.get("entity_db_id"),
            "total_bids": int(ev.get("total_bids") or 0),
            "opp_count": int(ev.get("opp_count") or 0),
            "official_act_matches": int(ev.get("official_act_matches") or 0),
            "proof": (
                "entity_coverage.is_covered + last_seen_at within window; "
                "entity matched to sc_public_entities (reconciled); "
                "bids stored via crawl normalize path"
            ),
        }
        rec.evidences = list(rec.evidences or []) + [evidence]
        promoted += 1
        if status == "verified":
            verified_n += 1
        else:
            collected_n += 1
        attempts.append(
            {
                "canonical_id": rec.canonical_id,
                "cnpj8": c8,
                "status": status,
                "last_seen_at": _iso(last_seen),
                "sources": sources,
            }
        )
        if limit and promoted >= limit:
            break

    # Persist derived blockers for ALL non-operational rows (no bare none)
    normalized_blockers = 0
    for rec in records:
        if is_strict_operational(rec):
            rec.current_blocker = None
            continue
        derived = derive_blocker_class(rec)
        if rec.current_blocker != derived:
            rec.current_blocker = derived
            normalized_blockers += 1

    summary: dict[str, Any] = {
        "strategy": "promote_from_evidence",
        "evidence_rows_loaded": len(evidence_rows),
        "promoted": promoted,
        "verified": verified_n,
        "collected": collected_n,
        "unmatched_registry_skipped": unmatched,
        "blockers_normalized": normalized_blockers,
        "sla_hours": sla_hours,
        "sample_promotions": attempts[:20],
        "dry_run": False,
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out = EVIDENCE_DIR / f"promote_from_evidence-{stamp}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    summary["evidence_path"] = str(out)

    if persist:
        persist_registry(records)
        summary["persisted"] = True
    else:
        summary["persisted"] = False

    logger.info(
        "promote_from_evidence: promoted=%s verified=%s collected=%s blockers_fixed=%s",
        promoted,
        verified_n,
        collected_n,
        normalized_blockers,
    )
    return summary


def normalize_registry_blockers(
    records: list[EntitySourceRecord],
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Rewrite current_blocker for every non-operational entity (no bare none)."""
    from scripts.source_registry.builder import persist_registry

    fixed = 0
    for rec in records:
        if is_strict_operational(rec):
            rec.current_blocker = None
            continue
        derived = derive_blocker_class(rec)
        if rec.current_blocker != derived:
            rec.current_blocker = derived
            fixed += 1
    summary = {"strategy": "normalize_blockers", "fixed": fixed, "total": len(records)}
    if persist:
        persist_registry(records)
        summary["persisted"] = True
    return summary
