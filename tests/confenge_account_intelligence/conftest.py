"""Fixtures for account-intelligence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def regional_lean() -> dict:
    return _load("regional_lean.json")


@pytest.fixture
def national_structured() -> dict:
    return _load("national_structured.json")


@pytest.fixture
def addendum_signals() -> dict:
    return _load("addendum_signals.json")


@pytest.fixture
def mature_no_reajuste() -> dict:
    return _load("mature_no_reajuste.json")


@pytest.fixture
def insufficient_facts() -> dict:
    return _load("insufficient_facts.json")


@pytest.fixture
def do_not_contact() -> dict:
    return _load("do_not_contact.json")
