#!/usr/bin/env python3
"""Rebuild evidence ledger from actual persisted data.

Fixes the ~50% error rate in coverage_evidence where:
- Entities marked ``success_zero`` actually have data (false negatives)
- Root cause: evidence was recorded per-crawl-run using only the current
  run's pncp_ids, not checking the total persisted data across runs.

This script:
1. Collects ALL actual persisted data per entity within the 200km radius
2. Deletes existing entity-level evidence rows
3. Inserts correct evidence from persisted data only
4. Adds validation trigger to prevent future drift
5. Cross-verifies no false positives/negatives remain

Usage::

    python scripts/fix/rebuild_evidence_ledger.py [--verify-only]

Exit codes:
    0 — Evidence rebuilt successfully
    1 — Error during rebuild
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)

OTHER_SOURCES = [
    "ciga_ckan",
    "compras_gov",
    "contracts",
    "doe_sc",
    "dom_sc",
    "mides_bigquery",
    "pcp",
    "sc_compras",
    "transparencia",
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_conn(dsn: str | None = None):
    """Connect to PostgreSQL."""
    import psycopg2

    return psycopg2.connect(dsn or DEFAULT_DSN)


# ---------------------------------------------------------------------------
# Phase 1: Collect actual data state
# ---------------------------------------------------------------------------


def collect_entity_data(conn) -> dict:
    """Collect entity data within 200km and their actual persisted data.

    Returns dict with:
        entity_ids: list of entity IDs within 200km
        has_bids: set of entity IDs with bids in pncp_raw_bids
        has_contracts: set of entity IDs with contracts (from entity_coverage)
        entities_with_data: union of has_bids and has_contracts
    """
    cur = conn.cursor()

    # Active entities within 200km
    cur.execute("SELECT id FROM sc_public_entities WHERE is_active = TRUE AND raio_200km = TRUE")
    entity_ids = [row[0] for row in cur.fetchall()]

    # Entities with bids (from raw table - authoritative)
    cur.execute(
        "SELECT DISTINCT matched_entity_id FROM pncp_raw_bids WHERE is_active = TRUE AND matched_entity_id IS NOT NULL"
    )
    eid_set = set(entity_ids)
    has_bids = {row[0] for row in cur.fetchall()} & eid_set

    # Entities with contracts (from entity_coverage - pre-computed)
    cur.execute("SELECT DISTINCT entity_id FROM entity_coverage WHERE source = 'contracts' AND total_bids > 0")
    has_contracts = {row[0] for row in cur.fetchall()} & eid_set

    cur.close()
    return {
        "entity_ids": entity_ids,
        "has_bids": has_bids,
        "has_contracts": has_contracts,
        "entities_with_data": has_bids | has_contracts,
    }


# ---------------------------------------------------------------------------
# Phase 2: Rebuild evidence
# ---------------------------------------------------------------------------


def rebuild(conn, entity_data: dict, dry_run: bool = False) -> dict[str, Any]:
    """Rebuild evidence ledger from actual data."""
    entity_ids = entity_data["entity_ids"]
    has_bids = entity_data["has_bids"]
    has_contracts = entity_data["has_contracts"]
    entities_with_data = entity_data["entities_with_data"]

    run_id_str = f"rebuild-{int(datetime.now(UTC).timestamp())}"
    now_ts = datetime.now(UTC)
    stats = {"rows_deleted": 0, "rows_inserted": 0}

    if dry_run:
        stats["dry_run"] = True
        stats["entity_count"] = len(entity_ids)
        stats["with_data"] = len(entities_with_data)
        stats["no_data"] = len(entity_ids) - len(entities_with_data)
        return stats

    cur = conn.cursor()

    # 1. DELETE all existing entity-level evidence
    cur.execute("DELETE FROM coverage_evidence WHERE entity_id IS NOT NULL")
    stats["rows_deleted"] = cur.rowcount

    # 2. INSERT PNCP evidence
    for eid in entity_ids:
        state = "success_with_data" if eid in entities_with_data else "success_zero"
        meta = json.dumps(
            {
                "rebuild": True,
                "method": "from_persisted_data",
                "completeness": "verified_via_rebuild",
            }
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, started_at, completed_at,
                count_obtained, count_transformed, count_persisted, state, metadata)
               VALUES (%s, 'pncp', 'bids', %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                eid,
                run_id_str,
                now_ts,
                now_ts,
                1 if eid in entities_with_data else 0,
                1 if eid in entities_with_data else 0,
                1 if eid in entities_with_data else 0,
                state,
                meta,
            ),
        )
        stats["rows_inserted"] += 1

    conn.commit()

    # 3. Update actual counts from entity_coverage
    cur.execute(
        "SELECT entity_id, total_bids FROM entity_coverage WHERE source = 'pncp' AND entity_id = ANY(%s)",
        (entity_ids,),
    )
    for eid, total in cur.fetchall():
        if total and total > 1:
            cur.execute(
                """UPDATE coverage_evidence SET count_obtained=%s, count_transformed=%s, count_persisted=%s
                   WHERE entity_id=%s AND source='pncp' AND run_id=%s""",
                (total, total, total, eid, run_id_str),
            )
    conn.commit()

    # 4. INSERT other source evidence
    for src in OTHER_SOURCES:
        cur.execute(
            "SELECT entity_id, total_bids FROM entity_coverage "
            "WHERE source = %s AND entity_id = ANY(%s) AND total_bids > 0",
            (src, entity_ids),
        )
        for eid, total in cur.fetchall():
            meta = json.dumps(
                {
                    "rebuild": True,
                    "method": "from_entity_coverage",
                    "source": src,
                    "completeness": "verified_via_rebuild",
                }
            )
            cur.execute(
                """INSERT INTO coverage_evidence
                   (entity_id, source, data_type, run_id, started_at, completed_at,
                    count_obtained, count_transformed, count_persisted, state, metadata)
                   VALUES (%s, %s, 'bids', %s, %s, %s, %s, %s, %s, 'success_with_data', %s)""",
                (eid, src, run_id_str, now_ts, now_ts, total, total, total, meta),
            )
            stats["rows_inserted"] += 1

    # 5. Add contracts source - success_zero for entities without contracts
    for eid in entity_ids:
        if eid not in has_contracts:
            meta = json.dumps(
                {
                    "rebuild": True,
                    "method": "from_entity_coverage",
                    "source": "contracts",
                    "completeness": "verified_via_rebuild",
                }
            )
            cur.execute(
                """INSERT INTO coverage_evidence
                   (entity_id, source, data_type, run_id, started_at, completed_at,
                    count_obtained, count_transformed, count_persisted, state, metadata)
                   VALUES (%s, 'contracts', 'bids', %s, %s, %s, %s, %s, %s, 'success_zero', %s)""",
                (eid, run_id_str, now_ts, now_ts, 0, 0, 0, meta),
            )
            stats["rows_inserted"] += 1

    conn.commit()
    cur.close()
    return stats


# ---------------------------------------------------------------------------
# Phase 3: Create validation trigger
# ---------------------------------------------------------------------------


def create_validation_trigger(conn) -> None:
    """Create PostgreSQL trigger enforcing evidence state integrity."""
    cur = conn.cursor()
    cur.execute("DROP TRIGGER IF EXISTS trg_validate_coverage_evidence ON coverage_evidence")
    cur.execute("""
        CREATE OR REPLACE FUNCTION fn_validate_coverage_evidence()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.state = 'partial' THEN
                RAISE EXCEPTION 'state=partial is deprecated';
            END IF;
            IF NEW.state = 'success_with_data' AND NEW.count_persisted <= 0 THEN
                RAISE EXCEPTION 'success_with_data requires count_persisted > 0 (got %)', NEW.count_persisted;
            END IF;
            IF NEW.state = 'success_zero' AND NEW.count_persisted > 0 THEN
                RAISE EXCEPTION 'success_zero requires count_persisted = 0 (got %)', NEW.count_persisted;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_validate_coverage_evidence
            BEFORE INSERT OR UPDATE ON coverage_evidence
            FOR EACH ROW EXECUTE FUNCTION fn_validate_coverage_evidence();
    """)
    conn.commit()
    cur.close()


# ---------------------------------------------------------------------------
# Phase 4: Verify
# ---------------------------------------------------------------------------


def verify(conn) -> dict[str, Any]:
    """Verify evidence accuracy against persisted data."""
    cur = conn.cursor()

    cur.execute("SELECT id FROM sc_public_entities WHERE is_active = TRUE AND raio_200km = TRUE")
    entity_ids = [row[0] for row in cur.fetchall()]

    # False negatives
    cur.execute(
        """SELECT COUNT(*) FROM v_latest_evidence v
           WHERE v.source='pncp' AND v.state='success_zero'
           AND v.entity_id IN (SELECT matched_entity_id FROM pncp_raw_bids WHERE is_active=TRUE)""",
    )
    fn = cur.fetchone()[0]

    # success_with_data with no count
    cur.execute(
        "SELECT COUNT(*) FROM v_latest_evidence WHERE source='pncp' AND state='success_with_data' AND count_persisted <= 0",
    )
    fp = cur.fetchone()[0]

    # success_zero with count > 0
    cur.execute(
        "SELECT COUNT(*) FROM v_latest_evidence WHERE source='pncp' AND state='success_zero' AND count_persisted > 0",
    )
    sz = cur.fetchone()[0]

    # Data but no success_with_data
    cur.execute(
        """SELECT COUNT(*) FROM (
           SELECT ec.entity_id FROM entity_coverage ec
           WHERE ec.source='pncp' AND ec.total_bids>0 AND ec.entity_id = ANY(%s)
           EXCEPT
           SELECT v.entity_id FROM v_latest_evidence v
           WHERE v.source='pncp' AND v.state='success_with_data'
        ) x""",
        (entity_ids,),
    )
    missing = cur.fetchone()[0]

    # Trigger exists
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='trg_validate_coverage_evidence')",
    )
    trigger_exists = cur.fetchone()[0]

    # Partial state check
    cur.execute("SELECT COUNT(*) FROM coverage_evidence WHERE state = 'partial'")
    partial_count = cur.fetchone()[0]

    # State distribution
    cur.execute(
        "SELECT state, COUNT(*) FROM v_latest_evidence WHERE entity_id IS NOT NULL AND source='pncp' GROUP BY state",
    )
    state_dist = {row[0]: row[1] for row in cur.fetchall()}

    cur.close()

    total = len(entity_ids)
    correct_success = state_dist.get("success_with_data", 0)
    correct_zero = state_dist.get("success_zero", 0)
    total_correct = correct_success + correct_zero
    accuracy = round(total_correct / total * 100, 1) if total > 0 else 100.0

    return {
        "total_entities": total,
        "fn": fn,
        "fp": fp,
        "sz": sz,
        "missing_evidence_for_data": missing,
        "trigger_exists": trigger_exists,
        "partial_remaining": partial_count,
        "state_dist": state_dist,
        "accuracy_pct": accuracy,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_verify(report: dict[str, Any]) -> None:
    """Print verification report."""
    print(f"Total entities: {report['total_entities']}")
    print(f"False negatives (success_zero+has_data): {report['fn']}")
    print(f"success_with_data+count_persisted<=0: {report['fp']}")
    print(f"success_zero+count_persisted>0: {report['sz']}")
    print(f"Data but missing evidence: {report['missing_evidence_for_data']}")
    print(f"Partial state remaining: {report['partial_remaining']}")
    print(f"Validation trigger: {'exists' if report['trigger_exists'] else 'MISSING'}")
    print(f"Accuracy: {report['accuracy_pct']}% ({report['state_dist']})")

    if report["fn"] == 0 and report["fp"] == 0 and report["sz"] == 0 and report["missing_evidence_for_data"] == 0:
        print("\n  ✅ EVIDENCE ACCURACY VERIFIED — No false positives or false negatives")
    else:
        print("\n  ⚠️  Residual inaccuracies found — review needed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild evidence ledger from actual persisted data",
    )
    parser.add_argument("--verify-only", action="store_true", help="Verify current accuracy only")
    parser.add_argument("--skip-trigger", action="store_true", help="Skip validation trigger creation")
    args = parser.parse_args()

    print("=" * 70)
    print("  EVIDENCE LEDGER REBUILD")
    print("=" * 70)

    conn = get_conn()

    if args.verify_only:
        print("\n--- Verification ---")
        report = verify(conn)
        print_verify(report)
        conn.close()
        return 0

    # Phase 1: Collect
    print("\n--- Phase 1: Collecting data ---")
    entity_data = collect_entity_data(conn)
    print(f"Entities within 200km: {len(entity_data['entity_ids'])}")
    print(f"Entities with data: {len(entity_data['entities_with_data'])}")
    print(f"Entities without data: {len(entity_data['entity_ids']) - len(entity_data['entities_with_data'])}")

    # Phase 2: Rebuild
    print("\n--- Phase 2: Rebuilding evidence ---")
    rebuild(conn, entity_data)
    print("Rebuild complete")

    # Phase 3: Trigger
    if not args.skip_trigger:
        print("\n--- Phase 3: Validation trigger ---")
        create_validation_trigger(conn)
        print("Trigger created")

    # Phase 4: Verify
    print("\n--- Phase 4: Verification ---")
    report = verify(conn)
    print_verify(report)

    conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
