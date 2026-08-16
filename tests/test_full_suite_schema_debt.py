"""#33 — list schema-blocked suite modules and keep canonical views in baseline."""

from __future__ import annotations

import json
import subprocess
import sys

from scripts.schema.diagnostics import EXPECTED_VIEWS
from scripts.schema.full_suite_debt import (
    CANONICAL_VIEWS_REQUIRED,
    inventory_schema_debt,
)


def test_canonical_views_are_in_expected_baseline() -> None:
    missing = [name for name in CANONICAL_VIEWS_REQUIRED if name not in EXPECTED_VIEWS]
    assert missing == []


def test_inventory_lists_real_schema_gated_modules() -> None:
    report = inventory_schema_debt()
    assert report["canonical_views_registered"] is True
    assert report["blocked"] is False
    modules = {row["module"] for row in report["failing_or_skipped_modules"]}
    assert report["module_count"] == len(modules) > 0
    assert any("test_" in name and name.endswith(".py") for name in modules)
    assert report["next_test"]


def test_cli_json_matches_inventory() -> None:
    cmd = [sys.executable, "-m", "scripts.schema.full_suite_debt", "--json"]
    first = subprocess.run(cmd, capture_output=True, text=True, check=False)
    second = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert first.returncode == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    live = inventory_schema_debt()
    assert payload["module_count"] == live["module_count"]
    assert payload["canonical_view_gaps"] == []
    assert payload["failing_or_skipped_modules"]
