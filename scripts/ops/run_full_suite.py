#!/usr/bin/env python3
"""Canonical global pytest suite entrypoint (local + CI).

Semantics (non-negotiable for FULL_SUITE_EXECUTED claims):
- No implicit marker exclusion of ``slow`` (``-m ""`` + ``-o addopts=''``).
- Disposable PostgreSQL is assumed already reachable via DATABASE_URL /
  LOCAL_DATALAKE_DSN (caller provisions PG16).
- Applies **all** currently versioned migrations (no hard-coded max).
- Loads deterministic DB seeds required by integration tests.
- Sets REQUIRE_REAL_DB=1 and RESILIENCE_REQUIRE_DB=1 so tests/conftest
  does not mock psycopg2.connect.

Usage:
  export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5544/extra_full_suite
  export DATABASE_URL=$LOCAL_DATALAKE_DSN
  python -m scripts.ops.run_full_suite
  python -m scripts.ops.run_full_suite --skip-migrations --skip-seeds
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.ops.apply_migrations import file_checksum, list_migrations, version_key
from scripts.testing.database_run import (
    assert_generated_database_connection,
    isolated_database,
)
from scripts.testing.real_db_guard import connection_kind

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "db" / "migrations"
REQUIRED_SEEDS = (
    "db/seed/001_sc_entities.py",
    "db/seed/002_entity_aliases.py",
)
MIGRATION_INTERNAL_LEDGER_ENTRIES = {
    "021": ("coverage-2.4_entity_coverage_rebuild", "sha256=coverage-2-4-manual"),
}


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        print(
            "ERROR: DATABASE_URL or LOCAL_DATALAKE_DSN required for full suite",
            file=sys.stderr,
        )
        sys.exit(2)
    return dsn


def apply_all_migrations(dsn: str) -> None:
    """Apply every versioned migration under db/migrations (no max cap)."""
    cmd = [
        sys.executable,
        "-m",
        "scripts.ops.apply_migrations",
        "--dsn",
        dsn,
        "--mode",
        "fresh",
    ]
    print("==> migrations:", " ".join(cmd), flush=True)
    # Trusted argv: fixed sys.executable + module path from this repo.
    subprocess.check_call(cmd, cwd=REPO)  # noqa: S603


def apply_seeds(dsn: str) -> None:
    """Deterministic seeds required by entity_resolver / inventory tests."""
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    env["LOCAL_DATALAKE_DSN"] = dsn
    for rel in REQUIRED_SEEDS:
        path = REPO / rel
        if not path.is_file():
            raise FileNotFoundError(f"REAL_DB_SEED_MISSING: {rel}")
        print(f"==> seed: {rel}", flush=True)
        # Trusted argv: sys.executable + in-repo seed script path.
        subprocess.check_call(  # noqa: S603
            [sys.executable, str(path)], cwd=REPO, env=env
        )


def _expected_migration_ledger() -> dict[str, tuple[str, str]]:
    expected = {version_key(path): (path.name, file_checksum(path)) for path in list_migrations(MIGRATIONS)}
    expected.update(MIGRATION_INTERNAL_LEDGER_ENTRIES)
    return expected


def compare_migration_ledger(
    expected: dict[str, tuple[str, str]],
    actual: dict[str, tuple[str, str]],
) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    drifted = sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])
    if missing or extra or drifted:
        raise RuntimeError(f"REAL_DB_SCHEMA_DRIFT: missing={missing} extra={extra} drifted={drifted}")


def validate_real_db_contract(dsn: str) -> dict[str, Any]:
    """Fail closed on fake connection, migration drift, or missing suite seeds."""
    import psycopg2

    conn = psycopg2.connect(dsn, connect_timeout=5)
    kind = connection_kind(conn)
    if kind != "psycopg2":
        conn.close()
        raise RuntimeError(f"REAL_DB_FAKE_CONNECTION: expected psycopg2, got {kind}")
    try:
        database = assert_generated_database_connection(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT version, name, checksum FROM public._migrations")
            actual = {str(row[0]): (str(row[1]), str(row[2])) for row in cur.fetchall()}
            compare_migration_ledger(_expected_migration_ledger(), actual)
            cur.execute("SELECT count(*) FROM sc_public_entities")
            entity_count = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM entity_aliases WHERE is_active")
            alias_count = int(cur.fetchone()[0])
    finally:
        conn.close()
    if entity_count < 2085 or alias_count < 359:
        raise RuntimeError(f"REAL_DB_SEED_MISSING: sc_public_entities={entity_count} entity_aliases={alias_count}")
    return {
        "connection_kind": kind,
        "database": database,
        "migration_count": len(actual),
        "entity_count": entity_count,
        "alias_count": alias_count,
    }


def run_pytest(
    extra: list[str],
    *,
    marker: str = "",
    dsn: str | None = None,
    order: str = "normal",
) -> int:
    env = os.environ.copy()
    if dsn:
        for key in (
            "DATABASE_URL",
            "LOCAL_DATALAKE_DSN",
            "TEST_DSN",
            "NATIONAL_INTEL_DSN",
            "CAMPAIGN_TEST_DSN",
            "LINKAGE_TEST_DSN",
        ):
            env[key] = dsn
    # Real PG for integration/database tests; never use operator personal DSN defaults.
    env["REQUIRE_REAL_DB"] = "1"
    env["RESILIENCE_REQUIRE_DB"] = "1"
    env.setdefault("RESILIENCE_ENV", "test")
    env.setdefault("CI", "true")
    env["REAL_DB_TEST_ORDER"] = order
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-m",
        marker,
        "-o",
        "addopts=",
        "--cov=scripts",
        "--cov-report=term-missing",
        "--cov-fail-under=10",
        "-q",
        "--tb=short",
        *extra,
    ]
    print("==> pytest:", " ".join(cmd), flush=True)
    print(
        "==> env: REQUIRE_REAL_DB=1 RESILIENCE_REQUIRE_DB=1 "
        f"marker={marker or '<all>'} order={order} "
        f"DATABASE_URL set={bool(env.get('DATABASE_URL'))}",
        flush=True,
    )
    # Trusted argv: sys.executable + fixed pytest module path/flags.
    return subprocess.call(cmd, cwd=REPO, env=env)  # noqa: S603


def run_real_db_repeated(admin_dsn: str, *, repeat: int, extra: list[str]) -> int:
    """Run the complete real_db selection on a new database each time."""
    for index in range(repeat):
        order = "normal" if index == 0 else "reverse"
        with isolated_database(admin_dsn) as database:
            print(
                f"==> real_db run {index + 1}/{repeat}: database={database.name} order={order}",
                flush=True,
            )
            apply_all_migrations(database.dsn)
            apply_seeds(database.dsn)
            contract = validate_real_db_contract(database.dsn)
            print(f"==> real_db preflight: {contract}", flush=True)
            result = run_pytest(
                extra,
                marker="real_db",
                dsn=database.dsn,
                order=order,
            )
            if result != 0:
                return result
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Assume schema already applied on the target DSN",
    )
    parser.add_argument(
        "--skip-seeds",
        action="store_true",
        help="Skip sc_public_entities / entity_aliases seed scripts",
    )
    parser.add_argument(
        "--real-db-only",
        action="store_true",
        help="Run only -m real_db on a generated database-per-run",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of isolated real_db executions (run 2+ reverses collection order)",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra args forwarded to pytest after the canonical flags",
    )
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.repeat != 1 and not args.real_db_only:
        parser.error("--repeat is supported only with --real-db-only")

    dsn = _dsn()
    if args.real_db_only:
        if args.skip_migrations or args.skip_seeds:
            parser.error("--real-db-only is fail-closed; skip flags are not allowed")
        return run_real_db_repeated(dsn, repeat=args.repeat, extra=list(args.pytest_args))

    if args.skip_migrations or args.skip_seeds:
        # Diagnostic resume mode: the caller owns and names an already-isolated DB.
        os.environ.setdefault("DATABASE_URL", dsn)
        os.environ.setdefault("LOCAL_DATALAKE_DSN", dsn)
        if not args.skip_migrations:
            apply_all_migrations(dsn)
        if not args.skip_seeds:
            apply_seeds(dsn)
        return run_pytest(list(args.pytest_args), dsn=dsn)

    # Canonical full-suite runs also start empty. The supplied DSN is an admin
    # endpoint only; test code never receives or mutates that database.
    with isolated_database(dsn) as database:
        print(f"==> full-suite database={database.name}", flush=True)
        apply_all_migrations(database.dsn)
        apply_seeds(database.dsn)
        contract = validate_real_db_contract(database.dsn)
        print(f"==> full-suite preflight: {contract}", flush=True)
        return run_pytest(list(args.pytest_args), dsn=database.dsn)


if __name__ == "__main__":
    raise SystemExit(main())
