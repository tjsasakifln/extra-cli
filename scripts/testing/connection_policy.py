"""#343 — explicit mock vs real PostgreSQL policy for canonical tests.

A required real DSN is never silently replaced by MagicMock. Missing
database or schema fails or skips with a named preflight reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal
from unittest.mock import MagicMock

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
OPPORTUNITY_TABLES: tuple[str, ...] = (
    "opportunity_intel",
    "opportunity_runs",
    "opportunity_checkpoints",
    "opportunity_coverage",
)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def canonical_dsn() -> str:
    return (
        os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
        or "postgresql://test:test@127.0.0.1:5433/extra_test"
    )


def dsn_is_required() -> bool:
    return env_flag("REQUIRE_REAL_DB") or env_flag("REQUIRE_OPPORTUNITY_DB")


def connection_kind(conn: object) -> str:
    """Name the live connection type. MagicMock is never reported as PostgreSQL."""
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


def refuse_silent_mock(conn: object, *, required: bool, context: str) -> str:
    """Reject a MagicMock when a real DSN is required. Returns the kind used."""
    kind = connection_kind(conn)
    if required and kind == "MagicMock":
        raise RuntimeError(
            f"{context}: required real DSN was silently replaced by MagicMock "
            f"(dsn={canonical_dsn()!r})"
        )
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
            f"{context}: preflight refused MagicMock (not a schema miss)",
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
    must_be_real = dsn_is_required() if required is None else required
    connect = opener
    if connect is None:
        try:
            import psycopg2
        except ImportError as exc:
            if must_be_real:
                raise pytest.UsageError(f"psycopg2 unavailable but real DSN required: {exc}") from exc
            pytest.skip(f"psycopg2 unavailable: {exc}")
        connect = psycopg2.connect
    try:
        conn = connect(target, connect_timeout=connect_timeout)
    except TypeError:
        try:
            conn = connect(target)
        except Exception as exc:
            if must_be_real:
                raise pytest.UsageError(
                    f"required DSN not reachable ({target!r}): {type(exc).__name__}"
                ) from exc
            pytest.skip(f"database unreachable: {exc}")
    except Exception as exc:
        if must_be_real:
            raise pytest.UsageError(
                f"required DSN not reachable ({target!r}): {type(exc).__name__}"
            ) from exc
        pytest.skip(f"database unreachable: {exc}")
    kind = refuse_silent_mock(conn, required=must_be_real, context="open_canonical_connection")
    return conn, kind, target
