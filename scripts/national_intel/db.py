"""Minimal DB helper for national_intel (isolated DSN preferred)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def resolve_dsn(explicit: str | None = None) -> str:
    dsn = explicit or os.environ.get("NATIONAL_INTEL_DSN") or os.environ.get("LOCAL_DATALAKE_DSN")
    if not dsn:
        raise SystemExit(
            "DSN required: set NATIONAL_INTEL_DSN (preferred, port 5435) "
            "or pass --dsn. Do not point at HC writer DB during live backfill."
        )
    # Soft guard: warn if classic HC port appears
    if ":5433/" in dsn or dsn.rstrip("/").endswith(":5433"):
        # allow explicit override for read-only inventory but print warning to stderr
        import sys

        print(
            "WARNING: DSN uses port 5433 (HC backfill DB). "
            "national_intel is read-only SQL but prefer 5435 isolated DB.",
            file=sys.stderr,
        )
    return dsn


@contextmanager
def connect(dsn: str) -> Iterator[Any]:
    try:
        import psycopg

        conn = psycopg.connect(dsn)
        try:
            yield conn
        finally:
            conn.close()
        return
    except ImportError:
        pass
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(conn: Any, sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        # Avoid treating bare "%" in SQL (e.g. LIKE 'v_%') as pyformat placeholders
        # when no params are intended.
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if hasattr(r, "keys"):
            out.append(dict(r))
        else:
            out.append(dict(zip(cols, r, strict=False)))
    return out
