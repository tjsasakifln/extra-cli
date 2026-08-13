"""Tests for the AlertaLicitação recall gate (#35). Drives shipped functions."""

from __future__ import annotations

import pytest

from scripts.coverage.alerta_recall_gate import (
    BUCKET_ALERTA_ONLY,
    BUCKET_EXTRA_ONLY,
    LAYER_ADERENTE,
    LAYER_BRUTO,
    LAYER_MATERIAL,
    RETIRE_CONTINUE,
    RETIRE_REDUCE,
    RETIRE_RETIRE,
    OpportunityRef,
    evaluate_recall,
    evaluate_retirement,
    gate_exit,
    wilson_interval,
)


def _ref(
    identity: str,
    *,
    aderente: bool = True,
    material: bool = True,
    tipo_fonte: str = "api",
    platform: str = "alerta",
) -> OpportunityRef:
    return OpportunityRef(
        identity=identity,
        source_platform=platform,
        ente_id="ente-1",
        modalidade="pregao",
        municipio="Florianopolis",
        esfera="municipal",
        natureza_objeto="engenharia",
        publicacao_original="pncp",
        tipo_fonte=tipo_fonte,
        published_at="2026-07-01T10:00:00Z",
        discovered_at="2026-07-01T12:00:00Z",
        aderente=aderente,
        material=material,
        strata=("ente", "plataforma"),
    )


def test_wilson_interval_empty_and_full() -> None:
    assert wilson_interval(0, 0) == (None, None)
    low, high = wilson_interval(10, 10)
    assert low is not None and high is not None
    assert 0.0 <= low <= 1.0
    assert high == 1.0 or high < 1.0
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_recall_layers_exclude_extra_only_from_denominator() -> None:
    alerta = [
        _ref("A1"),
        _ref("A2", aderente=True, material=False),
        _ref("A3", aderente=False, material=False),
        _ref("A4"),
    ]
    extra = [
        _ref("A1", platform="extra"),
        _ref("A2", platform="extra"),
        _ref("X9", platform="extra"),  # extra_only gain
    ]
    report = evaluate_recall(
        alerta_items=alerta,
        extra_items=extra,
        window_start="2026-07-01",
        window_end="2026-07-31",
        cutoff="2026-07-31T23:59:59Z",
        filters={"uf": "SC", "profile": "confenge"},
        period_id="2026-07",
    )
    assert "X9" in report.buckets[BUCKET_EXTRA_ONLY]
    assert "X9" not in report.layers[LAYER_BRUTO].misses
    assert report.layers[LAYER_BRUTO].denominator == 4
    assert report.layers[LAYER_BRUTO].numerator == 2
    assert report.layers[LAYER_ADERENTE].denominator == 3  # A1 A2 A4
    assert report.layers[LAYER_ADERENTE].numerator == 2
    assert report.layers[LAYER_MATERIAL].denominator == 2  # A1 A4
    assert report.layers[LAYER_MATERIAL].numerator == 1
    assert report.layers[LAYER_MATERIAL].misses == ("A4",)
    assert "X9" in report.extra_only_audit
    # extra_only must not appear in any layer denominator identity set
    for layer in report.layers.values():
        assert "X9" not in layer.misses
        assert layer.denominator != 5


def test_alerta_only_misses_are_adjudicated_with_346() -> None:
    alerta = [_ref("M1", tipo_fonte="html"), _ref("M2")]
    extra = [_ref("M2", platform="extra")]
    report = evaluate_recall(
        alerta_items=alerta,
        extra_items=extra,
        window_start="2026-01-01",
        window_end="2026-01-31",
        cutoff="2026-01-31T23:59:59Z",
        filters={"setor": "engenharia"},
        period_id="2026-01",
        latency_hours_by_id={"M1": 40.0},
    )
    assert report.buckets[BUCKET_ALERTA_ONLY] == ("M1",)
    assert len(report.misses) == 1
    miss = report.misses[0]
    assert miss.identity == "M1"
    assert miss.reconciles_with == "#346"
    assert miss.cause == "freshness_lag"
    assert "freshness" in miss.next_action


def test_window_manifest_records_filters_hashes_strata_and_slo() -> None:
    alerta = [_ref("Z1")]
    extra = [_ref("Z1", platform="extra")]
    report = evaluate_recall(
        alerta_items=alerta,
        extra_items=extra,
        window_start="2026-02-01",
        window_end="2026-02-28",
        cutoff="2026-02-28T23:59:59Z",
        filters={"modalidade": "pregao", "esfera": "municipal"},
        period_id="2026-02",
    )
    man = report.manifest
    assert man.filters["modalidade"] == "pregao"
    assert man.cutoff.endswith("Z")
    assert man.universe_hash
    assert man.sample_size == 1
    assert "ente" in man.strata and "natureza_objeto" in man.strata
    assert man.hashes["alerta"]
    assert man.slo["material_min"] == 0.95
    payload = report.as_dict()
    assert payload["schema_version"] == 1
    assert payload["layers"]["bruto"]["numerator"] == 1


def test_operational_count_proxy_is_rejected() -> None:
    with pytest.raises(ValueError, match="operational counts"):
        evaluate_recall(
            alerta_items=[_ref("A")],
            extra_items=[],
            window_start="2026-01-01",
            window_end="2026-01-31",
            cutoff="2026-01-31Z",
            filters={"proxy": "db_row_count"},
            period_id="x",
        )


def test_retirement_requires_repeated_windows() -> None:
    from scripts.coverage.alerta_recall_gate import LayerMetric

    perfect = LayerMetric(
        name="material",
        numerator=100,
        denominator=100,
        rate=1.0,
        misses=(),
        ci_low=0.96,
        ci_high=1.0,
    )
    decision, _ = evaluate_retirement(
        perfect,
        consecutive_windows_meeting=1,
        slo={"retire_material_min": 0.97, "retire_windows": 4, "reduce_material_min": 0.93},
    )
    assert decision == RETIRE_REDUCE
    decision, _ = evaluate_retirement(
        perfect,
        consecutive_windows_meeting=4,
        slo={"retire_material_min": 0.97, "retire_windows": 4, "reduce_material_min": 0.93},
    )
    assert decision == RETIRE_RETIRE
    weak = LayerMetric(
        name="material",
        numerator=50,
        denominator=100,
        rate=0.5,
        misses=("a",),
        ci_low=0.4,
        ci_high=0.6,
    )
    decision, _ = evaluate_retirement(
        weak,
        consecutive_windows_meeting=10,
        slo={"retire_material_min": 0.97, "retire_windows": 4, "reduce_material_min": 0.93},
    )
    assert decision == RETIRE_CONTINUE


def test_gate_exit_fail_closed_when_material_below_slo() -> None:
    alerta = [_ref("A1"), _ref("A2"), _ref("A3"), _ref("A4"), _ref("A5")]
    extra = [_ref("A1", platform="extra")]
    report = evaluate_recall(
        alerta_items=alerta,
        extra_items=extra,
        window_start="2026-03-01",
        window_end="2026-03-31",
        cutoff="2026-03-31T23:59:59Z",
        filters={"uf": "SC"},
        period_id="2026-03",
    )
    assert gate_exit(report) == 2
    assert report.retirement == RETIRE_CONTINUE
