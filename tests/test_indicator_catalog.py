"""DoD §25 — every catalog indicator has definition, formula, denominator, etc."""
from __future__ import annotations

from scripts.coverage.coverage_contract import (
    ALL_METRIC_IDS,
    BLOCKED_SEMANTICS,
    METRIC_DEFINITIONS,
    MetricStatus,
    NOT_READY_SEMANTICS,
    PARTIAL_SEMANTICS,
    READY_SEMANTICS,
    _not_ready,
    _ready,
    export_indicator_catalog,
    validate_indicator_catalog,
)


def test_catalog_validation_ok() -> None:
    report = validate_indicator_catalog()
    assert report["ok"] is True, report
    assert report["indicator_count"] == len(ALL_METRIC_IDS)
    assert report["issues"] == []


def test_every_indicator_has_definition_formula_denominator_source_asof() -> None:
    for metric_id in ALL_METRIC_IDS:
        d = METRIC_DEFINITIONS[metric_id]
        assert d.definition.strip()
        assert d.formula.strip()
        assert d.denominator_policy.strip()
        assert d.as_of_policy.strip()
        assert d.source_policy.strip()
        assert d.required_fields_present() is True


def test_ready_semantics_document_execution_not_code_existence() -> None:
    assert "executed" in READY_SEMANTICS.lower()
    assert "validated" in READY_SEMANTICS.lower()
    assert "code existence alone" in READY_SEMANTICS.lower()


def test_partial_semantics_explicit_limitations_not_ready() -> None:
    """DoD §25: PARTIAL = computed with explicit limitations; never READY/DONE."""
    low = PARTIAL_SEMANTICS.lower()
    assert "partial" in low
    assert "limitation" in low or "limitations" in low
    assert "never equivalent to ready" in low or "never" in low
    assert PARTIAL_SEMANTICS != READY_SEMANTICS
    catalog = validate_indicator_catalog()
    assert catalog["partial_semantics"] == PARTIAL_SEMANTICS


def test_blocked_semantics_external_or_technical_dependency() -> None:
    """DoD §25: BLOCKED = impeded by external or technical dependency."""
    low = BLOCKED_SEMANTICS.lower()
    assert "blocked" in low
    assert "external" in low or "technical" in low
    assert "dependency" in low
    catalog = validate_indicator_catalog()
    assert catalog["blocked_semantics"] == BLOCKED_SEMANTICS
    assert "not_ready" in NOT_READY_SEMANTICS.lower()


def test_ready_result_carries_status_denominator_formula() -> None:
    result = _ready(
        "source_mapping_coverage",
        numerator=1093,
        denominator=1093,
        reason="unit-test",
    )
    assert result.status == MetricStatus.READY.value
    assert result.denominator == 1093
    assert result.formula
    assert result.pct == 100.0


def test_not_ready_has_status_and_null_pct() -> None:
    result = _not_ready(
        "freshness_coverage",
        reason="entity-level freshness unavailable",
        denominator=1093,
    )
    assert result.status == MetricStatus.NOT_READY.value
    assert result.pct is None
    assert result.numerator is None
    assert result.denominator == 1093


def test_export_indicator_catalog_includes_all_ids() -> None:
    cat = export_indicator_catalog()
    ids = {item["metric_id"] for item in cat["items"]}
    assert ids == set(ALL_METRIC_IDS)
    assert cat["ok"] is True
