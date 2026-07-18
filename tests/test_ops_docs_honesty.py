"""DoD §31 operational docs honesty — shipped scanner."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.scan_ops_docs_honesty import scan

REPO = Path(__file__).resolve().parents[1]


def test_ops_docs_honesty_scan_ok() -> None:
    report = scan(REPO)
    assert report["missing"] == [], report
    assert report["checks"]["readme_honesty_markers"] is True
    assert report["checks"]["runbook_rollback_drift_coverage"] is True
    assert report["checks"]["adr_index_active"] is True
    assert report["checks"]["adr_index_revoked_section"] is True
    assert report["checks"]["glossary_universe_1093"] is True
    assert report["ok"] is True


def test_cli_exit_zero() -> None:
    from scripts.ops.scan_ops_docs_honesty import main

    assert main(["--repo", str(REPO)]) == 0
