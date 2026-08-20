"""#285 — admission control for @pytest.mark.real_db.

A real_db test never receives a MagicMock connection. Missing opt-in is an
explicit skip or configuration error before the test body runs. A live
canonical DSN uses the real driver connection type.

Named preflight states (issue #341 / #343):

- DB_UNAVAILABLE — host unreachable, driver missing, or MagicMock
- DB_REACHABLE_SCHEMA_MISSING — connected, required tables/views absent
- DB_READY — real driver + required schema present

REQUIRE_REAL_DB=1 + explicit DSN: missing connection/schema is a fail, not a skip.
Optional mode: skip fast with the named state in the reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal
from unittest.mock import MagicMock
from urllib.parse import urlparse

Strategy = Literal["real", "skip", "config_error", "mock"]
AdmissionState = Literal["DB_UNAVAILABLE", "DB_REACHABLE_SCHEMA_MISSING", "DB_READY"]

DB_UNAVAILABLE = "DB_UNAVAILABLE"
DB_REACHABLE_SCHEMA_MISSING = "DB_REACHABLE_SCHEMA_MISSING"
DB_READY = "DB_READY"

CONNECT_TIMEOUT_SECONDS = 2

_DSN_ENV_KEYS: tuple[str, ...] = (
    "LOCAL_DATALAKE_DSN",
    "DATABASE_URL",
    "NATIONAL_INTEL_DSN",
    "CAMPAIGN_TEST_DSN",
)


def env_flag(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def canonical_dsn() -> str:
    """Canonical test DSN. Explicit env wins; never exclusive to port 5436."""
    for key in _DSN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "postgresql://test:test@127.0.0.1:5433/extra_test"


def explicit_dsn_provided() -> bool:
    return any(os.environ.get(key, "").strip() for key in _DSN_ENV_KEYS)


def require_real_db() -> bool:
    return env_flag("REQUIRE_REAL_DB")


def dsn_host_for_logs(dsn: str) -> str:
    """Host/port/db only. Never return credentials."""
    try:
        parsed = urlparse(dsn)
        host = parsed.hostname or "unknown"
        port = parsed.port
        db = (parsed.path or "").lstrip("/") or "unknown"
        if port:
            return f"{host}:{port}/{db}"
        return f"{host}/{db}"
    except Exception:
        return "unparsed"


def connection_type_name(conn: object) -> str:
    return type(conn).__name__


def connection_kind(conn: object) -> str:
    if conn is None:
        return "none"
    if isinstance(conn, MagicMock):
        return "MagicMock"
    module = type(conn).__module__ or ""
    name = type(conn).__name__
    if "mock" in module.lower() or name in {"MagicMock", "AsyncMock", "NonCallableMagicMock"}:
        return "MagicMock"
    if "psycopg2" in module:
        return "psycopg2"
    if module.startswith("psycopg.") or module == "psycopg":
        return "psycopg"
    return name


def is_magic_mock(conn: object) -> bool:
    return connection_kind(conn) == "MagicMock"


def refuse_magic_mock_sql(conn: object, *, context: str) -> str:
    """A MagicMock fetch is never accepted as SQL."""
    kind = connection_kind(conn)
    if kind == "MagicMock":
        raise RuntimeError(
            f"{DB_UNAVAILABLE}: {context}: MagicMock is not a PostgreSQL connection "
            f"(host={dsn_host_for_logs(canonical_dsn())})"
        )
    return kind


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
        conn = opener(target, connect_timeout=CONNECT_TIMEOUT_SECONDS)  # type: ignore[operator]
    except TypeError:
        try:
            conn = opener(target)  # type: ignore[operator]
        except Exception:
            return False
    except Exception:
        return False
    if is_magic_mock(conn):
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
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


@dataclass(frozen=True)
class AdmissionResult:
    state: AdmissionState
    reason: str
    kind: str
    host: str
    missing: tuple[str, ...] = ()
    missing_views: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.state == DB_READY


def _existing_relations(conn: object, *, kind: str, names: tuple[str, ...]) -> set[str]:
    if not names:
        return set()
    table_type = "BASE TABLE" if kind == "table" else "VIEW"
    found: set[str] = set()
    sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = %s AND table_name = %s"
    )
    cursor = conn.cursor()  # type: ignore[union-attr]
    try:
        with cursor:
            for name in names:
                cursor.execute(sql, (table_type, name))
                row = cursor.fetchone()
                if not row:
                    continue
                if isinstance(row, dict):
                    found.add(str(row.get("table_name")))
                else:
                    found.add(str(row[0]))
    except TypeError:
        # cursor is not a context manager
        for name in names:
            cursor.execute(sql, (table_type, name))
            row = cursor.fetchone()
            if not row:
                continue
            if isinstance(row, dict):
                found.add(str(row.get("table_name")))
            else:
                found.add(str(row[0]))
    return found


def probe_database(
    dsn: str | None = None,
    *,
    timeout: int = CONNECT_TIMEOUT_SECONDS,
    opener: Any | None = None,
    required_tables: tuple[str, ...] = (),
    required_views: tuple[str, ...] = (),
    context: str = "real_db",
) -> AdmissionResult:
    """Classify connection + schema BEFORE any product SQL.

    Never logs the DSN. Never treats MagicMock as PostgreSQL. information_schema
    only — a late UndefinedTable in a test body is a harness defect.
    """
    target = dsn or canonical_dsn()
    host = dsn_host_for_logs(target)
    connect = opener
    if connect is None:
        try:
            import psycopg2
        except ImportError as exc:
            return AdmissionResult(
                DB_UNAVAILABLE,
                f"{context}: psycopg2 unavailable: {exc}",
                "none",
                host,
            )
        connect = psycopg2.connect

    conn: Any = None
    try:
        try:
            conn = connect(target, connect_timeout=timeout)
        except TypeError:
            try:
                conn = connect(target, timeout=timeout)
            except TypeError:
                conn = connect(target)
    except Exception as exc:
        return AdmissionResult(
            DB_UNAVAILABLE,
            f"{context}: database unreachable at {host}: {type(exc).__name__}",
            "none",
            host,
        )

    kind = connection_kind(conn)
    if kind == "MagicMock":
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        return AdmissionResult(
            DB_UNAVAILABLE,
            f"{context}: MagicMock is not a PostgreSQL connection at {host}",
            "MagicMock",
            host,
        )

    if not required_tables and not required_views:
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        return AdmissionResult(
            DB_READY,
            f"{context}: reachable via {kind} at {host}",
            kind,
            host,
        )

    try:
        have_tables = _existing_relations(conn, kind="table", names=required_tables)
        have_views = _existing_relations(conn, kind="view", names=required_views)
    except Exception as exc:
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        return AdmissionResult(
            DB_REACHABLE_SCHEMA_MISSING,
            f"{context}: schema probe failed at {host}: {type(exc).__name__}",
            kind,
            host,
            required_tables,
            required_views,
        )

    closer = getattr(conn, "close", None)
    if callable(closer):
        closer()

    missing_tables = tuple(name for name in required_tables if name not in have_tables)
    missing_views = tuple(name for name in required_views if name not in have_views)
    if missing_tables or missing_views:
        return AdmissionResult(
            DB_REACHABLE_SCHEMA_MISSING,
            f"{context}: required schema missing at {host}: tables={list(missing_tables)} views={list(missing_views)}",
            kind,
            host,
            missing_tables,
            missing_views,
        )
    return AdmissionResult(
        DB_READY,
        f"{context}: schema ready via {kind} at {host}",
        kind,
        host,
    )


def apply_admission(result: AdmissionResult, *, require_real: bool) -> AdmissionResult:
    """Skip or fail with the named state. Never hang. Never swallow MagicMock."""
    import pytest

    if result.state == DB_READY:
        if result.kind == "MagicMock":
            pytest.fail(f"{DB_UNAVAILABLE}: {result.reason}")
        return result
    message = f"{result.state}: {result.reason}"
    if require_real:
        pytest.fail(message)
    pytest.skip(message)
    raise AssertionError("unreachable")


def admit_ready_connection(
    *,
    dsn: str | None = None,
    required_tables: tuple[str, ...] = (),
    required_views: tuple[str, ...] = (),
    context: str = "real_db",
    timeout: int = CONNECT_TIMEOUT_SECONDS,
    opener: Any | None = None,
    require_real: bool | None = None,
) -> tuple[Any, str]:
    """Open a real driver connection after named preflight, or skip/fail.

    The returned connection is the opener's object. MagicMock is refused.
    Caller owns close().
    """
    required = require_real_db() if require_real is None else require_real
    target = dsn or canonical_dsn()
    classified = probe_database(
        target,
        timeout=timeout,
        opener=opener,
        required_tables=required_tables,
        required_views=required_views,
        context=context,
    )
    apply_admission(classified, require_real=required)

    connect = opener
    if connect is None:
        import psycopg2

        connect = psycopg2.connect
    try:
        conn = connect(target, connect_timeout=timeout)
    except TypeError:
        try:
            conn = connect(target, timeout=timeout)
        except TypeError:
            conn = connect(target)
    refuse_magic_mock_sql(conn, context=context)
    return conn, target


def admit_real_db_or_raise(
    *,
    real_db_marker: bool,
    require_real: bool | None = None,
    db_available: bool | None = None,
    opener: Any | None = None,
) -> Strategy:
    """Used by the pytest fixture. Skip/error happen before a mock is installed."""
    import pytest

    required = require_real_db() if require_real is None else require_real
    if real_db_marker and not required:
        # Optional mode: skip before any connect so collection stays fast.
        pytest.skip(
            f"{DB_UNAVAILABLE}: real_db test requires REQUIRE_REAL_DB=1 and the "
            "canonical DSN; refusing silent MagicMock (issue #285)"
        )
    classified: AdmissionResult | None = None
    if db_available is None:
        classified = probe_database(opener=opener, context="real_db")
        available = classified.state != DB_UNAVAILABLE and classified.kind != "MagicMock"
    else:
        available = db_available

    strategy = decide_connection_strategy(
        real_db_marker=real_db_marker,
        require_real=required,
        db_available=available,
    )
    if strategy == "skip":
        pytest.skip(
            f"{DB_UNAVAILABLE}: real_db test requires REQUIRE_REAL_DB=1 and the "
            "canonical DSN; refusing silent MagicMock (issue #285)"
        )
    if strategy == "config_error":
        host = dsn_host_for_logs(canonical_dsn())
        reason = classified.reason if classified is not None else f"canonical DSN not reachable at {host}"
        pytest.fail(f"{DB_UNAVAILABLE}: REQUIRE_REAL_DB=1 but {reason}")
    return strategy
