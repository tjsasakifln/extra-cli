"""Database fixtures for integration tests.

Requires a test PostgreSQL instance.  By default connects to
``postgresql://test:test@localhost:5433/extra_test`` (the docker-compose
service).  Override via ``TEST_DSN`` env var.

Usage::

    docker compose up -d test-db
    pytest -m integration
    docker compose down
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

_logger = logging.getLogger(__name__)

DEFAULT_TEST_DSN = "postgresql://test:test@localhost:5433/extra_test"
MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"


@pytest.fixture(scope="session")
def test_dsn() -> str:
    """Return the DSN for the test database."""
    return os.getenv("TEST_DSN", DEFAULT_TEST_DSN)


@pytest.fixture(scope="session")
def db_conn(test_dsn: str):
    """Session-scoped real PostgreSQL connection for integration tests.

    Applies migrations from ``db/migrations/`` on first connect.
    Skips the entire session if the database is unreachable.
    """
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")

    conn = None
    try:
        conn = psycopg2.connect(test_dsn)
        conn.autocommit = True

        # Apply migrations
        if MIGRATIONS_DIR.exists():
            _logger.info("Applying migrations from %s", MIGRATIONS_DIR)
            for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                try:
                    with open(sql_file) as f:
                        conn.cursor().execute(f.read())
                except Exception as exc:
                    _logger.warning(
                        "Migration %s failed (may already be applied): %s",
                        sql_file.name,
                        exc,
                    )
        else:
            _logger.warning("Migrations directory not found: %s", MIGRATIONS_DIR)

        yield conn

    except Exception as exc:
        pytest.skip(f"Test database not available: {exc}")
        yield None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@pytest.fixture(autouse=False)
def clean_bids(db_conn):
    """Clean up test data from pncp_raw_bids after each test.

    Only deletes rows where pncp_id starts with 'test_'.
    """
    if db_conn is None:
        return
    try:
        cur = db_conn.cursor()
        cur.execute("DELETE FROM pncp_raw_bids WHERE pncp_id LIKE 'test_%'")
        db_conn.commit()
        cur.close()
    except Exception as exc:
        _logger.warning("Failed to clean test bids: %s", exc)
