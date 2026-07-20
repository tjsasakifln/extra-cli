"""Tests for EXTRA weekly operational cycle — contract, catalog, orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.collect.run_contract import (
    CollectionRun,
    classify_terminal_status,
    new_collection_id,
)
from scripts.ops.weekly_cycle import (
    _EXTRA_UNIVERSE_ORGAO,
    EXIT_OK,
    EXIT_TECH,
    EXIT_UNRELIABLE,
    EXPECTED_UNIVERSE_200KM,
    StageResult,
    StrictReadinessPolicy,
    _build_claims_catalog,
    classify_execution_scope,
    classify_opportunity_freshness,
    compute_exit_code,
    evaluate_entity_freshness_reports,
    evaluate_readiness,
    run_weekly_cycle,
)
from scripts.quality.indicator_catalog import (
    get_indicator,
    validate_metric_claim,
)

# ---------------------------------------------------------------------------
# Collect contract
# ---------------------------------------------------------------------------


def test_new_collection_id_format() -> None:
    cid = new_collection_id("extra-weekly")
    assert cid.startswith("col-extra-weekly-")
    assert len(cid) > 20


def test_success_zero_requires_scope_complete() -> None:
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=True,
            source_available=True,
        )
        == "success_zero"
    )
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


def test_absence_of_error_is_not_success_if_request_incomplete() -> None:
    assert (
        classify_terminal_status(
            request_completed=False,
            records_fetched=0,
            records_persisted=0,
            scope_complete=False,
            source_available=True,
        )
        == "failure"
    )


def test_interrupted_is_failure() -> None:
    assert (
        classify_terminal_status(
            request_completed=False,
            records_fetched=10,
            records_persisted=5,
            scope_complete=False,
            source_available=True,
            interrupted=True,
        )
        == "failure"
    )


def test_blocked_when_source_unavailable() -> None:
    assert (
        classify_terminal_status(
            request_completed=False,
            records_fetched=0,
            records_persisted=0,
            scope_complete=False,
            source_available=False,
        )
        == "blocked"
    )


def test_reused_fresh_explicit() -> None:
    assert (
        classify_terminal_status(
            request_completed=True,
            records_fetched=0,
            records_persisted=0,
            scope_complete=True,
            source_available=True,
            reused_within_sla=True,
        )
        == "reused_fresh"
    )


def test_collection_run_finish_payload() -> None:
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="col-test",
        collector_version="test/1",
        period_start="2026-07-01",
        period_end="2026-07-07",
    )
    st = run.finish(
        records_obtained=3,
        records_persisted=3,
        request_completed=True,
        scope_complete=True,
        raw_uri="api://example",
        content_hashes=["abc"],
    )
    assert st == "success"
    d = run.to_dict()
    assert d["run_id"]
    assert d["collection_id"] == "col-test"
    assert d["payload_hash"]
    assert d["contract_version"] == "1.0"
    assert run.is_consultive_ok()


# ---------------------------------------------------------------------------
# Indicator catalog
# ---------------------------------------------------------------------------


def test_unknown_metric_fails_closed() -> None:
    with pytest.raises(KeyError):
        get_indicator("coverage_fake_95")


def test_forbidden_claim_on_proxy() -> None:
    r = validate_metric_claim(
        "contracts_ops_proxy",
        "cobertura operacional completa de 95%",
    )
    assert r["ok"] is False


def test_allowed_freshness_claim() -> None:
    r = validate_metric_claim(
        "freshness_source",
        "source data age relative to SLA",
    )
    assert r["ok"] is True


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_tech_on_validate_fail() -> None:
    stages = [StageResult(name="validate_db", status="fail", error="missing")]
    assert compute_exit_code(stages, []) == EXIT_TECH


def test_exit_blocked_on_opp_blocked() -> None:
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        request_completed=False,
        scope_complete=False,
        source_available=False,
        error="down",
    )
    stages = [
        StageResult(name="validate_db", status="ok"),
        StageResult(name="collect", status="blocked"),
        StageResult(name="intelligence", status="ok", detail={"counts": {"opportunities": 1}}),
        StageResult(name="delivery", status="ok"),
    ]
    assert compute_exit_code(stages, [run]) == 3


def _delivery_ok_detail() -> dict:
    return {
        "excel_ok": True,
        "checksums_file": "/tmp/checksums.json",
        "product_checksums": {"executive_md": {"sha256": "abc"}},
    }


def _fresh_sources() -> list[dict]:
    return [
        {
            "source": "pncp_opportunities",
            "level": "fresh",
            "age_hours": 1.0,
            "sla_hours": 48,
        },
        {
            "source": "pncp_contracts",
            "level": "fresh",
            "age_hours": 2.0,
            "sla_hours": 168,
            "row_count": 100,
        },
    ]


def _universe_ok_stage() -> StageResult:
    return StageResult(
        name="validate_db",
        status="ok",
        detail={
            "universe_200km": EXPECTED_UNIVERSE_200KM,
            "expected_universe": EXPECTED_UNIVERSE_200KM,
            "universe_version": "extra-sc-raio-200km-v1",
        },
    )


def _ok_opp_run() -> CollectionRun:
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        records_obtained=10,
        records_persisted=10,
        request_completed=True,
        scope_complete=True,
        reused_within_sla=True,
    )
    return run


def _ok_contracts_run() -> CollectionRun:
    run = CollectionRun.start(
        source="pncp_contracts",
        collection_id="c",
        collector_version="t",
        mode="reuse",
    )
    run.finish(
        records_obtained=100,
        records_persisted=100,
        request_completed=True,
        scope_complete=False,
        reused_within_sla=True,
        raw_uri="db://pncp_supplier_contracts",
    )
    return run


def _consultive_ok_stages() -> list[StageResult]:
    return [
        StageResult(name="validate_config", status="ok"),
        _universe_ok_stage(),
        StageResult(name="freshness", status="ok", detail={"sources": _fresh_sources()}),
        StageResult(name="collect", status="ok"),
        StageResult(name="process", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 5, "contracts": 10}},
        ),
        StageResult(name="delivery", status="ok", detail=_delivery_ok_detail()),
    ]


def test_exit_ok_with_reused_and_products() -> None:
    """Fully valid consultive state → EXIT_OK."""
    stages = _consultive_ok_stages()
    runs = [_ok_opp_run(), _ok_contracts_run()]
    ev = evaluate_readiness(
        stages,
        runs,
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_OK
    assert ev.consultive_ready is True
    assert ev.delivery_completed is True
    assert ev.blockers == ()


def test_exit_unreliable_empty_without_success_zero() -> None:
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
    stages = [
        _universe_ok_stage(),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 0}},
        ),
        StageResult(name="delivery", status="ok", detail=_delivery_ok_detail()),
    ]
    assert compute_exit_code(stages, [run], strict=True) == EXIT_UNRELIABLE


# ---------------------------------------------------------------------------
# Adversarial reliability (PR review blockers)
# ---------------------------------------------------------------------------


def test_partial_status_never_classifies_as_fresh() -> None:
    """A partial PNCP run within SLA must not become freshness=fresh."""
    assert (
        classify_opportunity_freshness(
            status="partial",
            age_hours=1.0,
            sla_hours=48,
            scope_complete=False,
        )
        == "incomplete"
    )
    assert (
        classify_opportunity_freshness(
            status="partial",
            age_hours=0.5,
            sla_hours=48,
            scope_complete=True,  # even if flag wrong, partial status wins
        )
        == "incomplete"
    )


def test_complete_status_within_sla_is_fresh() -> None:
    assert (
        classify_opportunity_freshness(
            status="completed",
            age_hours=10.0,
            sla_hours=48,
            scope_complete=True,
        )
        == "fresh"
    )


def test_completed_with_scope_incomplete_is_not_fresh() -> None:
    assert (
        classify_opportunity_freshness(
            status="completed",
            age_hours=1.0,
            sla_hours=48,
            scope_complete=False,
        )
        == "incomplete"
    )


def test_partial_collect_never_exit_ok_even_with_products() -> None:
    """Partial critical collection must not wash to EXIT_OK under strict."""
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        records_obtained=50,
        records_persisted=20,
        request_completed=True,
        scope_complete=False,
        error="some modalidades failed",
    )
    assert run.terminal_status == "partial"
    stages = [
        _universe_ok_stage(),
        StageResult(name="collect", status="warn"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 40}},
        ),
        StageResult(name="delivery", status="ok", detail=_delivery_ok_detail()),
    ]
    assert compute_exit_code(stages, [run], strict=True) == EXIT_UNRELIABLE
    # also non-strict: partial is never consultively OK
    assert compute_exit_code(stages, [run], strict=False) == EXIT_UNRELIABLE


def test_strict_missing_excel_is_nonzero() -> None:
    stages = [
        _universe_ok_stage(),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 5}},
        ),
        StageResult(
            name="delivery",
            status="fail",
            detail={"excel_ok": False, "product_checksums": {}},
            error="Excel generation failed",
        ),
    ]
    assert (
        compute_exit_code(
            stages,
            [_ok_opp_run(), _ok_contracts_run()],
            strict=True,
            freshness=_fresh_sources(),
            execution_scope="full",
        )
        == EXIT_TECH
    )


def test_strict_delivery_ok_without_excel_flag_is_unreliable() -> None:
    """Even if status text is ok, missing excel_ok fails strict."""
    stages = [
        _universe_ok_stage(),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 5}},
        ),
        StageResult(
            name="delivery",
            status="ok",
            detail={"excel_ok": False, "checksums_file": "x"},
        ),
    ]
    assert (
        compute_exit_code(
            stages,
            [_ok_opp_run(), _ok_contracts_run()],
            strict=True,
            freshness=_fresh_sources(),
            execution_scope="full",
        )
        == EXIT_UNRELIABLE
    )


# ---------------------------------------------------------------------------
# Strict fail-closed readiness (ARCH-RESET-RECOVERY / PR #59 regression)
# ---------------------------------------------------------------------------


def _pr59_live_stages() -> list[StageResult]:
    """Stages reconstructed from PR #59 live-weekly-collect/manifest.json."""
    return [
        StageResult(name="validate_config", status="ok"),
        StageResult(
            name="validate_db",
            status="warn",
            detail={
                "universe_200km": 0,
                "expected_universe": EXPECTED_UNIVERSE_200KM,
            },
            error="universe_200km=0 != 1093 (scope drift)",
        ),
        StageResult(
            name="freshness",
            status="warn",
            detail={
                "sources": [
                    {
                        "source": "pncp_opportunities",
                        "level": "never",
                        "sla_hours": 48,
                        "age_hours": None,
                        "indicator": "freshness_source",
                    },
                    {
                        "source": "pncp_contracts",
                        "level": "never",
                        "sla_hours": 168,
                        "indicator": "freshness_source",
                    },
                ]
            },
        ),
        StageResult(name="collect", status="ok"),
        StageResult(name="process", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={
                "counts": {
                    "opportunities": 1,
                    "contracts": 0,
                    "competitors": 0,
                    "orgaos": 1,
                }
            },
        ),
        StageResult(name="delivery", status="ok", detail=_delivery_ok_detail()),
    ]


