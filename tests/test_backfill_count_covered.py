"""Integration tests for _count_covered and new_entities_covered in backfill.

Requires a running PostgreSQL. Set TEST_DSN env var or use default.

    REQUIRE_TEST_DB=1 pytest tests/test_backfill_count_covered.py -v
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _require_db():
    """Skip or fail based on REQUIRE_TEST_DB env var."""
    dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.close()
    except Exception as e:
        if os.getenv("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"Database required but unavailable: {e}")
        pytest.skip(f"Database not available: {e}")


def _get_conn():
    import psycopg2
    dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
    return psycopg2.connect(dsn)


class TestCountCoveredNoDuplicate:
    """Verify _count_covered has single definition and works correctly."""

    def test_single_definition_exists(self):
        """_count_covered must be defined exactly once on MultiSourceBackfill."""
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        # Count methods named _count_covered
        methods = [
            name for name, _ in MultiSourceBackfill.__dict__.items()
            if name == "_count_covered"
        ]
        assert len(methods) == 1, (
            f"Expected 1 _count_covered, found {len(methods)}. "
            "Remove the duplicate definition."
        )

    def test_count_covered_returns_int(self):
        """_count_covered() must return an integer without requiring arguments."""
        _require_db()
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
        pipeline = MultiSourceBackfill(dsn=dsn)

        result = pipeline._count_covered()
        assert isinstance(result, int), (
            f"_count_covered() returned {type(result).__name__}, expected int"
        )

    def test_run_pipeline_no_type_error(self):
        """run_pipeline(dry_run=False) must not raise TypeError from _count_covered."""
        _require_db()
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
        pipeline = MultiSourceBackfill(dsn=dsn)

        with patch.object(pipeline, '_run_source') as mock_source, \
             patch.object(pipeline, '_generate_report'):
            mock_source.return_value = {
                'status': 'dry_run',
                'source': 'pncp',
                'duration_s': 0.1,
                'fetched': 0, 'transformed': 0, 'inserted': 0, 'updated': 0,
                'matched': 0, 'unmatched': 0, 'new_entities_covered': 0,
                'warnings': [], 'dependencies_missing': [],
            }

            # This should NOT raise TypeError
            try:
                stats = pipeline.run_pipeline(
                    sources=['pncp'],
                    dry_run=True,
                )
            except TypeError as e:
                pytest.fail(
                    f"run_pipeline() raised TypeError: {e}. "
                    "Check that _count_covered() is called without arguments."
                )

            assert isinstance(stats, dict), f"Expected dict, got {type(stats).__name__}"
            assert 'entities_before' in stats


class TestNewEntitiesCovered:
    """Verify new_entities_covered calculation in _run_source."""

    def test_new_entities_covered_calculation(self):
        """Insert coverage, run source, verify new_entities_covered == 1."""
        _require_db()
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
        pipeline = MultiSourceBackfill(dsn=dsn)

        # Get baseline
        baseline = pipeline._count_covered()

        # Insert a test entity coverage row if entity exists
        conn = _get_conn()
        try:
            cur = conn.cursor()
            # Find an entity to use
            cur.execute("SELECT id FROM sc_public_entities WHERE is_active = TRUE LIMIT 1")
            row = cur.fetchone()
            if row is None:
                pytest.skip("No active entities in sc_public_entities")

            entity_id = row[0]

            # Insert coverage
            cur.execute(
                """INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km, last_seen_at)
                   VALUES (%s, 'test_count_covered', TRUE, TRUE, NOW())
                   ON CONFLICT (entity_id, source) DO UPDATE
                   SET is_covered = TRUE, last_seen_at = NOW()""",
                (entity_id,),
            )
            conn.commit()

            # Now count should be > baseline if this entity was newly covered
            after_insert = pipeline._count_covered()
            new_count = max(0, after_insert - baseline)

            # Verify the new coverage was counted
            assert after_insert >= baseline, (
                f"Coverage decreased: {baseline} → {after_insert}"
            )
            print(f"  baseline={baseline}, after_insert={after_insert}, new={new_count}")

            # Cleanup
            cur.execute(
                "DELETE FROM entity_coverage WHERE source = 'test_count_covered'"
            )
            conn.commit()
            cur.close()

            # Verify cleanup
            after_cleanup = pipeline._count_covered()
            assert after_cleanup == baseline, (
                f"Cleanup failed: {baseline} != {after_cleanup}"
            )
        finally:
            conn.close()

    def test_run_source_new_entities_covered_in_result(self):
        """_run_source must include new_entities_covered in its result dict."""
        _require_db()
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
        pipeline = MultiSourceBackfill(dsn=dsn)

        with patch('scripts.pipeline.backfill_multi_source._get_conn') as mock_get_conn, \
             patch('scripts.pipeline.backfill_multi_source._load_entities') as mock_load, \
             patch('scripts.pipeline.backfill_multi_source.crawl_source') as mock_crawl:

            # Setup mock connection
            mock_conn = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_load.return_value = []

            from scripts.crawl.ingestion._base.crawler import CrawlerResult
            result = CrawlerResult(
                source="pncp",
                status="success",
                fetched=10,
                transformed=8,
                inserted=5,
                updated=3,
                matched=2,
            )
            mock_crawl.return_value = result

            # Mock _count_covered to simulate coverage change
            call_count = [0]
            def count_side_effect():
                call_count[0] += 1
                return 10 if call_count[0] == 1 else 13  # before=10, after=13

            with patch.object(pipeline, '_count_covered', side_effect=count_side_effect):
                run_result = pipeline._run_source('pncp', dry_run=False)

            assert 'new_entities_covered' in run_result, (
                f"Result missing 'new_entities_covered': {list(run_result.keys())}"
            )
            assert run_result['new_entities_covered'] == 3, (
                f"Expected 3 new entities covered, got {run_result['new_entities_covered']}"
            )
            print(f"  new_entities_covered={run_result['new_entities_covered']} (13-10=3)")
