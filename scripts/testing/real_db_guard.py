"""#285 — admission control for @pytest.mark.real_db.

A real_db test never receives a MagicMock connection. Missing opt-in is an
explicit skip or configuration error before the test body runs. A live
canonical DSN uses the real driver connection type.
"""

from __future__ import annotations

import os
from typing import Literal
from unittest.mock import MagicMock

Strategy = Literal["real", "skip", "config_error", "mock"]


def env_flag(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def canonical_dsn() -> str:
    return os.environ.get(
        "LOCAL_DATALAKE_DSN",
        "postgresql://test:test@127.0.0.1:5433/extra_test",
    )


def require_real_db() -> bool:
    return env_flag("REQUIRE_REAL_DB")


def dsn_is_reachable(dsn: str | None = None, *, opener: object | None = None) -> bool:
    """Probe the canonical DSN. opener(dsn) must return an object with close()."""
    target = dsn or canonical_dsn()
    if opener is None:
        try:
            import psycopg2
        except ImportError:
            return False
        opener = psycopg2.connect
    try:
        conn = opener(target, connect_timeout=2)  # type: ignore[operator]
    except Exception:
        return False
    closer = getattr(conn, "close", None)
    if callable(closer):
        closer()
    return True


def decide_connection_strategy(
    *,
    real_db_marker: bool,
    require_real: bool,
    db_available: bool,
) -> Strategy:
    """Pure admission. real_db never returns 'mock'."""
    if real_db_marker:
        if require_real and db_available:
            return "real"
        if require_real and not db_available:
            return "config_error"
        return "skip"
    return "mock"


def connection_type_name(conn: object) -> str:
    return type(conn).__name__


def is_magic_mock(conn: object) -> bool:
    return isinstance(conn, MagicMock)


def admit_real_db_or_raise(
    *,
    real_db_marker: bool,
    require_real: bool | None = None,
    db_available: bool | None = None,
) -> Strategy:
    """Used by the pytest fixture. Skip/error happen before a mock is installed."""
    import pytest

    required = require_real_db() if require_real is None else require_real
    available = dsn_is_reachable() if db_available is None else db_available
    strategy = decide_connection_strategy(
        real_db_marker=real_db_marker,
        require_real=required,
        db_available=available,
    )
    if strategy == "skip":
        pytest.skip(
            "real_db test requires REQUIRE_REAL_DB=1 and the canonical DSN; "
            "refusing silent MagicMock (issue #285)"
        )
    if strategy == "config_error":
        raise pytest.UsageError(
            "REQUIRE_REAL_DB=1 but the canonical DSN is not reachable; "
            f"dsn={canonical_dsn()!r}. This is a configuration error, not a missing table."
        )
    return strategy
