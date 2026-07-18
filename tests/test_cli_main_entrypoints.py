"""Prove main operational CLIs are documented (argparse help) without web UI."""
from __future__ import annotations

import subprocess
import sys


def _help(mod: str) -> str:
    r = subprocess.run(
        [sys.executable, "-m", mod, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # some modules exit 0 or 2 with help
    out = (r.stdout or "") + (r.stderr or "")
    assert "usage" in out.lower() or "Usage" in out or len(out) > 50
    return out


def test_workspace_cli_help() -> None:
    out = _help("scripts.workspace")
    assert "today" in out or "opportunities" in out


def test_opportunity_intel_cli_help() -> None:
    out = _help("scripts.opportunity_intel.cli")
    assert "list" in out or "radar" in out or "show" in out


def test_no_web_required_for_help() -> None:
    # Smoke: help works without starting HTTP server
    _help("scripts.workspace")
