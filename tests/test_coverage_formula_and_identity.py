"""#280 unified covered-entity formula and #350 dual-coverage identity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import scripts.coverage.calculator as coverage_calculator
import scripts.coverage.manifest as coverage_manifest
import scripts.coverage.validate_coverage as coverage_panel
import scripts.coverage_truth as coverage_qa
import scripts.reports.coverage_weekly as coverage_weekly
from scripts.coverage.calculator import report_coverage
from scripts.coverage.covered_entity import (
    COVERED_ENTITY_FORMULA,
    MISSING_EVIDENCE,
    CoverageFormulaDivergenceError,
    assert_surfaces_agree,
    classify_evidence_identity,
    compute_coverage_kpis,
    dual_coverage_evidence_gate,
    is_covered_state,
)
from scripts.coverage_truth import compute_metrics

FIXTURE_ROWS = [
    {"entity_id": "e-ok-data", "state": "success_with_data"},
    {"entity_id": "e-ok-zero", "state": "success_zero"},
    {"entity_id": "e-blocked", "state": "blocked"},
    {"entity_id": "e-failed", "state": "failed"},
    {"entity_id": "e-error", "state": "error"},
    {"entity_id": "e-partial", "state": "partial"},
    {"entity_id": "e-boolean-only", "is_covered": True},
]


def test_surfaces_share_one_covered_entity_formula() -> None:
    assert coverage_calculator.COVERED_ENTITY_FORMULA is COVERED_ENTITY_FORMULA
    assert coverage_weekly.COVERED_ENTITY_FORMULA is COVERED_ENTITY_FORMULA
    assert coverage_panel.COVERED_ENTITY_FORMULA is COVERED_ENTITY_FORMULA
    assert coverage_manifest.COVERED_ENTITY_FORMULA is COVERED_ENTITY_FORMULA
    assert coverage_qa.COVERED_ENTITY_FORMULA is COVERED_ENTITY_FORMULA
    kpis = {
        "panel": coverage_panel.COVERED_ENTITY_FORMULA(FIXTURE_ROWS),
        "pdf": coverage_weekly.COVERED_ENTITY_FORMULA(FIXTURE_ROWS),
        "excel": coverage_weekly.COVERED_ENTITY_FORMULA(FIXTURE_ROWS),
        "manifest": coverage_manifest.COVERED_ENTITY_FORMULA(FIXTURE_ROWS),
        "qa": coverage_qa.COVERED_ENTITY_FORMULA(FIXTURE_ROWS),
    }
    agreed = assert_surfaces_agree(kpis)
    assert agreed.covered_entity_ids == frozenset({"e-ok-data", "e-ok-zero"})
    assert agreed.covered_count == 2
    assert "e-blocked" in agreed.excluded_entity_ids
    assert "e-failed" in agreed.excluded_entity_ids
    assert "e-boolean-only" in agreed.excluded_entity_ids


def test_failed_and_blocked_never_count_as_covered() -> None:
    assert is_covered_state("failed") is False
    assert is_covered_state("blocked") is False
    assert is_covered_state("error") is False
    assert is_covered_state("success_with_data") is True
    kpis = compute_coverage_kpis(FIXTURE_ROWS)
    assert "e-blocked" not in kpis.covered_entity_ids
    assert "e-failed" not in kpis.covered_entity_ids


def test_disagreeing_surfaces_fail_the_gate() -> None:
    panel = compute_coverage_kpis(FIXTURE_ROWS)
    matrix = compute_coverage_kpis(
        [{"entity_id": "e-ok-data", "state": "success_with_data"}]
    )
    with pytest.raises(CoverageFormulaDivergenceError, match="panel"):
        assert_surfaces_agree({"panel": panel, "matrix": matrix})


def test_source_wide_aggregate_is_missing_evidence_not_a_numerator() -> None:
    rows = [
        {
            "id": 3,
            "entity_id": None,
            "canonical_entity_key": None,
            "source": "pncp",
            "data_type": "bids",
            "state": "success_with_data",
            "run_id": 22,
            "count_obtained": 800,
            "count_persisted": 800,
            "metadata": {"pipeline": "resilient_cycle"},
        }
    ]
    assert classify_evidence_identity(
        entity_id=None,
        canonical_entity_key=None,
        metadata={"pipeline": "resilient_cycle"},
    ) == "SOURCE_WIDE_AGGREGATE"
    gate = dual_coverage_evidence_gate(rows)
    assert gate["classification"] == MISSING_EVIDENCE
    assert gate["measurement_success"] is False
    assert gate["numerator_rows"] == []
    assert gate["reason"] == "source_wide_aggregate_without_identity"


def test_identified_rows_enter_numerators_source_wide_does_not() -> None:
    rows = [
        {
            "entity_id": None,
            "canonical_entity_key": None,
            "metadata": {"pipeline": "resilient_cycle"},
            "state": "success_with_data",
        },
        {
            "entity_id": 10,
            "canonical_entity_key": "ent-10",
            "state": "success_with_data",
        },
    ]
    gate = dual_coverage_evidence_gate(rows)
    assert gate["measurement_success"] is True
    assert gate["source_wide_count"] == 1
    assert gate["identified_count"] == 1
    assert len(gate["numerator_rows"]) == 1
    assert gate["numerator_rows"][0]["canonical_entity_key"] == "ent-10"


def test_published_surfaces_call_formula_not_is_covered() -> None:
    state_rows = [
        ("ok", "success_with_data", "pncp", {}),
        ("blk", "blocked", "pncp", {}),
        ("fail", "failed", "pncp", {}),
    ]
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = state_rows
    published = report_coverage(conn)
    expected = compute_coverage_kpis(
        [{"entity_id": r[0], "state": r[1], "source": r[2]} for r in state_rows]
    )
    assert published["total_covered"] == expected.covered_count == 1
    assert published["covered_entity_ids"] == ["ok"]

    qa = compute_metrics(
        entities=[
            {"id": 1, "razao_social": "A"},
            {"id": 2, "razao_social": "B"},
            {"id": 3, "razao_social": "C"},
        ],
        coverage=[],
        evidence=[
            {"entity_id": 1, "source": "pncp", "state": "success_with_data"},
            {"entity_id": 2, "source": "pncp", "state": "blocked"},
            {"entity_id": 3, "source": "pncp", "state": "failed"},
        ],
        source_health=[],
        contract_presence={},
        radius_km=200,
    )
    assert qa["monitoring_coverage"]["entities_monitored"] == 1
    assert "1" in qa["monitoring_coverage"]["covered_entity_ids"]

    kpis = compute_coverage_kpis(
        [{"entity_id": r[0], "state": r[1], "source": r[2]} for r in state_rows]
    )

    def _fake_query(sql, params=None):
        if "COUNT(*) AS total" in sql:
            return [{"total": 3}]
        return []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(coverage_weekly, "query", _fake_query)
    monkeypatch.setattr(coverage_weekly, "published_coverage_kpis", lambda _conn: kpis)
    monkeypatch.setattr(coverage_weekly, "get_conn", lambda: conn)
    weekly = coverage_weekly.fetch_coverage_data(__import__("datetime").date(2026, 8, 13))
    monkeypatch.undo()
    assert weekly["total_covered"] == 1


def test_unmappable_identity_bearing_row_is_not_silently_dropped() -> None:
    # A row with a key that classify treats as mapped stays in identified;
    # residual without identity and without aggregate markers is source-wide.
    # True drop-protection is the fail-closed unmapped path when identity is
    # present but cannot join the universe — exercised via dual_coverage gate
    # when we force UNMAPPABLE by monkeypatch.
    from scripts.coverage import covered_entity as ce

    original = ce.classify_evidence_identity

    def _force_unmappable(**kwargs):
        if kwargs.get("entity_id") == "ghost":
            return ce.UNMAPPABLE
        return original(**kwargs)

    ce.classify_evidence_identity = _force_unmappable  # type: ignore[method-assign]
    try:
        gate = dual_coverage_evidence_gate([{"entity_id": "ghost", "state": "success_with_data"}])
        assert gate["classification"] == MISSING_EVIDENCE
        assert gate["reason"] == "unmappable_evidence_cannot_drop"
        assert gate["numerator_rows"] == []
    finally:
        ce.classify_evidence_identity = original  # type: ignore[method-assign]
