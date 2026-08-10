"""Postgres connection helpers for target-fit store (read-write)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


def connect(dsn: str, *, readonly: bool = False) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    if readonly:
        conn.set_session(readonly=True, autocommit=True)
    else:
        conn.autocommit = False
    return conn


@contextmanager
def transaction(dsn: str) -> Iterator[Any]:
    conn = connect(dsn, readonly=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
