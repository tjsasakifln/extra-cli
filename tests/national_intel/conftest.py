"""Fixtures for national_intel tests — isolated DSN only."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from scripts.national_intel.preflight import (
    admit_or_raise,
    probe_national_intel,
    resolve_probe_dsn,
)


@pytest.fixture(scope="session")
def national_intel_dsn() -> str:
    dsn = resolve_probe_dsn()
    # Refuse accidental HC writer if env forces it without override flag
    if ":5433/" in dsn and os.environ.get("ALLOW_NI_ON_5433") != "1":
        pytest.skip("Refusing tests on port 5433 without ALLOW_NI_ON_5433=1")
    return dsn


@pytest.fixture(scope="function")
def pg_conn(national_intel_dsn: str) -> Iterator:
    result = probe_national_intel(national_intel_dsn)
    admit_or_raise(result)
    try:
        from scripts.national_intel.db import connect
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"db helper unavailable: {exc}")
    try:
        with connect(national_intel_dsn, connect_timeout=2) as conn:
            if hasattr(conn, "rollback"):
                conn.rollback()
            yield conn
            if hasattr(conn, "rollback"):
                conn.rollback()
    except Exception as exc:
        pytest.skip(f"isolated Postgres unavailable after preflight: {exc}")
