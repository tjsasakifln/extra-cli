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
    EXIT_OK,
    EXIT_TECH,
    EXIT_UNRELIABLE,
    StageResult,
    compute_exit_code,
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


def test_exit_ok_with_reused_and_products() -> None:
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
    stages = [
        StageResult(name="validate_db", status="ok"),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 5}},
        ),
        StageResult(name="delivery", status="ok"),
    ]
    assert compute_exit_code(stages, [run]) == EXIT_OK


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
        StageResult(name="validate_db", status="ok"),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 0}},
        ),
        StageResult(name="delivery", status="ok"),
    ]
    assert compute_exit_code(stages, [run]) == EXIT_UNRELIABLE


# ---------------------------------------------------------------------------
# Offline cycle (uses real DB if available)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_weekly_cycle_offline_skip_collect(tmp_path: Path) -> None:
    """Offline+skip path produces manifest and exit code without network collect."""
    import os

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
    assert report.human_accept.get("status") == "PENDING_HUMAN"
    assert "LOCAL_READY" in report.claims_forbidden
    # offline with data in lake should typically be 0 or 2 depending on lake
    assert report.exit_code in {0, 2, 3}


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
