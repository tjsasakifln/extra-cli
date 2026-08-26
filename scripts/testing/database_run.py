"""Disposable PostgreSQL databases for deterministic test-suite runs.

The caller supplies a local PostgreSQL DSN with ``CREATEDB`` privilege.  This
module creates a sibling database with a generated name, verifies that it is
empty, and drops it after the run.  Administrative operations use psycopg2;
``psql`` is deliberately not a hidden runtime dependency.
"""

from __future__ import annotations

import importlib
import os
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

LOCAL_DATABASE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
REAL_DB_NAME_PREFIX = "extra_real_db_"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FORBIDDEN_DATABASE_MARKERS = ("prod", "production", "soak")


class DatabaseRunError(RuntimeError):
    """Fail-closed configuration or lifecycle error for a test database."""


def require_psycopg2(
    importer: Callable[[str], Any] = importlib.import_module,
) -> Any:
    """Return the required PostgreSQL driver or raise a named tooling error."""
    try:
        return importer("psycopg2")
    except (ImportError, ModuleNotFoundError) as exc:
        raise DatabaseRunError("REAL_DB_TOOLING_MISSING: psycopg2 is required; psql is not required") from exc


def validate_database_name(name: str, *, required_prefix: str | None = None) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(name):
        raise DatabaseRunError(f"REAL_DB_INVALID_DATABASE_NAME: {name!r}")
    lowered = name.lower()
    if lowered in {"postgres", "template0", "template1"} or any(
        marker in lowered for marker in _FORBIDDEN_DATABASE_MARKERS
    ):
        raise DatabaseRunError(f"REAL_DB_FORBIDDEN_DATABASE_NAME: {name!r}")
    if required_prefix and not name.startswith(required_prefix):
        raise DatabaseRunError(f"REAL_DB_UNSAFE_DATABASE_NAME: expected prefix {required_prefix!r}")
    return name


def validate_local_admin_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise DatabaseRunError("REAL_DB_INVALID_DSN: PostgreSQL URL required")
    host = parsed.hostname or ""
    if host not in LOCAL_DATABASE_HOSTS:
        raise DatabaseRunError(f"REAL_DB_ISOLATION_FAIL: local PostgreSQL required, got host={host or 'missing'}")
    database = (parsed.path or "").lstrip("/")
    if any(marker in database.lower() for marker in _FORBIDDEN_DATABASE_MARKERS):
        raise DatabaseRunError("REAL_DB_ISOLATION_FAIL: production/soak database refused")
    return dsn


def dsn_with_database(dsn: str, database: str) -> str:
    validate_database_name(database)
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=f"/{database}"))


def generated_database_name() -> str:
    return f"{REAL_DB_NAME_PREFIX}{os.getpid()}_{uuid.uuid4().hex[:10]}"


def assert_initially_empty(table_count: int, view_count: int) -> None:
    if table_count != 0 or view_count != 0:
        raise DatabaseRunError(
            f"REAL_DB_DIRTY_REUSE: newly created database is not empty (tables={table_count}, views={view_count})"
        )


def assert_generated_database_connection(conn: Any) -> str:
    """Refuse destructive test setup unless the connection is per-run isolated."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        database = str(cur.fetchone()[0])
    validate_database_name(database, required_prefix=REAL_DB_NAME_PREFIX)
    return database


def _admin_connection(admin_dsn: str, *, connector: Callable[..., Any] | None = None) -> Any:
    validate_local_admin_dsn(admin_dsn)
    connect = connector or require_psycopg2().connect
    parsed = urlparse(admin_dsn)
    postgres_dsn = urlunparse(parsed._replace(path="/postgres"))
    conn = connect(postgres_dsn, connect_timeout=5)
    conn.autocommit = True
    return conn


def create_database(
    admin_dsn: str,
    database: str,
    *,
    connector: Callable[..., Any] | None = None,
) -> str:
    """Create a local database and return its DSN; never reuse an existing DB."""
    validate_database_name(database)
    require_psycopg2()
    from psycopg2 import sql

    conn = _admin_connection(admin_dsn, connector=connector)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if cur.fetchone() is not None:
                raise DatabaseRunError(f"REAL_DB_DIRTY_REUSE: database already exists: {database}")
            cur.execute("SELECT current_user")
            owner = str(cur.fetchone()[0])
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database),
                    sql.Identifier(owner),
                )
            )
    finally:
        conn.close()
    target = dsn_with_database(admin_dsn, database)
    assert_database_empty(target, connector=connector)
    return target


def recreate_database(
    admin_dsn: str,
    database: str,
    *,
    connector: Callable[..., Any] | None = None,
) -> str:
    """Drop and recreate an explicitly confirmed local database."""
    validate_database_name(database)
    drop_database(admin_dsn, database, connector=connector, missing_ok=True)
    return create_database(admin_dsn, database, connector=connector)


def drop_database(
    admin_dsn: str,
    database: str,
    *,
    connector: Callable[..., Any] | None = None,
    missing_ok: bool = True,
) -> None:
    validate_database_name(database)
    require_psycopg2()
    from psycopg2 import sql

    conn = _admin_connection(admin_dsn, connector=connector)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            clause = "DROP DATABASE IF EXISTS {}" if missing_ok else "DROP DATABASE {}"
            cur.execute(sql.SQL(clause).format(sql.Identifier(database)))
    finally:
        conn.close()


def assert_database_empty(
    dsn: str,
    *,
    connector: Callable[..., Any] | None = None,
) -> None:
    connect = connector or require_psycopg2().connect
    conn = connect(dsn, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            table_count = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM information_schema.views WHERE table_schema = 'public'")
            view_count = int(cur.fetchone()[0])
    finally:
        conn.close()
    assert_initially_empty(table_count, view_count)


@dataclass(frozen=True)
class IsolatedDatabase:
    name: str
    dsn: str


@contextmanager
def isolated_database(admin_dsn: str) -> Iterator[IsolatedDatabase]:
    """Create and always tear down a generated database-per-run."""
    name = generated_database_name()
    validate_database_name(name, required_prefix=REAL_DB_NAME_PREFIX)
    dsn = create_database(admin_dsn, name)
    try:
        yield IsolatedDatabase(name=name, dsn=dsn)
    finally:
        drop_database(admin_dsn, name)
