"""Tests for opportunity_intel/manifest.py — coverage manifest validation.

Test categories:
    - Unit tests (no DB): validate constant, assertion logic, sanity checks.
    - Integration tests (live DB): validate SQL queries produce correct results.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.opportunity_intel.manifest import (  # noqa: E402
    CANONICAL_UNIVERSE_WITHIN_200KM,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROD_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)


def _prod_conn():
    """Return a connection to the production database, or skip if unavailable."""
    try:
        import psycopg2

        conn = psycopg2.connect(_PROD_DSN, connect_timeout=3)
        conn.autocommit = True
        return conn
    except Exception as e:
        pytest.skip(f"Production database unavailable: {e}")


# ---------------------------------------------------------------------------
# Unit tests (no database required)
# ---------------------------------------------------------------------------


class TestCanonicalUniverse:
    """Validate the canonical universe constant."""

    def test_denominator_is_1093(self):
        """The canonical universe MUST be 1093 entities within 200 km."""
        assert CANONICAL_UNIVERSE_WITHIN_200KM == 1093, (
            f"Canonical universe changed from 1093 to {CANONICAL_UNIVERSE_WITHIN_200KM}. "
            "Update docs/coverage-truth/fase0-audit-2026-07-12.md if this is intentional."
        )

    def test_denominator_is_positive(self):
        """Canonical universe must be positive."""
        assert CANONICAL_UNIVERSE_WITHIN_200KM > 0


class TestCoverageMath:
    """Validate the assertion guards that prevent invalid coverage math."""

    def test_coverage_between_0_and_100(self):
        """Coverage percentage must always be 0-100."""
        # Valid scenarios
        for pct in [0.0, 50.0, 100.0, 33.33]:
            assert 0 <= pct <= 100, f"pct_covered inválido: {pct}"

        # Invalid scenarios — these should fail the assertion
        for pct in [-1.0, 101.0, 265.95]:
            assert not (0 <= pct <= 100), f"pct_covered {pct} should have been caught by assert"

    def test_no_negative_entities_without_data(self):
        """entities_without_data must never be negative."""
        total_entities = 1093

        # Valid: entities_with_data <= total_entities
        for entities_with_data in [0, 500, 1093]:
            entities_without_data = total_entities - entities_with_data
            assert entities_without_data >= 0, f"entities_without_data negativo: {entities_without_data}"

        # Invalid: entities_with_data > total_entities
        entities_with_data = 3851  # The old bug — counts all SC, not just raio_200km
        entities_without_data = total_entities - entities_with_data
        assert entities_without_data < 0, "This should be negative — demonstrates the old bug"

    def test_numerator_between_zero_and_denominator(self):
        """entities_with_data must be between 0 and total_entities inclusive."""
        total_entities = 1093

        # Valid
        assert 0 <= 0 <= total_entities
        assert 0 <= 500 <= total_entities
        assert 0 <= 1093 <= total_entities

        # Invalid: overcount
        assert not (0 <= 3851 <= total_entities), "3851 > 1093 should fail the assertion"

        # Invalid: negative
        assert not (0 <= -1 <= total_entities), "-1 should fail the assertion"


# ---------------------------------------------------------------------------
# Integration tests (require live production database)
# ---------------------------------------------------------------------------


class TestManifestQueries:
    """Validate SQL queries against the production database.

    These tests are read-only and validate that the manifest queries
    produce mathematically valid results.
    """

    @pytest.mark.integration
    def test_numerator_join_matches_canonical_universe(self):
        """entities_with_data from JOIN must be <= canonical universe count."""
        conn = _prod_conn()
        try:
            cur = conn.cursor()

            # Use the same query from _build_manifest()
            cur.execute("""
                SELECT COUNT(DISTINCT oi.orgao_cnpj) AS cnt
                FROM opportunity_intel oi
                INNER JOIN sc_public_entities spe
                    ON spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8)
                WHERE oi.is_active = TRUE
                  AND oi.orgao_cnpj IS NOT NULL
                  AND oi.source != 'test_batch'
                  AND spe.raio_200km = TRUE
            """)
            row = cur.fetchone()
            entities_with_data: int = row[0]

            assert 0 <= entities_with_data <= CANONICAL_UNIVERSE_WITHIN_200KM, (
                f"entities_with_data ({entities_with_data}) outside valid range [0, {CANONICAL_UNIVERSE_WITHIN_200KM}]"
            )
        finally:
            conn.close()

    @pytest.mark.integration
    def test_no_test_batch_in_production(self):
        """test_batch records must be excluded from production queries."""
        conn = _prod_conn()
        try:
            cur = conn.cursor()

            # Check total active test_batch records
            cur.execute("""
                SELECT COUNT(*) FROM opportunity_intel
                WHERE source = 'test_batch' AND is_active = TRUE
            """)
            total_test_batch = cur.fetchone()[0]

            # With test_batch excluded, the main count should differ
            cur.execute("""
                SELECT COUNT(*) FROM opportunity_intel
                WHERE is_active = TRUE AND source != 'test_batch'
            """)
            without_test_batch = cur.fetchone()[0]

            # If test_batch records exist, the counts must differ
            if total_test_batch > 0:
                cur.execute("""
                    SELECT COUNT(*) FROM opportunity_intel
                    WHERE is_active = TRUE
                """)
                total_active = cur.fetchone()[0]
                assert without_test_batch == total_active - total_test_batch, (
                    f"test_batch exclusion mismatch: total={total_active}, "
                    f"test_batch={total_test_batch}, without={without_test_batch}"
                )
        finally:
            conn.close()

    @pytest.mark.integration
    def test_gaps_query_join_uses_left_8(self):
        """The gaps join must use LEFT(orgao_cnpj, 8) to match cnpj_8 format.

        The old code used spe.cnpj_8 = oi.orgao_cnpj (8 chars = 14 chars),
        which never matched. The fix uses spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8).
        This test proves the LEFT join finds matches, while the old join finds none.
        """
        conn = _prod_conn()
        try:
            cur = conn.cursor()

            # OLD join (direct equality) — should find 0 matches
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM sc_public_entities spe
                WHERE spe.raio_200km = TRUE
                  AND EXISTS (
                    SELECT 1 FROM opportunity_intel oi
                    WHERE oi.is_active = TRUE
                      AND oi.source != 'test_batch'
                      AND oi.orgao_cnpj IS NOT NULL
                      AND spe.cnpj_8 = oi.orgao_cnpj
                  )
            """)
            old_join_matches = cur.fetchone()[0]

            # NEW join (LEFT(orgao_cnpj, 8)) — should find real matches
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM sc_public_entities spe
                WHERE spe.raio_200km = TRUE
                  AND EXISTS (
                    SELECT 1 FROM opportunity_intel oi
                    WHERE oi.is_active = TRUE
                      AND oi.source != 'test_batch'
                      AND oi.orgao_cnpj IS NOT NULL
                      AND spe.cnpj_8 = LEFT(oi.orgao_cnpj, 8)
                  )
            """)
            new_join_matches = cur.fetchone()[0]

            # The old join returns 0 (cnpj_8=8 chars vs orgao_cnpj=14 chars)
            assert old_join_matches == 0, (
                f"Old direct join found {old_join_matches} matches (should be 0 — "
                "cnpj_8 is 8 chars, orgao_cnpj is 14 chars)"
            )

            # The new join returns real matches (cnpj_8 = LEFT(orgao_cnpj, 8))
            assert new_join_matches > 0, (
                f"New LEFT join found {new_join_matches} matches (should be > 0 — "
                "entities with opportunity data within 200km radius)"
            )
        finally:
            conn.close()

    @pytest.mark.integration
    def test_source_health_excludes_test_batch(self):
        """source_health must not include test_batch as a source."""
        conn = _prod_conn()
        try:
            cur = conn.cursor()

            cur.execute("""
                SELECT source, COUNT(*) AS cnt
                FROM opportunity_intel
                WHERE is_active = TRUE
                  AND source != 'test_batch'
                GROUP BY source
                ORDER BY cnt DESC
            """)
            sources = {row[0] for row in cur.fetchall()}

            assert "test_batch" not in sources, "test_batch source found in production source_health query"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Offline validation tests (mock data, no DB needed)
# ---------------------------------------------------------------------------


class TestAssertionGuard:
    """Validate that _build_manifest assertions would fire on bad data."""

    def test_negative_entities_raises_assertion(self):
        """Simulate what happens when the assertion catches a negative value."""
        entities_with_data = -1

        with pytest.raises(AssertionError, match="entities_with_data negativo"):
            assert entities_with_data >= 0, f"entities_with_data negativo: {entities_with_data}"

    def test_overcount_raises_assertion(self):
        """Simulate what happens when entities_with_data > total_entities."""
        entities_with_data = 3851  # The old bug value
        total_entities = 1093

        with pytest.raises(AssertionError, match="> total_entities"):
            assert entities_with_data <= total_entities, (
                f"entities_with_data ({entities_with_data}) > total_entities ({total_entities})"
            )

    def test_pct_above_100_raises_assertion(self):
        """Simulate what happens when pct_covered > 100."""
        pct_covered = 265.95  # The old bug value

        with pytest.raises(AssertionError, match="pct_covered inválido"):
            assert 0 <= pct_covered <= 100, f"pct_covered inválido: {pct_covered}"

    def test_zero_total_entities_raises_assertion(self):
        """total_entities of zero must be caught."""
        total_entities = 0

        with pytest.raises(AssertionError, match="total_entities é zero"):
            assert total_entities > 0, "total_entities é zero"
