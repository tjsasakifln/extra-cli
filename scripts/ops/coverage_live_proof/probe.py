"""Prove the connection is real PostgreSQL — never MagicMock, SQLite, or a proxy."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

from scripts.ops.coverage_live_proof.errors import FakeConnectionError, NotPostgresError


def is_fake_connection(conn: object) -> bool:
    """True for MagicMock, unittest.mock.Mock, or types whose name/module is a mock."""
    if isinstance(conn, (MagicMock, Mock)):
        return True
    module = type(conn).__module__.lower()
    name = type(conn).__name__.lower()
    if "unittest.mock" in module or module == "mock":
        return True
    if "magicmock" in name or name.endswith("mock") or "fake" in name:
        return True
    return False


def is_sqlite_connection(conn: object) -> bool:
    module = type(conn).__module__.lower()
    name = type(conn).__name__.lower()
    return "sqlite" in module or "sqlite" in name


def is_postgres_version(version_text: str) -> bool:
    return "postgresql" in (version_text or "").lower()


def connection_driver_name(conn: object) -> str:
    typ = type(conn)
    return f"{typ.__module__}.{typ.__name__}"


def assert_real_postgres(conn: object) -> dict[str, str]:
    """Query the server and refuse fakes / non-PostgreSQL.

    Returns postgres_version and driver type. Does not log the DSN.
    """
    if is_fake_connection(conn):
        raise FakeConnectionError("MagicMock/proxy refused as live proof")
    if is_sqlite_connection(conn):
        raise NotPostgresError("SQLite refused as live proof")

    execute = getattr(conn, "cursor", None)
    if not callable(execute):
        raise NotPostgresError("connection has no cursor(); not PostgreSQL")

    cur = conn.cursor()
    try:
        try:
            cur.execute("SELECT version(), current_setting('server_version')")
            row = cur.fetchone()
        except Exception as exc:
            raise NotPostgresError(f"version query failed: {exc}") from exc
        if not row:
            raise NotPostgresError("version query returned no row")
        version_text = str(row[0] or "")
        server_version = str(row[1] or "")
        if not is_postgres_version(version_text) and not is_postgres_version(server_version):
            raise NotPostgresError(
                f"server is not PostgreSQL: {version_text[:80] or type(conn).__name__}"
            )
        return {
            "postgres_version": version_text,
            "server_version": server_version,
            "driver": connection_driver_name(conn),
        }
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()


def connect_real(dsn: str, *, connect_timeout: int = 8) -> Any:
    """Open a real psycopg2 connection and refuse a mocked driver."""
    import psycopg2

    if is_fake_connection(psycopg2.connect):
        raise FakeConnectionError("psycopg2.connect is mocked; refusing live proof")
    conn = psycopg2.connect(dsn, connect_timeout=connect_timeout)
    if is_fake_connection(conn):
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        raise FakeConnectionError("psycopg2.connect returned MagicMock/proxy")
    return conn
