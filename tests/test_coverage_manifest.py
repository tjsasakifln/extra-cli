"""Tests for coverage manifest — Story 1.5.

Tests cover:
    - CoverageManifestEntry creation and defaults
    - CoverageManifest aggregation
    - to_dict() serialization
    - to_markdown() rendering
    - build_manifest_from_db with mock connection
    - Warning generation
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from scripts.coverage.manifest import (
    CoverageManifest,
    CoverageManifestEntry,
    build_manifest_from_db,
)


class TestCoverageManifestEntry:
    def test_default_values(self):
        entry = CoverageManifestEntry(capability="open_tenders", source="pncp")
        assert entry.total_pairs == 0
        assert entry.covered_pairs == 0
        assert entry.pct_covered == 0.0
        assert entry.with_data == 0
        assert entry.zero_data == 0

    def test_custom_values(self):
        entry = CoverageManifestEntry(
            capability="open_tenders",
            source="pncp",
            total_pairs=100,
            covered_pairs=80,
            pct_covered=80.0,
            with_data=60,
            zero_data=20,
        )
        assert entry.total_pairs == 100
        assert entry.pct_covered == 80.0


class TestCoverageManifest:
    def test_empty_manifest(self):
        manifest = CoverageManifest()
        assert manifest.total_capabilities == 0
        assert manifest.total_sources == 0
        assert len(manifest.entries) == 0

    def test_single_entry(self):
        manifest = CoverageManifest()
        entry = CoverageManifestEntry(
            capability="open_tenders",
            source="pncp",
            total_pairs=100,
            covered_pairs=95,
            pct_covered=95.0,
        )
        manifest.entries.append(entry)
        manifest.total_capabilities = 1
        manifest.total_sources = 1
        assert len(manifest.entries) == 1

    def test_to_dict(self):
        manifest = CoverageManifest()
        entry = CoverageManifestEntry(
            capability="open_tenders",
            source="pncp",
            total_pairs=100,
            covered_pairs=95,
            pct_covered=95.0,
            with_data=80,
            zero_data=15,
            partial=3,
            blocked=1,
            errored=1,
        )
        manifest.entries.append(entry)
        manifest.total_capabilities = 1
        manifest.total_sources = 1

        result = manifest.to_dict()
        assert result["total_capabilities"] == 1
        assert len(result["entries"]) == 1
        assert result["entries"][0]["pct_covered"] == 95.0
        assert result["entries"][0]["breakdown"]["with_data"] == 80
        assert result["entries"][0]["breakdown"]["zero_data"] == 15

    def test_to_markdown(self):
        manifest = CoverageManifest()
        entry = CoverageManifestEntry(
            capability="open_tenders",
            source="pncp",
            total_pairs=100,
            covered_pairs=95,
            pct_covered=95.0,
        )
        manifest.entries.append(entry)
        manifest.total_capabilities = 1
        manifest.total_sources = 1

        md = manifest.to_markdown()
        assert "# Coverage Manifest" in md
        assert "open_tenders" in md
        assert "pncp" in md
        assert "95.0%" in md

    def test_generated_at_timestamp(self):
        manifest = CoverageManifest()
        assert manifest.generated_at is not None
        assert isinstance(manifest.generated_at, datetime)


class TestBuildManifestFromDb:
    def test_view_not_exists(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = [False]  # view doesn't exist

        manifest = build_manifest_from_db(conn)
        assert len(manifest.blockers) == 1
        assert "Apply migration 040" in manifest.blockers[0]["recommended_action"]

    def test_empty_view(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value

        # First query: view exists
        cursor.fetchone.side_effect = [
            [True],   # view exists
        ]
        # Second query: no rows
        cursor.fetchall.return_value = []

        manifest = build_manifest_from_db(conn)
        assert len(manifest.entries) == 0

    def test_with_data(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value

        # First query: view exists
        cursor.fetchone.side_effect = [
            [True],  # view exists
        ]

        # Mock column names
        cursor.description = [
            ("capability", None, None, None, None, None, None),
            ("source", None, None, None, None, None, None),
            ("total_entity_pairs", None, None, None, None, None, None),
            ("covered_pairs", None, None, None, None, None, None),
            ("pct_covered", None, None, None, None, None, None),
            ("with_data", None, None, None, None, None, None),
            ("zero_data", None, None, None, None, None, None),
            ("partial", None, None, None, None, None, None),
            ("in_progress", None, None, None, None, None, None),
            ("blocked", None, None, None, None, None, None),
            ("stale", None, None, None, None, None, None),
            ("errored", None, None, None, None, None, None),
            ("last_check_at", None, None, None, None, None, None),
        ]
        cursor.fetchall.return_value = [
            ("open_tenders", "pncp", 100, 90, 90.0, 80, 10, 5, 0, 2, 1, 2, None),
        ]

        manifest = build_manifest_from_db(conn)
        assert len(manifest.entries) == 1
        assert manifest.entries[0].capability == "open_tenders"
        assert manifest.entries[0].pct_covered == 90.0
        assert manifest.entries[0].with_data == 80
        assert manifest.entries[0].blocked == 2
