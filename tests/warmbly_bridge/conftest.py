"""Shared fixtures for warmbly_bridge tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "scripts" / "warmbly_bridge" / "fixtures"
SCHEMAS = Path(__file__).resolve().parents[2] / "scripts" / "warmbly_bridge" / "schemas"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def schemas_dir() -> Path:
    return SCHEMAS


@pytest.fixture
def universe_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "universe.jsonl"


@pytest.fixture
def intel_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "account_intelligence.jsonl"


@pytest.fixture
def contacts_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "contacts.jsonl"


@pytest.fixture
def outcome_fixture(fixtures_dir: Path) -> Path:
    return fixtures_dir / "outcome_contacted.json"
