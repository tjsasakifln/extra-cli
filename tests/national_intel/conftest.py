"""Fixtures for national_intel tests — isolated DSN only."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Prefer campaign isolated DB (5436); fall back to legacy PR121 port 5435.
DEFAULT_ISOLATED = os.environ.get(
    "CAMPAIGN_TEST_DSN",
    "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc",
)


@pytest.fixture(scope="session")
def national_intel_dsn() -> str:
    dsn = os.environ.get("NATIONAL_INTEL_DSN", DEFAULT_ISOLATED)
    # Refuse accidental HC writer if env forces it without override flag
    if ":5433/" in dsn and os.environ.get("ALLOW_NI_ON_5433") != "1":
        pytest.skip("Refusing tests on port 5433 without ALLOW_NI_ON_5433=1")
    return dsn


@pytest.fixture(scope="function")
def pg_conn(national_intel_dsn: str) -> Iterator:
    try:
        from scripts.national_intel.db import connect
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"db helper unavailable: {exc}")
    try:
        with connect(national_intel_dsn) as conn:
            # Autocommit-friendly: ensure clean transaction per test
            if hasattr(conn, "rollback"):
                conn.rollback()
            yield conn
            if hasattr(conn, "rollback"):
                conn.rollback()
    except Exception as exc:
        pytest.skip(f"isolated Postgres unavailable: {exc}")
