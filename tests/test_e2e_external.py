"""Live E2E tests for the PNCP engineering pipeline.

These tests exercise the real external PNCP API through the public monitor
entrypoint and verify persistence in ``pncp_raw_bids`` and
``engineering_opportunities`` without manually creating ``ingestion_runs``.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.integration, pytest.mark.slow]


def _get_dsn() -> str:
    return os.getenv("TEST_DSN", "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")


def _require_db() -> None:
    cmd = ["psql", _get_dsn(), "-c", "select 1"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return
    if os.getenv("REQUIRE_TEST_DB") == "1":
        pytest.fail(f"Database required but unavailable: {result.stderr or result.stdout}")
    pytest.skip(f"Database not available: {result.stderr or result.stdout}")


class TestPNCPLivePipeline:
    """Real PNCP -> FetchResult -> transform -> DB -> engineering pipeline."""

    def test_monitor_crawl_source_persists_engineering_pipeline(self):
        if os.getenv("RUN_EXTERNAL_E2E") != "1":
            pytest.skip("Set RUN_EXTERNAL_E2E=1 to call PNCP and mutate an isolated test DB")
        _require_db()

        started_window = date(2026, 5, 14).isoformat()
        ended_window = date(2026, 5, 15).isoformat()
        crawl_cmd = [
            "python3",
            "scripts/crawl/monitor.py",
            "--source",
            "pncp",
            "--mode",
            "backfill",
            "--date-from",
            started_window,
            "--date-to",
            ended_window,
            "--target",
            "engineering",
            "--limit",
            "20",
            "--engineering-only",
        ]
        crawl = subprocess.run(crawl_cmd, capture_output=True, text=True, check=False)
        assert crawl.returncode == 0, crawl.stderr or crawl.stdout
        assert "success" in crawl.stdout
        assert "Engineering: classified=" in crawl.stdout

        run_sql = (
            "SELECT id, status, total_fetched, inserted, updated "
            "FROM ingestion_runs WHERE source = 'pncp' ORDER BY id DESC LIMIT 1"
        )
        run_q = subprocess.run(
            ["psql", _get_dsn(), "-At", "-c", run_sql],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run_q.returncode == 0, run_q.stderr or run_q.stdout
        run_parts = run_q.stdout.strip().split("|")
        assert len(run_parts) == 5
        assert run_parts[1] == "completed"
        assert int(run_parts[2]) > 0

        checks = {
            "raw_count": (
                "SELECT COUNT(*) FROM pncp_raw_bids "
                "WHERE source = 'pncp' "
                "AND data_publicacao::date BETWEEN DATE '2026-05-14' AND DATE '2026-05-15'"
            ),
            "classified_count": (
                "SELECT COUNT(*) FROM engineering_opportunities "
                "WHERE source = 'pncp' "
                "AND data_publicacao::date BETWEEN DATE '2026-05-14' AND DATE '2026-05-15' "
                "AND engineering_score >= 40"
            ),
            "within_radius": (
                "SELECT COUNT(*) FROM engineering_opportunities "
                "WHERE source = 'pncp' "
                "AND data_publicacao::date BETWEEN DATE '2026-05-14' AND DATE '2026-05-15' "
                "AND within_200km = TRUE"
            ),
            "joined_count": (
                "SELECT COUNT(*) FROM engineering_opportunities eo "
                "JOIN pncp_raw_bids rb ON rb.pncp_id = eo.pncp_id "
                "WHERE eo.source = 'pncp' "
                "AND eo.data_publicacao::date BETWEEN DATE '2026-05-14' AND DATE '2026-05-15'"
            ),
        }
        for sql in checks.values():
            query = subprocess.run(
                ["psql", _get_dsn(), "-At", "-c", sql],
                capture_output=True,
                text=True,
                check=False,
            )
            assert query.returncode == 0, query.stderr or query.stdout
            assert int(query.stdout.strip()) > 0
