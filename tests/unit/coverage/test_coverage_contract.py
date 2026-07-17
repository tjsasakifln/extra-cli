"""Unit tests for the formal coverage contract.

Guarantees:
  - commercial signal is NEVER labeled coverage
  - denominator is fixed / not gamed
  - SLA config loads
  - completeness treats missing fields as explicit absence
  - report schema contains all required metric keys
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.coverage.coverage_contract import (
    ALL_METRIC_IDS,
    DECISION_FIELDS,
    FIXED_CANONICAL_DENOMINATOR,
    HEADLINE_METRIC,
    LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY,
    METRIC_DEFINITIONS,
    METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
    METRIC_FRESHNESS_COVERAGE,
    METRIC_OPERATIONAL_SOURCE_COVERAGE,
    METRIC_OPPORTUNITY_RECALL,
    METRIC_REQUIRED_FIELD_COMPLETENESS,
    METRIC_SOURCE_MAPPING_COVERAGE,
    MetricKind,
    build_contract_report,
    compute_commercial_signal,
    compute_field_completeness,
    compute_opportunity_recall,
    compute_required_field_completeness,
    compute_source_mapping_coverage,
    format_report_table,
    load_sla_config,
    resolve_denominator,
)


# ---------------------------------------------------------------------------
# Metric names / kinds
# ---------------------------------------------------------------------------


def test_metric_ids_are_correct():
    assert METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL == (
        "entities_with_recent_commercial_signal"
    )
    assert METRIC_SOURCE_MAPPING_COVERAGE == "source_mapping_coverage"
    assert METRIC_OPERATIONAL_SOURCE_COVERAGE == "operational_source_coverage"
    assert METRIC_FRESHNESS_COVERAGE == "freshness_coverage"
    assert METRIC_OPPORTUNITY_RECALL == "opportunity_recall"
    assert METRIC_REQUIRED_FIELD_COMPLETENESS == "required_field_completeness"
    assert set(ALL_METRIC_IDS) == {
        METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
        METRIC_SOURCE_MAPPING_COVERAGE,
        METRIC_OPERATIONAL_SOURCE_COVERAGE,
        METRIC_FRESHNESS_COVERAGE,
        METRIC_OPPORTUNITY_RECALL,
        METRIC_REQUIRED_FIELD_COMPLETENESS,
    }


def test_commercial_signal_is_not_labeled_coverage():
    """Commercial signal metric must never be kind=coverage or named *coverage*."""
    definition = METRIC_DEFINITIONS[METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL]
    assert definition.kind == MetricKind.COMMERCIAL_SIGNAL
    assert definition.kind != MetricKind.COVERAGE
    assert "coverage" not in definition.metric_id
    assert "coverage" not in definition.metric_id.lower()
    assert LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY in definition.legacy_aliases

    result = compute_commercial_signal(
        FIXED_CANONICAL_DENOMINATOR,
        commercial_entity_ids={1, 2, 3},
    )
    assert result.metric_id == METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL
    assert result.is_coverage_metric is False
    assert result.kind == "commercial_signal"
    assert "coverage" not in result.metric_id
    assert result.numerator == 3
    assert result.denominator == FIXED_CANONICAL_DENOMINATOR
    assert result.pct == pytest.approx(round(3 / 1093 * 100, 2), abs=0.01)


def test_headline_is_commercial_signal_not_coverage():
    assert HEADLINE_METRIC == METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL
    assert "coverage" not in HEADLINE_METRIC


def test_legacy_alias_is_not_coverage():
    assert LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY == "commercial_opportunity_any"
    assert "coverage" not in LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY


# ---------------------------------------------------------------------------
# Denominator
# ---------------------------------------------------------------------------


def test_denominator_fixed_from_csv():
    """CSV fallback yields fixed 1093; never shrunk to improve %."""
    denom = resolve_denominator(conn=None, seed_path=Path("/nonexistent/seed.xlsx"))
    assert denom.value == FIXED_CANONICAL_DENOMINATOR
    assert denom.value == 1093
    assert denom.fixed_canonical is True
    # Must not be a toy denominator
    assert denom.value >= 1000


def test_denominator_never_changed_to_improve_pct(tmp_path: Path):
    """Even with a smaller CSV, we still report the actual count honestly —
    and the contract stamps fixed_canonical only when count == 1093.
    """
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text("ibge_code,cnpj,name\n1,123,A\n2,456,B\n", encoding="utf-8")
    denom = resolve_denominator(
        conn=None,
        seed_path=Path("/nonexistent/seed.xlsx"),
        csv_path=csv_path,
    )
    # Honest count — not inflated, not forced to 1093 when CSV differs
    assert denom.value == 2
    assert denom.fixed_canonical is False


# ---------------------------------------------------------------------------
# SLA config
# ---------------------------------------------------------------------------


def test_sla_config_loads():
    sla = load_sla_config()
    assert sla.open_opportunities_hours == 24
    assert sla.official_diaries_hours == 24
    assert sla.contracts_amendments_hours == 72
    assert sla.historical_consolidated_days == 7
    assert sla.cadastral_data_days == 30
    d = sla.to_dict()
    assert d["open_opportunities_hours"] == 24


def test_sla_config_missing_file_uses_defaults(tmp_path: Path):
    sla = load_sla_config(tmp_path / "missing.yaml")
    assert sla.open_opportunities_hours == 24
    assert sla.cadastral_data_days == 30


# ---------------------------------------------------------------------------
# Completeness — explicit absence
# ---------------------------------------------------------------------------


def test_decision_fields_match_contract():
    expected = {
        "entity",
        "cnpj",
        "process",
        "edital",
        "objeto",
        "modalidade",
        "situacao",
        "datas",
        "valor",
        "local",
        "url",
        "docs",
        "fonte",
        "collected_at",
        "commercial_class",
        "sector_class",
        "ranking_evidence",
    }
    assert set(DECISION_FIELDS) == expected
    assert len(DECISION_FIELDS) == 17


def test_completeness_handles_missing_fields_as_explicit_absence():
    rows = [
        {
            "orgao_nome": "Pref X",
            "objeto": "Reforma de escola",
            # deliberately missing cnpj, valor, datas, process, etc.
        }
    ]
    breakdown = compute_field_completeness(rows)
    assert breakdown["records"] == 1
    assert breakdown["per_field"]["entity"]["present"] == 1
    assert breakdown["per_field"]["objeto"]["present"] == 1
    assert breakdown["per_field"]["cnpj"]["present"] == 0
    assert breakdown["per_field"]["cnpj"]["absent"] == 1
    assert breakdown["per_field"]["cnpj"]["absence_explicit"] is True
    assert breakdown["per_field"]["valor"]["absent"] == 1
    assert breakdown["mean_completeness_pct"] is not None
    assert breakdown["mean_completeness_pct"] < 50.0

    result = compute_required_field_completeness(records=rows)
    assert result.status == "READY"
    assert result.metric_id == METRIC_REQUIRED_FIELD_COMPLETENESS
    assert result.pct is not None
    assert result.pct < 50.0
    assert result.denominator == len(DECISION_FIELDS)
    assert result.field_breakdown is not None
    assert result.field_breakdown["per_field"]["cnpj"]["absence_explicit"] is True


def test_completeness_full_record():
    full = {
        "entity": "Pref Y",
        "cnpj": "12345678000199",
        "process": "001/2026",
        "edital": "ED-1",
        "objeto": "Obra",
        "modalidade": "PE",
        "situacao": "OPEN",
        "datas": "2026-07-01",
        "valor": 1000,
        "local": "Florianópolis",
        "url": "https://example.com",
        "docs": ["a.pdf"],
        "fonte": "pncp",
        "collected_at": "2026-07-17T00:00:00Z",
        "commercial_class": "OPEN_OPPORTUNITY",
        "sector_class": "engineering",
        "ranking_evidence": {"score": 90},
    }
    breakdown = compute_field_completeness([full])
    assert breakdown["mean_completeness_pct"] == 100.0
    for f in DECISION_FIELDS:
        assert breakdown["per_field"][f]["present"] == 1
        assert breakdown["per_field"][f]["absent"] == 0


# ---------------------------------------------------------------------------
# Source mapping
# ---------------------------------------------------------------------------


def test_source_mapping_not_ready_without_registry(tmp_path: Path):
    missing = tmp_path / "nope.jsonl"
    result = compute_source_mapping_coverage(
        FIXED_CANONICAL_DENOMINATOR, registry_path=missing
    )
    assert result.status == "NOT_READY"
    assert result.numerator is None
    assert result.pct is None
    assert result.reason is not None
    assert "NOT_READY" in (result.reason or "") or "not found" in (result.reason or "").lower()
    # Must NOT invent 0% as covered
    assert result.pct != 0.0


def test_source_mapping_from_registry(tmp_path: Path):
    reg = tmp_path / "registry.jsonl"
    lines = []
    for i in range(FIXED_CANONICAL_DENOMINATOR):
        lines.append(
            json.dumps(
                {
                    "canonical_id": f"e{i}",
                    "access_status": "source_not_identified" if i % 2 else "mapped",
                }
            )
        )
    reg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = compute_source_mapping_coverage(
        FIXED_CANONICAL_DENOMINATOR, registry_path=reg
    )
    assert result.status == "READY"
    assert result.numerator == FIXED_CANONICAL_DENOMINATOR
    assert result.denominator == FIXED_CANONICAL_DENOMINATOR
    assert result.pct == 100.0
    assert result.is_coverage_metric is True


# ---------------------------------------------------------------------------
# Opportunity recall — never from DB counts
# ---------------------------------------------------------------------------


def test_opportunity_recall_not_ready_without_sample(tmp_path: Path):
    result = compute_opportunity_recall(
        FIXED_CANONICAL_DENOMINATOR,
        benchmark_path=tmp_path / "missing.json",
    )
    assert result.status == "NOT_READY"
    assert result.numerator is None
    assert "database" in (result.reason or "").lower() or "benchmark" in (
        result.reason or ""
    ).lower()


def test_opportunity_recall_from_stratified_sample(tmp_path: Path):
    sample = tmp_path / "recall.json"
    sample.write_text(
        json.dumps(
            {
                "items": [
                    {"relevant": True, "retrieved": True},
                    {"relevant": True, "retrieved": True},
                    {"relevant": True, "retrieved": False},
                    {"relevant": False, "retrieved": True},  # ignored for recall
                ]
            }
        ),
        encoding="utf-8",
    )
    result = compute_opportunity_recall(
        FIXED_CANONICAL_DENOMINATOR, benchmark_path=sample
    )
    assert result.status == "READY"
    assert result.numerator == 2
    assert result.denominator == 3  # relevant only
    assert result.pct == pytest.approx(66.67, abs=0.01)
    assert result.sample_size == 4
    assert any("not_from_database" in lim for lim in result.limitations)


# ---------------------------------------------------------------------------
# Full report schema
# ---------------------------------------------------------------------------


def test_report_schema_has_all_required_metric_keys(tmp_path: Path):
    report = build_contract_report(
        conn=None,
        session_dir=tmp_path,  # empty — metrics may be NOT_READY
        registry_path=tmp_path / "missing_registry.jsonl",
        benchmark_path=tmp_path / "missing_benchmark.json",
        commercial_entity_ids={10, 20},
        completeness_records=[{"orgao_nome": "X", "objeto": "Y"}],
        seed_path=Path("/nonexistent/seed.xlsx"),
        csv_path=Path("config/target_entities_200km.csv"),
    )
    payload = report.to_dict()

    assert payload["headline_metric"] == METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL
    assert payload["headline_is_coverage"] is False
    assert payload["denominator"]["value"] == FIXED_CANONICAL_DENOMINATOR

    metrics = payload["metrics"]
    for mid in ALL_METRIC_IDS:
        assert mid in metrics, f"missing metric key: {mid}"
        m = metrics[mid]
        assert "metric_id" in m
        assert "numerator" in m
        assert "denominator" in m
        assert "pct" in m
        assert "status" in m
        assert "kind" in m
        assert "is_coverage_metric" in m

    # Legacy alias present for backward compat
    assert LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY in metrics
    alias = metrics[LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY]
    assert alias["is_coverage_metric"] is False
    assert alias["kind"] == "commercial_signal"
    assert alias.get("alias_of") == METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL

    commercial = metrics[METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL]
    assert commercial["is_coverage_metric"] is False
    assert commercial["kind"] == "commercial_signal"
    assert commercial["numerator"] == 2
    assert commercial["denominator"] == 1093

    # source mapping must be NOT_READY (not invented 0%)
    sm = metrics[METRIC_SOURCE_MAPPING_COVERAGE]
    assert sm["status"] == "NOT_READY"
    assert sm["numerator"] is None


def test_format_report_table_marks_commercial_not_coverage():
    report = build_contract_report(
        conn=None,
        commercial_entity_ids={1},
        completeness_records=[{"entity": "A"}],
        seed_path=Path("/nonexistent/seed.xlsx"),
        registry_path=Path("/nonexistent/registry.jsonl"),
        benchmark_path=Path("/nonexistent/bench.json"),
    )
    table = format_report_table(report)
    assert METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL in table
    assert "NOT coverage" in table
    assert "commercial_signal" in table
    # Must show numerator/denominator style values
    assert "1093" in table
