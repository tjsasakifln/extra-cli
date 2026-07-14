"""Integration test: validate all SQL references in Python code resolve to real schema objects.

This test enforces that EVERY SQL query embedded in Python references only
known tables, views, and functions that exist in the schema. It is the
primary gate for preventing schema drift between code and database.

Part of Story 1.2 (Unify Schema): AC #1 — Zero query with schema errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.schema.audit_sql_references import (
    KNOWN_SCHEMA_OBJECTS,
    scan_directory,
)


def test_all_sql_references_resolve():
    """Every SQL reference in scripts/ must resolve to a known schema object.

    This test scans all Python files for embedded SQL queries, extracts
    table/view/function references, and verifies each against the known
    schema objects list.

    The known schema objects list MUST be kept in sync with migrations.
    When new tables/views/functions are added to the schema, they must
    be added to audit_sql_references.KNOWN_SCHEMA_OBJECTS.
    """
    report = scan_directory(str(PROJECT_ROOT / "scripts"))

    # Collect all suspicious references with their file:line
    failures = []
    for ref in report.references:
        if ref.suspicious:
            for obj in sorted(ref.tables_referenced - KNOWN_SCHEMA_OBJECTS):
                # Filter out common false positives
                if obj[0].islower() and not any(
                    kw in obj.lower()
                    for kw in [
                        "timestamp",
                        "numeric",
                        "varchar",
                        "integer",
                        "boolean",
                        "bigint",
                        "serial",
                        "decimal",
                        "precision",
                        "interval",
                    ]
                ):
                    failures.append(
                        f"  {ref.file}:{ref.line} — unknown object `{obj}`\n    SQL: {ref.sql_snippet[:120]}"
                    )

    if failures:
        msg = (
            "\nSQL references to unknown schema objects:\n"
            + "\n".join(failures)
            + f"\n\nKnown schema objects: {len(KNOWN_SCHEMA_OBJECTS)} tables/views/functions"
            + "\nAdd missing objects to audit_sql_references.KNOWN_SCHEMA_OBJECTS if they are valid."
        )
        pytest.fail(msg)


def test_known_schema_objects_are_not_empty():
    """The KNOWN_SCHEMA_OBJECTS set must have entries."""
    assert len(KNOWN_SCHEMA_OBJECTS) > 20, (
        f"KNOWN_SCHEMA_OBJECTS has only {len(KNOWN_SCHEMA_OBJECTS)} entries. "
        "Populate it with all tables, views, and functions from migrations."
    )


def test_critical_tables_exist_in_known():
    """Critical tables must be in the known schema objects list."""
    critical = {
        "pncp_raw_bids",
        "pncp_supplier_contracts",
        "sc_public_entities",
        "entity_coverage",
        "opportunity_intel",
        "coverage_evidence",
    }
    missing = critical - KNOWN_SCHEMA_OBJECTS
    assert not missing, f"Critical tables missing from KNOWN_SCHEMA_OBJECTS: {missing}"


def test_canonical_views_exist_in_known():
    """All 5 canonical views must be registered."""
    canonical = {
        "v_entities_canonical",
        "v_open_opportunities_canonical",
        "v_contracts_canonical",
        "v_suppliers_canonical",
        "v_value_observations_canonical",
    }
    missing = canonical - KNOWN_SCHEMA_OBJECTS
    assert not missing, f"Canonical views missing from KNOWN_SCHEMA_OBJECTS: {missing}"
