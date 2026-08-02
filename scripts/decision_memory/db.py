"""PostgreSQL helpers for decision memory."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_DSN = "postgresql://test:test@127.0.0.1:5433/extra_test"


def get_dsn(explicit: str | None = None) -> str:
    return explicit or os.getenv("LOCAL_DATALAKE_DSN") or DEFAULT_DSN


def connect(dsn: str | None = None) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    target = get_dsn(dsn)
    return psycopg2.connect(target, cursor_factory=RealDictCursor)


def require_client_id(client_id: str | None) -> str:
    if not client_id or not str(client_id).strip():
        raise ValueError("client_id is required; silent default to 'extra' is forbidden")
    return str(client_id).strip()
