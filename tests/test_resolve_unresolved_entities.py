"""Regression tests for the unresolved-entity repair command."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from scripts.fix import resolve_unresolved_entities as resolver


def test_main_runs_readiness_without_shell() -> None:
    resolved = {
        "total_unresolved": 12,
        "still_unresolved": 0,
        "failed_municipalities": [],
    }
    completed = SimpleNamespace(returncode=2)

    with (
        patch.object(resolver, "resolve", return_value=resolved),
        patch.object(resolver.subprocess, "run", return_value=completed) as run,
    ):
        assert resolver.main() == 2

    readiness_script = resolver.PROJECT_ROOT / "scripts" / "consulting_readiness.py"
    run.assert_called_once_with([sys.executable, str(readiness_script)], check=False)
