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

REPO = Path(__file__).resolve().parents[2]


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
    subprocess.check_call(cmd, cwd=REPO)


def apply_seeds(dsn: str) -> None:
    """Deterministic seeds required by entity_resolver / inventory tests."""
    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    env["LOCAL_DATALAKE_DSN"] = dsn
    for rel in (
        "db/seed/001_sc_entities.py",
        "db/seed/002_entity_aliases.py",
    ):
        path = REPO / rel
        if not path.is_file():
            print(f"WARNING: seed missing {rel}", flush=True)
            continue
        print(f"==> seed: {rel}", flush=True)
        subprocess.check_call([sys.executable, str(path)], cwd=REPO, env=env)


def run_pytest(extra: list[str]) -> int:
    env = os.environ.copy()
    # Real PG for integration/database tests; never use operator personal DSN defaults.
    env["REQUIRE_REAL_DB"] = "1"
    env["RESILIENCE_REQUIRE_DB"] = "1"
    env.setdefault("RESILIENCE_ENV", "test")
    env.setdefault("CI", "true")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-m",
        "",
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
        f"DATABASE_URL set={bool(env.get('DATABASE_URL'))}",
        flush=True,
    )
    return subprocess.call(cmd, cwd=REPO, env=env)


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
        "pytest_args",
        nargs="*",
        help="Extra args forwarded to pytest after the canonical flags",
    )
    args = parser.parse_args(argv)

    dsn = _dsn()
    os.environ.setdefault("DATABASE_URL", dsn)
    os.environ.setdefault("LOCAL_DATALAKE_DSN", dsn)

    if not args.skip_migrations:
        apply_all_migrations(dsn)
    if not args.skip_seeds:
        apply_seeds(dsn)

    return run_pytest(list(args.pytest_args))


if __name__ == "__main__":
    raise SystemExit(main())
