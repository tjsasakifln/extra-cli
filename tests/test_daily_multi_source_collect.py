"""Tests for daily multi-source collection feeder (pack lake honesty).

Drives shipped modules:
  - scripts.ops.daily_multi_source_collect
  - scripts.collect.run_contract
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.collect.run_contract import CollectionRun, classify_terminal_status
from scripts.ops.daily_multi_source_collect import (
    CONSULTIVE_OK,
    REQUIRED_SOURCES,
    SourceFeedAssessment,
    _live_resilient_source,
    evaluate_feeder_completeness,
    map_assessment_to_terminal,
)


def test_resilient_source_success_survives_degraded_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.ops import resilient_cycle

    monkeypatch.setattr(
        resilient_cycle,
        "run_cycle",
        lambda **_kwargs: (
            1,
            {
                "status": "degraded",
                "results": {
                    "sc_compras": {
                        "status": "success",
                        "terminal_status": "success",
                        "request_completed": True,
                        "scope_complete": True,
                        "records_fetched": 2610,
                        "records_persisted": 2610,
                    }
                },
                "pending_checkpoints": 2,
            },
        ),
    )

    run = _live_resilient_source("collection-1", "sc_compras")

    assert run.terminal_status == "success"
    assert run.request_completed is True
    assert run.scope_complete is True
    assert run.records_persisted == 2610
    assert "aggregate_rc=1" in run.notes[0]


def test_resilient_source_real_partial_stays_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.ops import resilient_cycle

    monkeypatch.setattr(
        resilient_cycle,
        "run_cycle",
        lambda **_kwargs: (
            0,
            {
                "status": "healthy",
                "results": {
                    "sc_compras": {
                        "status": "partial",
                        "terminal_status": "partial",
                        "request_completed": True,
                        "scope_complete": False,
                        "records_fetched": 50,
                        "records_persisted": 50,
                    }
                },
            },
        ),
    )

    run = _live_resilient_source("collection-2", "sc_compras")

    assert run.terminal_status == "partial"
    assert run.request_completed is True
    assert run.scope_complete is False
    assert run.records_persisted == 50


def test_skip_without_proof_is_partial_never_success() -> None:
    a = SourceFeedAssessment(
        source="pncp_opportunities",
        role="required",
        level="stale",
        age_hours=100.0,
        sla_hours=24,
        row_count=10,
    )
    status, kwargs = map_assessment_to_terminal(a, skip_without_proof=True, offline=True)
    assert status == "partial"
    assert kwargs["reused_within_sla"] is False
    assert kwargs["scope_complete"] is False
    assert status not in CONSULTIVE_OK


def test_never_collected_is_failure() -> None:
    a = SourceFeedAssessment(
        source="ciga_ckan",
        role="required",
        level="never",
        sla_hours=24,
    )
    status, kwargs = map_assessment_to_terminal(a, offline=True)
    assert status == "failure"
    assert kwargs["request_completed"] is False
    assert "never" in str(kwargs.get("error") or "").lower()


def test_fresh_complete_maps_to_reused_fresh() -> None:
    a = SourceFeedAssessment(
        source="pncp_opportunities",
        role="required",
        level="fresh",
        age_hours=2.0,
        sla_hours=24,
        row_count=50,
        scope_complete=True,
        evidence="opportunity_runs/1",
    )
    status, kwargs = map_assessment_to_terminal(a, offline=True)
    assert status == "reused_fresh"
    assert kwargs["reused_within_sla"] is True
    assert kwargs["scope_complete"] is True


def test_incomplete_within_sla_is_partial_not_success() -> None:
    a = SourceFeedAssessment(
        source="ciga_ckan",
        role="required",
        level="incomplete",
        age_hours=1.0,
        sla_hours=24,
        row_count=3,
        scope_complete=False,
    )
    status, _kwargs = map_assessment_to_terminal(a, offline=True)
    assert status == "partial"
    assert status not in CONSULTIVE_OK


def test_evaluate_completeness_requires_all_required() -> None:
    ok_pncp = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    ok_pncp.finish(
        records_obtained=10,
        records_persisted=10,
        request_completed=True,
        scope_complete=True,
        reused_within_sla=True,
    )
    bad_ciga = CollectionRun.start(
        source="ciga_ckan",
        collection_id="c",
        collector_version="t",
    )
    bad_ciga.finish(
        request_completed=True,
        scope_complete=False,
        notes=["skip"],
    )
    bad_ciga.terminal_status = "partial"

    result = evaluate_feeder_completeness([ok_pncp, bad_ciga])
    assert result["complete"] is False
    assert "ciga_ckan" in result["required_failed"]
    assert "pncp_opportunities" in result["required_ok"]


def test_evaluate_completeness_all_required_ok() -> None:
    runs = []
    for src in REQUIRED_SOURCES:
        r = CollectionRun.start(source=src, collection_id="c", collector_version="t")
        r.finish(
            records_obtained=1,
            records_persisted=1,
            request_completed=True,
            scope_complete=True,
            reused_within_sla=True,
        )
        assert r.terminal_status == "reused_fresh"
        assert r.is_consultive_ok()
        runs.append(r)
    result = evaluate_feeder_completeness(runs)
    assert result["complete"] is True
    assert set(result["required_ok"]) == set(REQUIRED_SOURCES)


def test_partial_never_consultive_ok() -> None:
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        records_obtained=5,
        records_persisted=5,
        request_completed=True,
        scope_complete=False,
        error="partial pages",
    )
    assert run.terminal_status == "partial"
    assert run.is_consultive_ok() is False


def test_success_zero_incomplete_not_consultive() -> None:
    run = CollectionRun.start(
        source="ciga_ckan",
        collection_id="c",
        collector_version="t",
    )
    # Force success_zero without scope — must not be consultive
    run.terminal_status = "success_zero"
    run.scope_complete = False
    run.terminal_error = "scope incomplete"
    assert run.is_consultive_ok() is False


def test_classify_empty_without_scope_not_success() -> None:
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=False,
            source_available=True,
        )
        == "partial"
    )


def test_cli_help_entry_point() -> None:
    from scripts.ops.daily_multi_source_collect import build_parser, main

    p = build_parser()
    help_text = p.format_help()
    assert "daily" in help_text.lower() or "multi" in help_text.lower()
    assert "--offline" in help_text
    assert "--declare-only" in help_text or "--live" in help_text
    # --help exits 0 via SystemExit
    with pytest.raises(SystemExit) as ei:
        main(["--help"])
    assert ei.value.code == 0


def test_zero_confirmed_requires_entity_evidence() -> None:
    """Freshness alone never invents ZERO_CONFIRMED; evidence can."""
    from scripts.ops.multi_source_open_pack.models import BuyerEntity
    from scripts.ops.weekly_decision_artifacts import build_coverage_by_entity_source

    ent = BuyerEntity(
        entity_key="82922233",
        cnpj="82922233000100",
        cnpj8="82922233",
        name="MUNICIPIO DE FLORIANOPOLIS",
        canonical_name="MUNICIPIO DE FLORIANOPOLIS",
        municipio="FLORIANOPOLIS",
        uf="SC",
        ibge_code="4205407",
        lat=-27.6,
        lon=-48.5,
        distance_km=5.0,
        zone="core",
    )
    # Without evidence → NOT_QUERIED even if fresh
    rows = build_coverage_by_entity_source(
        entities=[ent],
        observations=[],
        freshness=[{"source": "ciga_ckan", "level": "fresh", "age_hours": 1.0, "sla_hours": 24}],
        policy={"source_roles": {"open_tenders": {"ciga_ckan": "required"}}},
    )
    assert rows[0]["result"] == "NOT_QUERIED"
    assert rows[0]["result"] != "ZERO_CONFIRMED"

    # With entity-scoped success_zero → ZERO_CONFIRMED
    rows2 = build_coverage_by_entity_source(
        entities=[ent],
        observations=[],
        freshness=[{"source": "ciga_ckan", "level": "fresh", "age_hours": 1.0, "sla_hours": 24}],
        policy={"source_roles": {"open_tenders": {"ciga_ckan": "required"}}},
        entity_source_evidence={("82922233", "ciga_ckan"): "success_zero"},
    )
    assert rows2[0]["result"] == "ZERO_CONFIRMED"


def test_module_import_and_constants() -> None:
    from scripts.ops import daily_multi_source_collect as m

    assert m.EXIT_OK == 0
    assert m.EXIT_INCOMPLETE == 2
    assert "pncp_opportunities" in m.REQUIRED_SOURCES
    assert "ciga_ckan" in m.REQUIRED_SOURCES
    assert Path(m.__file__).name == "daily_multi_source_collect.py"
