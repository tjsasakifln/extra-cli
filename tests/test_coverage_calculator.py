"""Unit tests for scripts/coverage/calculator.py.

Tests cover the report_coverage and print_coverage_report functions
using mocked database connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.coverage.calculator import print_coverage_report, report_coverage

# ---------------------------------------------------------------------------
# report_coverage
# ---------------------------------------------------------------------------


def _make_mock_conn(
    groups: list[tuple],
    by_source: list[tuple],
    uncovered: list[tuple],
) -> MagicMock:
    """Create a mock connection with three pre-defined query results.

    Args:
        groups: Rows for the groups query (raio, total, covered, uncovered).
        by_source: Rows for the by_source query (source, count, covered).
        uncovered: Rows for uncovered entities query
            (razao_social, cnpj_8, municipio, natureza_juridica).
    """
    conn = MagicMock()
    cursor = conn.cursor.return_value

    # Mock cursor.__enter__ for context manager usage
    conn.cursor.return_value.__enter__.return_value = cursor

    # We use side_effect to return different results on successive
    # cursor.fetchall() calls
    cursor.fetchall.side_effect = [groups, by_source, uncovered]
    # Mock description for first query
    # (description is only needed for returned cursors, which we don't use here)
    return conn


class TestReportCoverage:
    def test_all_entities_covered(self):
        """Return 100% coverage when all entities are covered."""
        conn = _make_mock_conn(
            groups=[(True, 10, 10, 0)],
            by_source=[("pncp", 10, 10)],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert result["total_entities"] == 10
        assert result["total_covered"] == 10
        assert result["total_uncovered"] == 0
        assert result["pct"] == 100.0
        assert len(result["groups"]) == 1
        assert result["groups"][0]["pct"] == 100.0

    def test_partial_coverage(self):
        """Return correct percentage when some entities are uncovered."""
        conn = _make_mock_conn(
            groups=[(True, 20, 12, 8)],
            by_source=[("dom_sc", 20, 12)],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert result["total_entities"] == 20
        assert result["total_covered"] == 12
        assert result["pct"] == 60.0

    def test_zero_entities(self):
        """Handle zero entities gracefully."""
        conn = _make_mock_conn(
            groups=[],
            by_source=[],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert result["total_entities"] == 0
        assert result["total_covered"] == 0
        assert result["pct"] == 0.0
        assert result["groups"] == []
        assert result["by_source"] == []

    def test_both_radius_groups(self):
        """Handle both within_200km and outside groups."""
        conn = _make_mock_conn(
            groups=[
                (True, 15, 12, 3),
                (False, 5, 2, 3),
            ],
            by_source=[("pncp", 15, 12)],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert len(result["groups"]) == 2
        assert result["groups"][0]["within_200km"] is True
        assert result["groups"][1]["within_200km"] is False
        assert result["total_entities"] == 20
        assert result["total_covered"] == 14

    def test_uncovered_within_200km(self):
        """Report uncovered entities within 200km radius."""
        conn = _make_mock_conn(
            groups=[(True, 5, 3, 2)],
            by_source=[("pncp", 5, 3)],
            uncovered=[
                ("Prefeitura de Sao Jose", "87654321", "Sao Jose", "PREFEITURA"),
                ("Prefeitura de Palhoca", "99887766", "Palhoca", "PREFEITURA"),
            ],
        )

        result = report_coverage(conn)

        assert len(result["uncovered_entities_200km"]) == 2
        assert result["uncovered_entities_200km"][0]["razao_social"] == "Prefeitura de Sao Jose"

    def test_no_uncovered_within_200km(self):
        """Return empty list when all 200km entities are covered."""
        conn = _make_mock_conn(
            groups=[(True, 10, 10, 0)],
            by_source=[("pncp", 10, 10)],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert result["uncovered_entities_200km"] == []

    def test_by_source_breakdown(self):
        """Provide per-source coverage breakdown."""
        conn = _make_mock_conn(
            groups=[(True, 30, 25, 5)],
            by_source=[
                ("pncp", 20, 18),
                ("dom_sc", 10, 7),
            ],
            uncovered=[],
        )

        result = report_coverage(conn)

        assert len(result["by_source"]) == 2
        assert result["by_source"][0]["source"] == "pncp"
        assert result["by_source"][0]["covered"] == 18
        assert result["by_source"][1]["source"] == "dom_sc"
        assert result["by_source"][1]["covered"] == 7


# ---------------------------------------------------------------------------
# print_coverage_report
# ---------------------------------------------------------------------------


class TestPrintCoverageReport:
    def test_logs_coverage_summary(self, caplog):
        """Log coverage report with correct values."""
        result = {
            "groups": [
                {"within_200km": True, "total": 10, "covered": 8, "uncovered": 2, "pct": 80.0},
            ],
            "total_entities": 10,
            "total_covered": 8,
            "total_uncovered": 2,
            "pct": 80.0,
            "by_source": [
                {"source": "pncp", "entities": 10, "covered": 8},
            ],
            "uncovered_entities_200km": [],
        }

        with caplog.at_level("INFO"):
            print_coverage_report(result)

        assert any("80.0" in msg for msg in caplog.messages)
        assert any("10" in msg for msg in caplog.messages)

    def test_warns_on_uncovered(self, caplog):
        """Log warning when uncovered entities exist within 200km."""
        result = {
            "groups": [
                {"within_200km": True, "total": 10, "covered": 6, "uncovered": 4, "pct": 60.0},
            ],
            "total_entities": 10,
            "total_covered": 6,
            "total_uncovered": 4,
            "pct": 60.0,
            "by_source": [
                {"source": "pncp", "entities": 10, "covered": 6},
            ],
            "uncovered_entities_200km": [
                {"razao_social": "Prefeitura Teste", "municipio": "Testopolis"},
            ],
        }

        with caplog.at_level("WARNING"):
            print_coverage_report(result)

        assert any("SEM COBERTURA" in msg for msg in caplog.messages)

    def test_no_warning_when_all_covered(self, caplog):
        """No warning logged when all entities are covered."""
        result = {
            "groups": [
                {"within_200km": True, "total": 5, "covered": 5, "uncovered": 0, "pct": 100.0},
            ],
            "total_entities": 5,
            "total_covered": 5,
            "total_uncovered": 0,
            "pct": 100.0,
            "by_source": [
                {"source": "pncp", "entities": 5, "covered": 5},
            ],
            "uncovered_entities_200km": [],
        }

        with caplog.at_level("WARNING"):
            print_coverage_report(result)

        warning_logs = [m for m in caplog.messages if "SEM COBERTURA" in m]
        assert len(warning_logs) == 0, "Expected no WARNING about uncovered entities"

    def test_empty_result_does_not_crash(self, caplog):
        """Empty/dummy result does not crash the logger."""
        result = {
            "groups": [],
            "total_entities": 0,
            "total_covered": 0,
            "total_uncovered": 0,
            "pct": 0.0,
            "by_source": [],
            "uncovered_entities_200km": [],
        }

        # Should not raise any exception
        print_coverage_report(result)
        assert True
