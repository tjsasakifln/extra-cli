#!/usr/bin/env python3
"""Inventory schema-gated test modules that block the full suite (#33).

Lists modules that skip or fail closed when the isolated PostgreSQL schema
(or required canonical views) is absent. Does not claim the full suite is green.

Usage:
    python3 -m scripts.schema.full_suite_debt
    python3 -m scripts.schema.full_suite_debt --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.schema.diagnostics import EXPECTED_VIEWS

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TESTS_ROOT = _PROJECT_ROOT / "tests"

# Views created by 030/041a and consumed by consulting/coverage code.
# Absence of these in EXPECTED_VIEWS was the honest schema-debt hole.
CANONICAL_VIEWS_REQUIRED: tuple[str, ...] = (
    "v_entities_canonical",
    "v_open_opportunities_canonical",
    "v_contracts_canonical",
    "v_suppliers_canonical",
)

_SKIP_RE = re.compile(
    r"skipif\s*\(.*?(REQUIRE_TEST_DB|REQUIRE_REAL_DB|relation|undefinedtable|schema)",
    re.I | re.S,
)
_DB_MARK_RE = re.compile(r"pytest\.mark\.(database|integration|real_db)")


def scan_schema_gated_modules(tests_root: Path | None = None) -> list[dict[str, str]]:
    """Walk tests/ and list modules that are schema/DB gated."""
    root = tests_root or _TESTS_ROOT
    found: list[dict[str, str]] = []
    for path in sorted(root.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        reasons: list[str] = []
        if _SKIP_RE.search(text):
            reasons.append("skipif_schema_or_real_db")
        if _DB_MARK_RE.search(text) and (
            "REQUIRE_TEST_DB" in text or "REQUIRE_REAL_DB" in text or "relation" in text.lower()
        ):
            reasons.append("db_marker_plus_schema_guard")
        if "EXPECTED_VIEWS" in text or "v_entities_canonical" in text:
            reasons.append("canonical_view_consumer")
        if not reasons:
            continue
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        found.append(
            {
                "module": rel,
                "reason": ",".join(sorted(set(reasons))),
                "class": "SKIPPED_SCHEMA",
            }
        )
    return found


def canonical_view_gaps(expected: set[str] | None = None) -> list[str]:
    registered = expected if expected is not None else EXPECTED_VIEWS
    return [name for name in CANONICAL_VIEWS_REQUIRED if name not in registered]


def inventory_schema_debt(tests_root: Path | None = None) -> dict[str, Any]:
    modules = scan_schema_gated_modules(tests_root)
    gaps = canonical_view_gaps()
    next_test = (
        "tests/integration/test_migration_fresh_install.py"
        if gaps
        else "tests/test_full_suite_schema_debt.py"
    )
    return {
        "failing_or_skipped_modules": modules,
        "module_count": len(modules),
        "canonical_views_required": list(CANONICAL_VIEWS_REQUIRED),
        "canonical_view_gaps": gaps,
        "canonical_views_registered": gaps == [],
        "blocked": bool(gaps),
        "blocked_reason": (
            "EXPECTED_VIEWS missing canonical Story 1.2 views"
            if gaps
            else None
        ),
        "next_test": next_test,
        "claims_forbidden": ["full suite green", "LOCAL_READY", "CI_GREEN"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List schema-gated full-suite debt (#33)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = inventory_schema_debt()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"schema-gated modules: {report['module_count']}")
        for row in report["failing_or_skipped_modules"]:
            print(f"  {row['class']}: {row['module']} ({row['reason']})")
        if report["canonical_view_gaps"]:
            print(f"BLOCKED views: {', '.join(report['canonical_view_gaps'])}")
        else:
            print("canonical views registered in EXPECTED_VIEWS")
        print(f"next test: {report['next_test']}")
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
