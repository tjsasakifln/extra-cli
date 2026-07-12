#!/usr/bin/env python3
"""Measure baseline entity matching coverage before/after changes.

Usage:
    python scripts/matching/measure_baseline.py              # Full baseline report
    python scripts/matching/measure_baseline.py --before     # Pre-change baseline
    python scripts/matching/measure_baseline.py --after      # Post-change validation
    python scripts/matching/measure_baseline.py --regression # Check zero regression

Output:
    - Baseline stats printed to stdout
    - JSON report saved to ``plan/baseline-matching.json`` (if dir exists)

This script is used by Story COVERAGE-1.1 (AC1, AC7, AC8).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DEFAULT_DSN  # noqa: E402 — sys.path must be set first


def measure_baseline(conn: Any, label: str = "baseline") -> dict:
    """Measure current entity matching coverage across all sources.

    Args:
        conn: Database connection.
        label: Label for this measurement (``baseline``, ``after``, ``regression``).

    Returns:
        Dict with baseline stats.
    """
    cur = conn.cursor()
    result: dict = {
        "label": label,
        "by_source": {},
        "total_bids": 0,
        "total_matched": 0,
        "total_unmatched": 0,
        "distinct_entities_covered": 0,
        "by_method": {},
    }

    # AC1: Per-source matching rates
    cur.execute(
        """SELECT source,
                  COUNT(*) AS total_bids,
                  COUNT(*) FILTER (WHERE matched_entity_id IS NOT NULL) AS matched,
                  COUNT(*) FILTER (WHERE matched_entity_id IS NULL) AS unmatched,
                  ROUND(
                      COUNT(*) FILTER (WHERE matched_entity_id IS NOT NULL)::numeric
                      / GREATEST(COUNT(*), 1) * 100, 1
                  ) AS pct
           FROM pncp_raw_bids
           GROUP BY source
           ORDER BY source"""
    )
    for row in cur.fetchall():
        source, total, matched, unmatched, pct = row
        result["by_source"][source] = {
            "total": total,
            "matched": matched,
            "unmatched": unmatched,
            "pct": float(pct) if pct is not None else 0.0,
        }
        result["total_bids"] += total
        result["total_matched"] += matched
        result["total_unmatched"] += unmatched

    # Distinct entities covered (by matched_entity_id)
    cur.execute(
        """SELECT COUNT(DISTINCT matched_entity_id)
           FROM pncp_raw_bids
           WHERE matched_entity_id IS NOT NULL"""
    )
    result["distinct_entities_covered"] = cur.fetchone()[0] or 0

    # AC7/AC8: By match method
    cur.execute(
        """SELECT COALESCE(match_method, 'unmatched') AS method,
                  COUNT(*) AS cnt
           FROM pncp_raw_bids
           GROUP BY match_method
           ORDER BY method"""
    )
    for row in cur.fetchall():
        method, cnt = row
        result["by_method"][method or "unmatched"] = cnt

    cur.close()

    # Summary
    total = result["total_bids"]
    result["overall_pct"] = round(result["total_matched"] / total * 100, 1) if total > 0 else 0.0

    return result


def print_baseline_report(result: dict) -> None:
    """Print baseline report to stdout."""
    print("\n" + "=" * 72)
    print(f"  Entity Matching Baseline Report — {result['label']}")
    print("=" * 72)

    print(f"\n  Overall: {result['total_matched']}/{result['total_bids']} "
          f"matched ({result['overall_pct']}%)")
    print(f"  Distinct entities covered: {result['distinct_entities_covered']}")

    print("\n  --- By Source ---")
    for source, stats in sorted(result["by_source"].items()):
        print(f"    {source:20s}: {stats['matched']:6d}/{stats['total']:6d} "
              f"({stats['pct']:5.1f}%)  [{stats['unmatched']} unmatched]")

    print("\n  --- By Match Method ---")
    for method, cnt in sorted(result["by_method"].items()):
        print(f"    {method:20s}: {cnt}")

    print("\n" + "=" * 72 + "\n")


def save_report(result: dict, path: str | None = None) -> str | None:
    """Save baseline report to JSON file.

    Args:
        result: Baseline dict from ``measure_baseline()``.
        path: Optional file path.  Defaults to ``plan/baseline-matching.json``.

    Returns:
        Path where report was saved, or ``None`` if directory missing.
    """
    if path is None:
        path = str(_PROJECT_ROOT / "plan" / "baseline-matching.json")

    dir_path = os.path.dirname(path)
    if not os.path.isdir(dir_path):
        return None

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure entity matching coverage baseline"
    )
    parser.add_argument(
        "--before",
        action="store_true",
        help="Alias for baseline measurement (pre-change)",
    )
    parser.add_argument(
        "--after",
        action="store_true",
        help="Post-change validation measurement",
    )
    parser.add_argument(
        "--regression",
        action="store_true",
        help="Compare with saved baseline and detect regression",
    )
    parser.add_argument(
        "--dsn",
        default=DEFAULT_DSN,
        help="PostgreSQL DSN",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save report to plan/baseline-matching.json",
    )
    args = parser.parse_args()

    label = "baseline"
    if args.after:
        label = "after"
    elif args.regression:
        label = "regression"

    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        result = measure_baseline(conn, label=label)

        # Regression check (AC8): compare after with saved baseline
        if args.regression:
            baseline_path = _PROJECT_ROOT / "plan" / "baseline-matching.json"
            if baseline_path.exists():
                with open(baseline_path, encoding="utf-8") as f:
                    baseline = json.load(f)

                # Check: every entity that was covered before must still be covered
                before_entities = baseline.get("distinct_entities_covered", 0)
                after_entities = result["distinct_entities_covered"]

                print_baseline_report(result)

                if after_entities < before_entities:
                    lost = before_entities - after_entities
                    print(f"  ❌ REGRESSION: {lost} entities lost coverage "
                          f"({before_entities} -> {after_entities})")
                    return 1
                else:
                    gained = after_entities - before_entities
                    print(f"  ✅ ZERO REGRESSION: {before_entities} -> "
                          f"{after_entities} entities covered (+{gained})")
                    return 0
            else:
                print("  ⚠️  No saved baseline found. Run with --before first.")
                print_baseline_report(result)
                return 1

        print_baseline_report(result)

        if args.save or args.before:
            saved = save_report(result)
            if saved:
                print(f"  Report saved to: {saved}")
            else:
                print("  ⚠️  plan/ directory not found — report not saved")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
