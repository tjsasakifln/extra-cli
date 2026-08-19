"""Frontier tests are pure — do not require the global psycopg2 connect patch."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_psycopg2_connect():
    yield