def _pr59_live_runs() -> list[CollectionRun]:
    opp = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="col-pr59",
        collector_version="weekly-cycle/1.0",
    )
    opp.finish(
        records_obtained=32,
        records_persisted=0,
        request_completed=True,
        scope_complete=True,
    )
    assert opp.terminal_status == "success"
    ct = CollectionRun.start(
        source="pncp_contracts",
        collection_id="col-pr59",
        collector_version="weekly-cycle/1.0",
        mode="reuse",
    )
    ct.finish(
        request_completed=False,
        scope_complete=False,
        source_available=True,
        error="no contracts in lake",
    )
    assert ct.terminal_status == "failure"
    return [opp, ct]


def _pr59_freshness() -> list[dict]:
    return [
        {
            "source": "pncp_opportunities",
            "level": "never",
            "sla_hours": 48,
            "age_hours": None,
        },
        {"source": "pncp_contracts", "level": "never", "sla_hours": 168},
    ]


def test_pr59_live_manifest_must_not_exit_ok() -> None:
    """Regression: PR #59 live proof had exit_code=0 with empty universe,
    freshness never, contracts failure, limit=5 sample — must be non-zero.
    """
    stages = _pr59_live_stages()
    runs = _pr59_live_runs()
    freshness = _pr59_freshness()
    # limit=5 → sample
    assert classify_execution_scope(offline=False, limit=5) == "sample"

    ev = evaluate_readiness(
        stages,
        runs,
        strict=True,
        freshness=freshness,
        execution_scope="sample",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert ev.consultive_ready is False
    assert ev.delivery_completed is True  # delivery alone is not enough
    assert "universe_missing_or_drifted" in ev.blockers
    assert "required_source_failed:pncp_contracts" in ev.blockers
    assert "freshness_not_valid" in ev.blockers
    assert "execution_scope_not_full:sample" in ev.blockers


def test_universe_zero_blocks_strict() -> None:
    stages = _consultive_ok_stages()
    stages[1] = StageResult(
        name="validate_db",
        status="warn",
        detail={"universe_200km": 0, "expected_universe": EXPECTED_UNIVERSE_200KM},
    )
    ev = evaluate_readiness(
        stages,
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert ev.consultive_ready is False
    assert "universe_missing_or_drifted" in ev.blockers


def test_universe_divergent_blocks_strict() -> None:
    stages = _consultive_ok_stages()
    stages[1] = StageResult(
        name="validate_db",
        status="warn",
        detail={"universe_200km": 500, "expected_universe": EXPECTED_UNIVERSE_200KM},
    )
    ev = evaluate_readiness(
        stages,
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code != EXIT_OK
    assert "universe_missing_or_drifted" in ev.blockers


def test_freshness_never_blocks_when_reusing() -> None:
    stages = _consultive_ok_stages()
    fr = [
        {"source": "pncp_opportunities", "level": "never", "age_hours": None},
        {"source": "pncp_contracts", "level": "never", "age_hours": None},
    ]
    # Both sources reused_fresh with never freshness
    ev = evaluate_readiness(
        stages,
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=fr,
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "freshness_not_valid" in ev.blockers


def test_freshness_unknown_blocks() -> None:
    # Live success on opp supersedes pre-freshness; contracts reused needs fresh
    opp = CollectionRun.start(
        source="pncp_opportunities", collection_id="c", collector_version="t"
    )
    opp.finish(
        records_obtained=1,
        records_persisted=1,
        request_completed=True,
        scope_complete=True,
    )
    fr = [
        {"source": "pncp_opportunities", "level": "unknown", "age_hours": None},
        {"source": "pncp_contracts", "level": "unknown", "age_hours": None},
    ]
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [opp, _ok_contracts_run()],
        strict=True,
        freshness=fr,
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "freshness_not_valid" in ev.blockers


def test_freshness_stale_blocks_reuse() -> None:
    fr = [
        {"source": "pncp_opportunities", "level": "stale", "age_hours": 100.0},
        {"source": "pncp_contracts", "level": "stale", "age_hours": 200.0},
    ]
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=fr,
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "freshness_not_valid" in ev.blockers


def test_freshness_unreliable_blocks() -> None:
    fr = [
        {"source": "pncp_opportunities", "level": "unreliable", "age_hours": 1.0},
        {"source": "pncp_contracts", "level": "fresh", "age_hours": 1.0},
    ]
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=fr,
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "freshness_not_valid" in ev.blockers


def test_required_contracts_failure_blocks() -> None:
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(
        request_completed=False,
        scope_complete=False,
        error="no contracts in lake",
    )
    assert ct.terminal_status == "failure"
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), ct],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "required_source_failed:pncp_contracts" in ev.blockers


def test_required_opportunities_partial_blocks() -> None:
    opp = CollectionRun.start(
        source="pncp_opportunities", collection_id="c", collector_version="t"
    )
    opp.finish(
        records_obtained=50,
        records_persisted=20,
        request_completed=True,
        scope_complete=False,
        error="partial",
    )
    assert opp.terminal_status == "partial"
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [opp, _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "required_source_failed:pncp_opportunities" in ev.blockers


def test_limit_sample_not_consultive_ready() -> None:
    assert classify_execution_scope(offline=False, limit=5) == "sample"
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="sample",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert ev.consultive_ready is False
    assert "execution_scope_not_full:sample" in ev.blockers


def test_fixture_offline_not_consultive_ready() -> None:
    assert classify_execution_scope(offline=True, limit=50) == "fixture"
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="fixture",
    )
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False


def test_success_zero_incomplete_scope_blocks() -> None:
    opp = CollectionRun.start(
        source="pncp_opportunities", collection_id="c", collector_version="t"
    )
    # Manually craft success_zero with incomplete scope (invalid by contract)
    opp.finish(
        records_obtained=0,
        records_persisted=0,
        request_completed=True,
        scope_complete=True,
    )
    assert opp.terminal_status == "success_zero"
    opp.scope_complete = False  # invalidate after classify
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [opp, _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE
    assert any("success_zero" in b for b in ev.blockers)


def test_delivery_ok_with_failed_source_not_exit_ok() -> None:
    """Delivery artifacts must not compensate for required source failure."""
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(request_completed=False, scope_complete=False, error="fail")
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), ct],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.delivery_completed is True
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False


def test_quality_green_collection_incomplete_not_exit_ok() -> None:
    """Record-level quality ok must not hide failed collection."""
    stages = _consultive_ok_stages()
    # quality ok but contracts failed
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(request_completed=False, scope_complete=False, error="empty")
    ev = evaluate_readiness(
        stages,
        [_ok_opp_run(), ct],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_UNRELIABLE


def test_timestamp_absent_age_hours_none_not_zero() -> None:
    """age_hours=None must not be coerced to 0.0 (freshness adapter safety)."""
    level = classify_opportunity_freshness(
        status="completed",
        age_hours=None,
        sla_hours=48,
        scope_complete=True,
    )
    assert level == "unknown"
    assert level != "fresh"


def test_complete_package_without_operational_readiness() -> None:
    """Full delivery with operational blockers → not consultive_ready."""
    stages = _pr59_live_stages()
    ev = evaluate_readiness(
        stages,
        _pr59_live_runs(),
        strict=True,
        freshness=_pr59_freshness(),
        execution_scope="full",  # even full scope can't fix empty universe
    )
    assert ev.delivery_completed is True
    assert ev.execution_completed is True
    assert ev.consultive_ready is False
    assert ev.exit_code == EXIT_UNRELIABLE


def test_fully_valid_execution_exit_ok() -> None:
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
    )
    assert ev.exit_code == EXIT_OK
    assert ev.consultive_ready is True
    assert not ev.blockers


def test_degraded_allowed_but_not_consultive() -> None:
    """Degraded/diagnostic mode may complete, never consultive_ready."""
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="diagnostic",
    )
    assert ev.consultive_ready is False
    assert ev.exit_code == EXIT_UNRELIABLE
    assert "execution_scope_not_full:diagnostic" in ev.blockers


