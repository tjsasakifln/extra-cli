"""Prove mandatory gates never swallow failures with ``|| true``.

Exercises the shipped scanner ``scripts.ops.scan_mandatory_gates_failclosed``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops.scan_mandatory_gates_failclosed import (
    MANDATORY_GATE_PATHS,
    scan_repo,
    scan_text,
)

REPO = Path(__file__).resolve().parents[1]


def test_mandatory_gate_paths_exist() -> None:
    missing = [p for p in MANDATORY_GATE_PATHS if not (REPO / p).is_file()]
    assert missing == [], f"mandatory gate files missing: {missing}"


def test_scan_text_detects_or_true_on_code_line() -> None:
    findings = scan_text(
        "scripts/ci_gate.sh",
        "set -euo pipefail\nruff check scripts/ || true\n",
    )
    assert any(f.kind == "or_true" for f in findings)


def test_scan_text_detects_continue_on_error_true() -> None:
    findings = scan_text(
        ".github/workflows/ci.yml",
        "jobs:\n  lint:\n    continue-on-error: true\n",
    )
    assert any(f.kind == "continue_on_error_true" for f in findings)


def test_scan_text_ignores_comment_and_ban_docs() -> None:
    findings = scan_text(
        ".github/workflows/ci.yml",
        "# NENHUM job usa continue-on-error:true ou || true\n"
        "# ruff check || true  # banned pattern documented only\n"
        "name: CI\n",
    )
    assert findings == []


def test_scan_text_does_not_let_ban_marker_mask_code() -> None:
    """Adversarial: `cmd || true  # no || true` must still be a violation."""
    findings = scan_text(
        "scripts/ci_gate.sh",
        "ruff check scripts/ || true  # no || true documented ban\n",
    )
    assert any(f.kind == "or_true" for f in findings)


def test_repo_mandatory_gates_are_fail_closed() -> None:
    """Live repo scan — this is the operational proof for DoD §13.4."""
    report = scan_repo(REPO)
    assert report["missing"] == [], report
    assert report["findings"] == [], report
    assert report["ok"] is True
    assert report["counts"]["scanned"] == len(MANDATORY_GATE_PATHS)


def test_cli_exit_zero_on_clean_repo() -> None:
    from scripts.ops.scan_mandatory_gates_failclosed import main

    assert main(["--repo", str(REPO)]) == 0
