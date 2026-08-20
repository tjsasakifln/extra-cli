"""#343 — explicit mock vs real PostgreSQL policy for canonical tests.

A required real DSN is never silently replaced by MagicMock. Missing
database or schema fails or skips with a named preflight reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from scripts.testing.real_db_guard import (
    DB_UNAVAILABLE,
    canonical_dsn,
    connection_kind,
    dsn_host_for_logs,
    env_flag,
)

Strategy = Literal["real", "skip", "fail", "mock"]

CANONICAL_REAL_SUITES: frozenset[str] = frozenset(
    {
        "test_golden_path_concorrentes_report.py",
        "test_golden_path_valores_report.py",
        "test_golden_path_idempotency.py",
        "test_opportunity_integration.py",
    }
)

GOLDEN_PATH_TABLES: tuple[str, ...] = ("sc_public_entities",)
IDEMPOTENCY_TABLES: tuple[str, ...] = ("sc_public_entities", "pncp_raw_bids")
OPPORTUNITY_TABLES: tuple[str, ...] = (
    "opportunity_intel",
    "opportunity_runs",
    "opportunity_checkpoints",
    "opportunity_coverage",
)


def dsn_is_required() -> bool:
    return env_flag("REQUIRE_REAL_DB") or env_flag("REQUIRE_OPPORTUNITY_DB")


def refuse_silent_mock(conn: object, *, required: bool, context: str) -> str:
    """Reject a MagicMock when a real DSN is required. Returns the kind used."""
    kind = connection_kind(conn)
    if required and kind == "MagicMock":
        raise RuntimeError(f"{DB_UNAVAILABLE}: {context}: required real DSN was silently replaced by MagicMock")
    return kind


@dataclass(frozen=True)
class SchemaPreflight:
    ok: bool
    reason: str
    missing: tuple[str, ...]
    kind: str


def preflight_tables(conn: object, tables: tuple[str, ...], *, context: str) -> SchemaPreflight:
    """Probe information_schema. Never runs product report SQL."""
    kind = connection_kind(conn)
    if kind == "MagicMock":
        return SchemaPreflight(
            False,
            f"{DB_UNAVAILABLE}: {context}: preflight refused MagicMock (not a schema miss)",
            tables,
            kind,
        )
    if not tables:
        return SchemaPreflight(True, f"{context}: no required tables", (), kind)
    try:
        cursor = conn.cursor()  # type: ignore[union-attr]
    except Exception as exc:
        return SchemaPreflight(False, f"{context}: cursor failed: {type(exc).__name__}", tables, kind)
    missing: list[str] = []
    try:
        with cursor:
            for name in tables:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s)",
                    (name,),
                )
                row = cursor.fetchone()
                exists = bool(row[0] if row is not None else False)
                if not exists:
                    missing.append(name)
    except Exception as exc:
        return SchemaPreflight(
            False,
            f"{context}: schema probe failed: {type(exc).__name__}",
            tables,
            kind,
        )
    if missing:
        return SchemaPreflight(
            False,
            f"{context}: missing schema {missing}",
            tuple(missing),
            kind,
        )
    return SchemaPreflight(True, f"{context}: schema ready via {kind}", (), kind)


def decide_suite_strategy(
    *,
    filename: str,
    real_db_marker: bool,
    integration_marker: bool,
    require_real: bool,
    db_available: bool,
) -> Strategy:
    """Uniform admission for suites that consult PostgreSQL.

    real_db / the four canonical suites never fall through to MagicMock.
    """
    consults = real_db_marker or filename in CANONICAL_REAL_SUITES
    if consults:
        if require_real and db_available:
            return "real"
        if require_real and not db_available:
            return "fail"
        return "skip"
    if integration_marker and require_real:
        return "real" if db_available else "fail"
    return "mock"


def open_canonical_connection(
    *,
    dsn: str | None = None,
    required: bool | None = None,
    connect_timeout: int = 3,
    opener: Any | None = None,
) -> tuple[Any, str, str]:
    """Open the canonical DSN and name the connection that was actually used."""
    import pytest

    target = dsn or canonical_dsn()
    host = dsn_host_for_logs(target)
    must_be_real = dsn_is_required() if required is None else required
    connect = opener
    if connect is None:
        try:
            import psycopg2
        except ImportError as exc:
            if must_be_real:
                raise pytest.UsageError(f"{DB_UNAVAILABLE}: psycopg2 unavailable but real DSN required") from exc
            pytest.skip(f"{DB_UNAVAILABLE}: psycopg2 unavailable")
        connect = psycopg2.connect
    try:
        conn = connect(target, connect_timeout=connect_timeout)
    except TypeError:
        try:
            conn = connect(target)
        except Exception as exc:
            if must_be_real:
                raise pytest.UsageError(
                    f"{DB_UNAVAILABLE}: required DSN not reachable at {host}: {type(exc).__name__}"
                ) from exc
            pytest.skip(f"{DB_UNAVAILABLE}: database unreachable at {host}: {type(exc).__name__}")
    except Exception as exc:
        if must_be_real:
            raise pytest.UsageError(
                f"{DB_UNAVAILABLE}: required DSN not reachable at {host}: {type(exc).__name__}"
            ) from exc
        pytest.skip(f"{DB_UNAVAILABLE}: database unreachable at {host}: {type(exc).__name__}")
    kind = refuse_silent_mock(conn, required=must_be_real, context="open_canonical_connection")
    return conn, kind, target
