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
    StageResult,
    _build_claims_catalog,
    classify_opportunity_freshness,
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


def _delivery_ok_detail() -> dict:
    return {
        "excel_ok": True,
        "checksums_file": "/tmp/checksums.json",
        "product_checksums": {"executive_md": {"sha256": "abc"}},
    }


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
        StageResult(name="delivery", status="ok", detail=_delivery_ok_detail()),
    ]
    assert compute_exit_code(stages, [run], strict=True) == EXIT_OK


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
        StageResult(name="validate_db", status="ok"),
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
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        records_obtained=1,
        records_persisted=1,
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
        StageResult(
            name="delivery",
            status="fail",
            detail={"excel_ok": False, "product_checksums": {}},
            error="Excel generation failed",
        ),
    ]
    assert compute_exit_code(stages, [run], strict=True) == EXIT_TECH


def test_strict_delivery_ok_without_excel_flag_is_unreliable() -> None:
    """Even if status text is ok, missing excel_ok fails strict."""
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="c",
        collector_version="t",
    )
    run.finish(
        records_obtained=1,
        records_persisted=1,
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
        StageResult(
            name="delivery",
            status="ok",
            detail={"excel_ok": False, "checksums_file": "x"},
        ),
    ]
    assert compute_exit_code(stages, [run], strict=True) == EXIT_UNRELIABLE


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
