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
    # Explicit DATABASE_URL / LOCAL_DATALAKE_DSN wins, including canonical :5433.
    # Port 5436 is only the isolated-campaign fallback inside resolve_probe_dsn.
    return resolve_probe_dsn()


@pytest.fixture(scope="function")
def pg_conn(national_intel_dsn: str) -> Iterator:
    result = probe_national_intel(national_intel_dsn)
    admit_or_raise(result)
    try:
        from scripts.national_intel.db import connect
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"db helper unavailable: {exc}")
    require_real = os.environ.get("REQUIRE_REAL_DB", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        with connect(national_intel_dsn, connect_timeout=2) as conn:
            if hasattr(conn, "rollback"):
                conn.rollback()
            yield conn
            if hasattr(conn, "rollback"):
                conn.rollback()
    except Exception as exc:
        from scripts.testing.real_db_guard import DB_UNAVAILABLE, dsn_host_for_logs

        host = dsn_host_for_logs(national_intel_dsn)
        message = f"{DB_UNAVAILABLE}: connect failed after preflight at {host}: {type(exc).__name__}"
        if require_real:
            pytest.fail(message)
        pytest.skip(message)