def test_hours_since_none_preserved() -> None:
    from scripts.ops.weekly_cycle import _hours_since

    assert _hours_since(None) is None


def test_classify_execution_scope_production_limit() -> None:
    assert classify_execution_scope(offline=False, limit=50) == "full"
    assert classify_execution_scope(offline=False, limit=49) == "sample"
    assert classify_execution_scope(offline=True, limit=1000) == "fixture"


def test_contract_claim_does_not_use_source_id_as_run_id() -> None:
    collection_id = "col-x"
    ct_run = CollectionRun.start(
        source="pncp_contracts",
        collection_id=collection_id,
        collector_version="t",
        run_id="cycle-ct-1",
    )
    ct_run.finish(
        records_obtained=1,
        records_persisted=1,
        request_completed=True,
        scope_complete=False,
        reused_within_sla=True,
    )
    claims = _build_claims_catalog(
        {
            "opportunities": [],
            "contracts": [
                {
                    "contrato_id": "c-1",
                    "source_id": "NOT-A-RUN-ID",
                    "orgao_nome": "X",
                    "fornecedor_nome": "Y",
                    "valor_total": 1,
                    "valor_tipo": "valor_contratado",
                    "cycle_collection_id": collection_id,
                    "cycle_run_id": "cycle-ct-1",
                    "source_record_run_id": None,
                    "source_record_id": "NOT-A-RUN-ID",
                    "scope": "extra_universe_200km",
                }
            ],
            "competitors": [],
        },
        [ct_run],
        [],
        collection_id=collection_id,
    )
    ct = next(c for c in claims if c["kind"] == "contract")
    assert ct["cycle_run_id"] == "cycle-ct-1"
    assert ct["source_record_run_id"] in (None, "")
    assert ct["source_record_id"] == "NOT-A-RUN-ID"
    assert ct["source_record_run_id"] != "NOT-A-RUN-ID"


