"""Run entity matching on unmatched PNCP bids.

Usage: python scripts/coverage/run_matching.py

This script runs entity matching on all unmatched PNCP bids
and reports coverage gain.
"""

from __future__ import annotations

import os
import sys

# Ensure project root is in path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def main() -> None:
    """Load entities, run matching, report coverage."""
    import psycopg2

    from config.settings import DEFAULT_DSN

    conn = psycopg2.connect(DEFAULT_DSN, connect_timeout=10)

    # Load entities using monitor.py's own functions
    from scripts.crawl.monitor import _load_entities, _match_entities_cascade

    entities = _load_entities(conn)
    print(f"Loaded {len(entities)} entities")

    # Count unmatched before
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM pncp_raw_bids WHERE source = %s AND matched_entity_id IS NULL",
        ("pncp",),
    )
    unmatched_before = cur.fetchone()[0]
    print(f"Unmatched PNCP bids before: {unmatched_before}")
    cur.close()

    # Run entity matching
    print("Running entity matching...")
    stats = _match_entities_cascade(conn, "pncp", entities)
    print("Matching complete:")
    print(f"  CNPJ matched: {stats.get('cnpj', 0)}")
    print(f"  Name matched: {stats.get('name_normalized', 0)}")
    print(f"  Fuzzy matched: {stats.get('fuzzy', 0)}")
    print(f"  Unmatched: {stats.get('unmatched', 0)}")
    print(f"  Total processed: {stats.get('total', 0)}")

    # Coverage after matching
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT entity_id) FROM entity_coverage WHERE is_covered = TRUE AND source = %s",
        ("pncp",),
    )
    after = cur.fetchone()[0]
    print(f"PNCP coverage after matching: {after}")
    cur.close()

    conn.close()


if __name__ == "__main__":
    main()
