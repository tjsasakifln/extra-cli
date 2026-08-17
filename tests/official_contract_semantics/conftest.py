"""Paths for official-semantics fixtures. Does not patch official/live sources."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "contracts" / "fixtures" / "official_semantics"
SCRIPTS_DIR = REPO_ROOT / "scripts" / "official_contract_semantics"