# ---------------------------------------------------------------------------
# Claims provenance (AC3)
# ---------------------------------------------------------------------------


def test_claims_include_material_rows_with_cycle_collection() -> None:
    """Opportunities, contracts and competitors link to this cycle collection_id."""
    collection_id = "col-test-extra"
    opp_run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id=collection_id,
        collector_version="t",
        run_id="cycle-opp-run-1",
    )
    opp_run.finish(
        records_obtained=1,
        records_persisted=1,
        request_completed=True,
        scope_complete=True,
        reused_within_sla=True,
    )
    ct_run = CollectionRun.start(
        source="pncp_contracts",
        collection_id=collection_id,
        collector_version="t",
        run_id="cycle-ct-run-1",
    )
    ct_run.finish(
        records_obtained=10,
        records_persisted=10,
        request_completed=True,
        scope_complete=False,
        reused_within_sla=True,
    )
    intel = {
        "opportunities": [
            {
                "id": 42,
                "source": "pncp",
                "source_id": "x",
                "numero_controle_pncp": "SC-1",
                "orgao_nome": "PREFEITURA DEMO",
                "ranking_effective": "REVIEW",
                "valor_estimado": 1000,
                "valor_tipo": "estimado",
                "run_id": 30,  # historical source record — must NOT replace cycle ids
                "cycle_collection_id": collection_id,
                "cycle_run_id": "cycle-opp-run-1",
                "source_record_run_id": 30,
            }
        ],
        "contracts": [
            {
                "contrato_id": "c-9",
                "orgao_nome": "ORGAO U",
                "fornecedor_nome": "FORN",
                "valor_total": 500,
                "valor_tipo": "valor_contratado",
                "source": "pncp",
                "cycle_collection_id": collection_id,
                "cycle_run_id": "cycle-ct-run-1",
                "scope": "extra_universe_200km",
            }
        ],
        "competitors": [
            {
                "fornecedor_cnpj": "11222333000144",
                "fornecedor_nome": "FORN SA",
                "n_contratos": 3,
                "soma_valor_contratado": 900,
                "valor_tipo": "soma_valor_contratado_nao_pago",
                "cycle_collection_id": collection_id,
                "cycle_run_id": "cycle-ct-run-1",
                "scope": "extra_universe_200km",
            }
        ],
    }
    claims = _build_claims_catalog(
        intel,
        [opp_run, ct_run],
        [{"source": "pncp_opportunities", "level": "fresh", "age_hours": 1, "sla_hours": 48}],
        collection_id=collection_id,
    )
    kinds = {c["kind"] for c in claims}
    assert "opportunity" in kinds
    assert "contract" in kinds
    assert "competitor" in kinds
    assert "collection_run" in kinds
    assert "freshness" in kinds

    opp_claims = [c for c in claims if c["kind"] == "opportunity"]
    assert len(opp_claims) == 1
    assert opp_claims[0]["collection_id"] == collection_id
    assert opp_claims[0]["cycle_run_id"] == "cycle-opp-run-1"
    assert opp_claims[0]["source_record_run_id"] == 30
    assert opp_claims[0]["normalized_table"] == "opportunity_intel"
    assert opp_claims[0]["product"]

    ct_claims = [c for c in claims if c["kind"] == "contract"]
    assert ct_claims[0]["collection_id"] == collection_id
    assert ct_claims[0]["cycle_run_id"] == "cycle-ct-run-1"
    assert ct_claims[0]["normalized_table"] == "pncp_supplier_contracts"
    assert ct_claims[0]["scope"] == "extra_universe_200km"

    comp = [c for c in claims if c["kind"] == "competitor"]
    assert comp[0]["collection_id"] == collection_id
    assert comp[0]["normalized_id"] == "11222333000144"


