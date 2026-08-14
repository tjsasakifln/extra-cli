"""Unit tests for scripts/coverage/calculator.py.

Published KPIs come from compute_coverage_kpis, never is_covered COUNT.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.coverage.calculator import print_coverage_report, report_coverage
from scripts.coverage.covered_entity import compute_coverage_kpis


def _make_mock_conn(state_rows: list[tuple]) -> MagicMock:
    conn = MagicMock()
    cursor = conn.cursor.return_value
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = state_rows
    return conn


class TestReportCoverage:
    def test_all_entities_covered(self):
        rows = [(f"e{i}", "success_with_data", "pncp", {}) for i in range(10)]
        result = report_coverage(_make_mock_conn(rows))
        expected = compute_coverage_kpis(
            [{"entity_id": r[0], "state": r[1], "source": r[2]} for r in rows]
        )
        assert result["total_covered"] == expected.covered_count == 10
        assert result["total_entities"] == 10
        assert result["pct"] == 100.0

    def test_partial_coverage_ignores_blocked(self):
        rows = [(f"e{i}", "success_with_data", "dom_sc", {}) for i in range(12)]
        rows += [(f"b{i}", "blocked", "dom_sc", {}) for i in range(8)]
        result = report_coverage(_make_mock_conn(rows))
        expected = compute_coverage_kpis(
            [{"entity_id": r[0], "state": r[1], "source": r[2]} for r in rows]
        )
        assert result["total_covered"] == expected.covered_count == 12
        assert result["total_uncovered"] == 8
        assert result["pct"] == 60.0
        assert "b0" not in result["covered_entity_ids"]

    def test_zero_entities(self):
        result = report_coverage(_make_mock_conn([]))
        assert result["total_entities"] == 0
        assert result["total_covered"] == 0
        assert result["pct"] == 0.0
        assert result["groups"] == []
        assert result["by_source"] == []

    def test_failed_and_blocked_never_published_as_covered(self):
        rows = [
            ("ok", "success_zero", "pncp", {}),
            ("bad", "failed", "pncp", {}),
            ("blk", "blocked", "pncp", {}),
        ]
        result = report_coverage(_make_mock_conn(rows))
        assert result["total_covered"] == 1
        assert result["covered_entity_ids"] == ["ok"]

    def test_uncovered_list_uses_formula_exclusions(self):
        rows = [
            ("covered", "success_with_data", "pncp", {}),
            ("gap", "error", "pncp", {}),
        ]
        result = report_coverage(_make_mock_conn(rows))
        assert any(item["razao_social"] == "gap" for item in result["uncovered_entities_200km"])

    def test_by_source_breakdown_uses_formula(self):
        rows = [
            ("a", "success_with_data", "pncp", {}),
            ("b", "blocked", "pncp", {}),
            ("c", "success_zero", "dom_sc", {}),
        ]
        result = report_coverage(_make_mock_conn(rows))
        by_source = {item["source"]: item for item in result["by_source"]}
        assert by_source["pncp"]["covered"] == 1
        assert by_source["dom_sc"]["covered"] == 1


class TestPrintCoverageReport:
    def test_logs_coverage_summary(self, caplog):
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
        assert len(warning_logs) == 0

    def test_empty_result_does_not_crash(self, caplog):
        result = {
            "groups": [],
            "total_entities": 0,
            "total_covered": 0,
            "total_uncovered": 0,
            "pct": 0.0,
            "by_source": [],
            "uncovered_entities_200km": [],
        }
        print_coverage_report(result)
        assert True
