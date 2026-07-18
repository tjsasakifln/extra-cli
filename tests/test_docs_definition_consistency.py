"""DoD §25 residual — docs share definitions; no out-of-scope promises."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.scan_docs_definition_consistency import (
    scan_conflicting_numbers,
    scan_out_of_scope_promises,
    scan_repo,
    scan_shared_definitions,
)

REPO = Path(__file__).resolve().parents[1]


def test_repo_scan_runs() -> None:
    report = scan_repo(REPO)
    assert "ok" in report
    assert report["canonical_docs"]


def test_shared_definitions_dod_has_universe_and_signal() -> None:
    defs = scan_shared_definitions(REPO)
    assert "DOD.md" in defs["present"]["universe_1093"]
    assert defs["ok"] is True


def test_out_of_scope_promises_empty_on_canonical_docs() -> None:
    findings = scan_out_of_scope_promises(REPO)
    assert findings == [], findings


def test_conflicting_high_coverage_claims_contextualized() -> None:
    nums = scan_conflicting_numbers(REPO)
    assert nums["ok"] is True, nums["conflicts"]


def test_cli_exit_matches_ok() -> None:
    from scripts.ops.scan_docs_definition_consistency import main

    code = main(["--repo", str(REPO)])
    assert code in (0, 1)
    report = scan_repo(REPO)
    assert (code == 0) == report["ok"]