def test_extra_universe_scope_sql_targets_raio_200km() -> None:
    """Contracts/competitors must filter Extra universe + SC — not national LIMIT alone."""
    sql = _EXTRA_UNIVERSE_ORGAO
    assert "sc_public_entities" in sql
    assert "raio_200km" in sql
    assert "orgao_cnpj_8" in sql
    assert "c.uf = 'SC'" in sql or 'c.uf = "SC"' in sql or "uf = 'SC'" in sql


def test_identity_pick_match_rejects_cross_root() -> None:
    from scripts.entity_identity.pncp_orgao_resolve import pick_match

    hit = pick_match(
        "12345678",
        "PREFEITURA MUNICIPAL DE EXEMPLO",
        [
            {
                "cnpj": "99999999000199",
                "razaoSocial": "PREFEITURA MUNICIPAL DE EXEMPLO",
            }
        ],
    )
    assert hit is None


# ---------------------------------------------------------------------------
# Offline cycle (real DB only — never under autouse mock)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_weekly_cycle_offline_skip_collect(tmp_path: Path) -> None:
    """Offline+skip path produces manifest — requires real DB (REQUIRE_REAL_DB=1)."""
    import os

    # conftest autouse mock is active unless integration + REQUIRE_REAL_DB=1
    if os.getenv("REQUIRE_REAL_DB") != "1":
        pytest.skip("Requires REQUIRE_REAL_DB=1 (real PostgreSQL; mock breaks manifest)")

    dsn = os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://test:test@127.0.0.1:5433/extra_test",
    )
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.close()
    except Exception:
        pytest.skip("PostgreSQL not available")

    out = tmp_path / "weekly"
    report = run_weekly_cycle(
        dsn=dsn,
        output_dir=out,
        strict=True,
        skip_collect=True,
        offline=True,
        limit=10,
    )
    assert report.cycle_id
    assert report.collection_id
    assert (out / "manifest.json").exists()
    assert (out / "executive_summary.md").exists()
    assert (out / "opportunities.csv").exists()
    assert (out / "claims_provenance.csv").exists()
    # AC3: claims file must mention contracts or competitors when lake has data
    claims_text = (out / "claims_provenance.csv").read_text(encoding="utf-8")
    assert "collection_id" in claims_text or "cycle_run_id" in claims_text
    assert report.human_accept.get("status") == "PENDING_HUMAN"
    assert "LOCAL_READY" in report.claims_forbidden
    assert report.exit_code in {0, 2, 3}


