"""Real-PostgreSQL preflight for national-claims persist/replay tests.

DSN absent → skip (or fail when REQUIRE_REAL_DB=1).
DSN present without schema → fail before any business SQL.
MagicMock is never a live database.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from urllib.parse import urlparse

from scripts.national_intel.preflight import Outcome
from scripts.testing.connection_policy import (
    canonical_dsn,
    connection_kind,
    dsn_is_required,
)

REQUIRED_TABLES: tuple[str, ...] = (
    "national_claims_universe",
    "national_claims_partition",
    "national_claims_aggregate_evidence",
    "national_claims_identity_evidence",
    "national_claims_decision",
    "national_claims_lkg",
)


def dsn_host(dsn: str) -> str:
    parsed = urlparse(dsn)
    host = parsed.hostname or "unknown"
    port = parsed.port
    database = (parsed.path or "").lstrip("/") or "unknown"
    if port:
        return f"{host}:{port}/{database}"
    return f"{host}/{database}"


def explicit_dsn_provided() -> bool:
    from os import environ

    return any(environ.get(key, "").strip() for key in ("LOCAL_DATALAKE_DSN", "DATABASE_URL", "NATIONAL_CLAIMS_DSN"))


def inspect_national_claims_schema(conn: Any) -> tuple[str, ...]:
    if isinstance(conn, MagicMock) or connection_kind(conn) == "MagicMock":
        raise RuntimeError("national_claims preflight refused MagicMock")
    missing: list[str] = []
    cursor = conn.cursor()
    try:
        for name in REQUIRED_TABLES:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s)",
                (name,),
            )
            row = cursor.fetchone()
            exists = bool(row[0] if row is not None else False)
            if not exists:
                missing.append(name)
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()
    return tuple(missing)


def probe_national_claims(
    dsn: str | None = None,
    *,
    require_real: bool | None = None,
    opener: Any | None = None,
) -> dict[str, Any]:
    from os import environ

    target = (
        dsn
        or environ.get("NATIONAL_CLAIMS_DSN")
        or environ.get("LOCAL_DATALAKE_DSN")
        or environ.get("DATABASE_URL")
        or canonical_dsn()
    )
    host = dsn_host(target)
    required = dsn_is_required() if require_real is None else require_real
    explicit = explicit_dsn_provided() or dsn is not None
    try:
        if opener is not None:
            try:
                conn = opener(target, connect_timeout=2)
            except TypeError:
                conn = opener(target)
        else:
            try:
                import psycopg2

                conn = psycopg2.connect(target, connect_timeout=2)
            except Exception as exc:
                outcome: Outcome = "fail" if required and explicit else "skip"
                return {
                    "outcome": outcome,
                    "reason": (f"national_claims preflight: database unreachable at {host}: {type(exc).__name__}"),
                    "dsn_host": host,
                    "missing_tables": (),
                }
    except Exception as exc:
        outcome = "fail" if required and explicit else "skip"
        return {
            "outcome": outcome,
            "reason": (f"national_claims preflight: database unreachable at {host}: {type(exc).__name__}"),
            "dsn_host": host,
            "missing_tables": (),
        }

    if isinstance(conn, MagicMock) or connection_kind(conn) == "MagicMock":
        outcome = "fail" if required else "skip"
        return {
            "outcome": outcome,
            "reason": f"national_claims preflight: MagicMock refused at {host}",
            "dsn_host": host,
            "missing_tables": REQUIRED_TABLES,
        }

    try:
        missing = inspect_national_claims_schema(conn)
    except Exception as exc:
        closer = getattr(conn, "close", None)
        if callable(closer):
            closer()
        return {
            "outcome": "fail" if required and explicit else "skip",
            "reason": (f"national_claims preflight: schema probe failed at {host}: {type(exc).__name__}"),
            "dsn_host": host,
            "missing_tables": REQUIRED_TABLES,
        }
    closer = getattr(conn, "close", None)
    if callable(closer):
        closer()
    if missing:
        return {
            "outcome": "fail",
            "reason": (f"national_claims preflight: required schema missing at {host}: tables={list(missing)}"),
            "dsn_host": host,
            "missing_tables": missing,
        }
    return {
        "outcome": "ready",
        "reason": f"national_claims preflight: ready at {host}",
        "dsn_host": host,
        "missing_tables": (),
    }


def admit_or_raise(result: dict[str, Any]) -> dict[str, Any]:
    import pytest

    if result["outcome"] == "ready":
        return result
    if result["outcome"] == "skip":
        pytest.skip(result["reason"])
    pytest.fail(result["reason"])
    raise AssertionError("unreachable")


def live_not_executed_payload(*, reason: str, smoke_command: str) -> dict[str, Any]:
    return {
        "LIVE_NOT_EXECUTED": True,
        "reason": reason,
        "live_smoke_command": smoke_command,
        "pii": False,
    }


def live_smoke_command() -> str:
    return (
        "export LOCAL_DATALAKE_DSN="
        '"${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}" && '
        'python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN" && '
        "python3 -m scripts.national_claims evaluate "
        "--input docs/contracts/national-claims/fixtures/needs-data.json "
        "--out reports/national_claims/live-smoke.json"
    )
