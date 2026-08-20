"""#341 — fail-closed preflight for national_intel PostgreSQL.

A reachable empty database is not a valid environment. Missing schema must
be reported as an explicit preflight result, never as UndefinedTable inside
a product test body. Connection probes use a short timeout so an absent
host cannot hang collection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from scripts.testing.real_db_guard import (
    DB_REACHABLE_SCHEMA_MISSING,
    DB_READY,
    DB_UNAVAILABLE,
    connection_kind,
)

CONNECT_TIMEOUT_SECONDS = 2
REQUIRED_TABLES: tuple[str, ...] = ("pncp_supplier_contracts",)
REQUIRED_VIEWS: tuple[str, ...] = (
    "v_intel_contracts_raw_national",
    "v_intel_contracts_geo_sc",
    "v_intel_supplier_geo",
    "v_intel_agency_profile",
)

Outcome = Literal["ready", "skip", "fail"]


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def explicit_dsn_provided() -> bool:
    """True when the caller named a DSN instead of relying on the 5436 default."""
    for key in ("NATIONAL_INTEL_DSN", "CAMPAIGN_TEST_DSN", "DATABASE_URL", "LOCAL_DATALAKE_DSN"):
        if os.environ.get(key, "").strip():
            return True
    return False


def resolve_probe_dsn() -> str:
    """Prefer an explicit runner DSN over the implicit campaign port 5436."""
    for key in ("NATIONAL_INTEL_DSN", "CAMPAIGN_TEST_DSN", "DATABASE_URL", "LOCAL_DATALAKE_DSN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc"


@dataclass(frozen=True)
class PreflightResult:
    outcome: Outcome
    reason: str
    dsn_host: str
    missing_tables: tuple[str, ...] = ()
    missing_views: tuple[str, ...] = ()
    state: str = ""

    @property
    def ready(self) -> bool:
        return self.outcome == "ready" and self.state == DB_READY


def _dsn_host(dsn: str) -> str:
    # Never return credentials. Host/port/db only for diagnostics.
    try:
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        host = parsed.hostname or "unknown"
        port = parsed.port
        db = (parsed.path or "").lstrip("/") or "unknown"
        if port:
            return f"{host}:{port}/{db}"
        return f"{host}/{db}"
    except Exception:
        return "unparsed"


def _connect(dsn: str, *, timeout: int = CONNECT_TIMEOUT_SECONDS) -> Any:
    try:
        import psycopg

        return psycopg.connect(dsn, connect_timeout=timeout)
    except ImportError:
        pass
    import psycopg2

    return psycopg2.connect(dsn, connect_timeout=timeout)


def _existing_relations(conn: Any, *, kind: str, names: tuple[str, ...]) -> set[str]:
    if not names:
        return set()
    table_type = "BASE TABLE" if kind == "table" else "VIEW"
    found: set[str] = set()
    sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = %s AND table_name = %s"
    )
    with conn.cursor() as cur:
        for name in names:
            cur.execute(sql, (table_type, name))
            row = cur.fetchone()
            if not row:
                continue
            if isinstance(row, dict):
                found.add(str(row.get("table_name")))
            else:
                found.add(str(row[0]))
    return found


def inspect_schema(conn: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return missing required tables and views. Never executes product SQL."""
    have_tables = _existing_relations(conn, kind="table", names=REQUIRED_TABLES)
    have_views = _existing_relations(conn, kind="view", names=REQUIRED_VIEWS)
    missing_tables = tuple(name for name in REQUIRED_TABLES if name not in have_tables)
    missing_views = tuple(name for name in REQUIRED_VIEWS if name not in have_views)
    return missing_tables, missing_views


def probe_national_intel(
    dsn: str | None = None,
    *,
    require_real: bool | None = None,
    timeout: int = CONNECT_TIMEOUT_SECONDS,
    opener: Any | None = None,
) -> PreflightResult:
    """Classify the DSN before any national_intel product test runs.

    Semantics (issue #341):
    - missing/unreachable DB → skip (optional) or fail if REQUIRE_REAL_DB=1
      and an explicit DSN was provided;
    - reachable DB without required schema → skip or fail with preflight
      reason, never UndefinedTable in the test body;
    - fully migrated DB → ready.
    """
    target = dsn or resolve_probe_dsn()
    host = _dsn_host(target)
    required = env_flag("REQUIRE_REAL_DB") if require_real is None else require_real
    explicit = explicit_dsn_provided() or dsn is not None
    connect = opener or _connect
    try:
        if opener is None:
            conn = connect(target, timeout=timeout)
        else:
            try:
                conn = opener(target, timeout=timeout)
            except TypeError:
                conn = opener(target)
    except Exception as exc:
        reason = f"national_intel preflight: database unreachable at {host}: {type(exc).__name__}"
        if required and explicit:
            return PreflightResult("fail", reason, host, state=DB_UNAVAILABLE)
        return PreflightResult("skip", reason, host, state=DB_UNAVAILABLE)

    if connection_kind(conn) == "MagicMock":
        reason = f"national_intel preflight: database unreachable at {host}: MagicMock"
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        if required and explicit:
            return PreflightResult("fail", reason, host, state=DB_UNAVAILABLE)
        return PreflightResult("skip", reason, host, state=DB_UNAVAILABLE)

    try:
        missing_tables, missing_views = inspect_schema(conn)
    except Exception as exc:
        reason = f"national_intel preflight: schema probe failed at {host}: {type(exc).__name__}"
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        if required and explicit:
            return PreflightResult("fail", reason, host, state=DB_REACHABLE_SCHEMA_MISSING)
        return PreflightResult("skip", reason, host, state=DB_REACHABLE_SCHEMA_MISSING)

    closer = getattr(conn, "close", None)
    if callable(closer):
        closer()

    if missing_tables or missing_views:
        reason = (
            "national_intel preflight: required schema missing at "
            f"{host}: tables={list(missing_tables)} views={list(missing_views)}"
        )
        if required and explicit:
            return PreflightResult(
                "fail",
                reason,
                host,
                missing_tables,
                missing_views,
                state=DB_REACHABLE_SCHEMA_MISSING,
            )
        return PreflightResult(
            "skip",
            reason,
            host,
            missing_tables,
            missing_views,
            state=DB_REACHABLE_SCHEMA_MISSING,
        )

    return PreflightResult(
        "ready",
        f"national_intel preflight: ready at {host}",
        host,
        missing_tables,
        missing_views,
        state=DB_READY,
    )


def admit_or_raise(result: PreflightResult) -> PreflightResult:
    """Translate a preflight result into pytest skip/fail before the test body."""
    import pytest

    if result.outcome == "ready" and result.state == DB_READY:
        return result
    message = f"{result.state or result.outcome}: {result.reason}"
    if result.outcome == "skip":
        pytest.skip(message)
    pytest.fail(message)
    raise AssertionError("unreachable")