# ---------------------------------------------------------------------------
# Entity-level freshness reports (ADR-028 / ENTITY-FRESHNESS-01)
# ---------------------------------------------------------------------------


def test_strict_rejects_incomplete_entity_freshness_reports() -> None:
    """Strict mode must fail-closed when dual entity freshness reports are incomplete."""
    incomplete = {
        "capability": "notices_or_bids",
        "entities": [{"entity_id": "only-one", "capability": "notices_or_bids"}],
        "covered": 0,
        "uncovered": 1,
        "unique_entity_count": 1,
    }
    blockers = evaluate_entity_freshness_reports(
        editais_report=incomplete,
        contracts_report=None,
    )
    assert blockers
    assert any("missing" in b or "cardinality" in b or "unique" in b for b in blockers)

    policy = StrictReadinessPolicy(require_entity_freshness_reports=True)
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
        policy=policy,
        entity_freshness_reports={
            "notices_or_bids": incomplete,
            "contracts": incomplete,
        },
    )
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False
    assert ev.blockers


def test_strict_rejects_missing_entity_freshness_when_required() -> None:
    policy = StrictReadinessPolicy(require_entity_freshness_reports=True)
    ev = evaluate_readiness(
        _consultive_ok_stages(),
        [_ok_opp_run(), _ok_contracts_run()],
        strict=True,
        freshness=_fresh_sources(),
        execution_scope="full",
        policy=policy,
        entity_freshness_reports=None,
    )
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False
    assert any("freshness_report_missing" in b for b in ev.blockers)


def test_pr59_false_green_regression() -> None:
    """Alias for AM-08: universe=0, freshness=never, contracts=failure, limit=5, Excel ok."""
    stages = _pr59_live_stages()
    runs = _pr59_live_runs()
    freshness = _pr59_freshness()
    ev = evaluate_readiness(
        stages,
        runs,
        strict=True,
        freshness=freshness,
        execution_scope="sample",
    )
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False
    assert len(ev.blockers) > 0
