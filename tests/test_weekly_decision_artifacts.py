"""Regressão do pacote decisório semanal multi-fonte (PDF obrigatório + frota)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops.multi_source_open_pack.db_loaders import LineageSelectionError
from scripts.ops.multi_source_open_pack.models import BuyerEntity, SourceObservation
from scripts.ops.weekly_decision_artifacts import (
    CANONICAL_N,
    RESULT_STATES,
    build_coverage_by_entity_source,
    is_engineering_opportunity,
    select_opportunity_lineage,
)


def test_live_collection_selects_only_its_persisted_source_run() -> None:
    selected = select_opportunity_lineage(
        collection_id="cycle-20260812",
        runs=[
            SimpleNamespace(
                source="pncp_opportunities",
                collection_id="cycle-20260812",
                terminal_status="success",
                records_persisted=1732,
                parameters={
                    "opportunity_runs_id": 501,
                    "external_run_id": "weekly-cycle-20260812",
                },
            )
        ],
        freshness=[],
    )

    assert selected.source_run_id == 501
    assert selected.external_run_id == "weekly-cycle-20260812"
    assert selected.expected_records == 1732
    assert selected.mode == "persisted"


def test_reuse_records_prior_run_and_freshness_proof() -> None:
    selected = select_opportunity_lineage(
        collection_id="cycle-20260812",
        runs=[
            SimpleNamespace(
                source="pncp_opportunities",
                collection_id="cycle-20260812",
                terminal_status="reused_fresh",
                records_persisted=1732,
                raw_uri="db://opportunity_runs/500",
            )
        ],
        freshness=[
            {
                "source": "pncp_opportunities",
                "level": "fresh",
                "last_run_id": 500,
                "external_run_id": "weekly-cycle-20260811",
                "age_hours": 2.25,
                "sla_hours": 24,
            }
        ],
    )

    assert selected.source_run_id == 500
    assert selected.external_run_id == "weekly-cycle-20260811"
    assert selected.mode == "reused"
    assert selected.freshness_hours == 2.25


def test_reuse_of_different_or_stale_run_is_rejected() -> None:
    run = SimpleNamespace(
        source="pncp_opportunities",
        collection_id="cycle-20260812",
        terminal_status="reused_fresh",
        records_persisted=1732,
        raw_uri="db://opportunity_runs/500",
    )

    with pytest.raises(LineageSelectionError, match="differs"):
        select_opportunity_lineage(
            collection_id="cycle-20260812",
            runs=[run],
            freshness=[
                {
                    "source": "pncp_opportunities",
                    "level": "fresh",
                    "last_run_id": 499,
                    "external_run_id": "weekly-cycle-20260810",
                    "age_hours": 2,
                    "sla_hours": 24,
                }
            ],
        )


class TestFleetFalsePositiveRegression:
    """Audit finding: manutenção de frota classificada como engenharia."""

    @pytest.mark.parametrize(
        "objeto",
        [
            "Manutenção da frota de veículos automotores",
            "manutenção de frota municipal",
            "Contratação de empresa para manutenção da frota veicular",
            "Serviços de manutenção preventiva e corretiva da frota de veículos",
            "Manutenção de frota de veículos leves e pesados do município",
        ],
    )
    def test_fleet_maintenance_is_not_engineering(self, objeto: str) -> None:
        assert is_engineering_opportunity(objeto) is False

    def test_pavimentacao_remains_engineering(self) -> None:
        assert is_engineering_opportunity(
            "Execução de pavimentação asfáltica de vias urbanas"
        )


class TestCoverageMatrixHonesty:
    def test_all_entities_published_with_result_vocab(self) -> None:
        entities = [
            BuyerEntity(
                entity_key=f"{i:08d}",
                cnpj=f"{i:08d}000100",
                cnpj8=f"{i:08d}",
                name=f"PREFEITURA {i}",
                canonical_name=f"PREFEITURA {i}",
                municipio="FLORIANOPOLIS",
                uf="SC",
                ibge_code="4205407",
                lat=-27.6,
                lon=-48.5,
                distance_km=5.0,
                zone="core",
            )
            for i in range(5)
        ]
        obs = [
            SourceObservation(
                observation_id="pncp:1",
                fonte="pncp",
                fonte_papel="required",
                id_externo="1",
                orgao="PREFEITURA 0",
                orgao_cnpj="00000000000100",
                municipio="FLORIANOPOLIS",
                uf="SC",
                objeto="pavimentacao",
                modalidade="Pregão",
                valor_estimado=1.0,
                data_publicacao="2026-07-01",
                data_abertura="",
                data_encerramento="2026-08-01",
                url="https://pncp.gov.br/app/editais/x",
                status_fonte="open",
                categoria_ato="edital_aberto",
                entity_key="00000000",
                in_universe=True,
                is_active_dispute=True,
                event_type="edital",
            )
        ]
        rows = build_coverage_by_entity_source(
            entities=entities,
            observations=obs,
            freshness=[
                {
                    "source": "pncp_opportunities",
                    "level": "fresh",
                    "age_hours": 1.0,
                    "sla_hours": 24,
                }
            ],
            policy={
                "source_roles": {
                    "open_tenders": {
                        "pncp": "required",
                        "ciga_ckan": "required",
                    }
                }
            },
        )
        # 5 entities × 2 sources
        assert len(rows) == 10
        assert any(r["result"] == "FOUND" for r in rows)
        assert any(r["result"] == "NOT_QUERIED" for r in rows)
        for r in rows:
            assert r["result"] in RESULT_STATES

    def test_found_is_not_confused_with_zero_confirmed(self) -> None:
        """Without entity-scoped success_zero ledger, fresh+empty = NOT_QUERIED."""
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
        rows = build_coverage_by_entity_source(
            entities=[ent],
            observations=[],
            freshness=[
                {
                    "source": "pncp_opportunities",
                    "level": "fresh",
                    "age_hours": 2.0,
                    "sla_hours": 24,
                }
            ],
            policy={"source_roles": {"open_tenders": {"pncp": "required"}}},
        )
        assert len(rows) == 1
        assert rows[0]["result"] == "NOT_QUERIED"
        assert rows[0]["result"] != "ZERO_CONFIRMED"
        assert rows[0]["result"] != "FOUND"


class TestStrictExitRequiresPdf:
    def test_exit_unreliable_without_pdf(self) -> None:
        from scripts.collect.run_contract import CollectionRun
        from scripts.ops.weekly_cycle import (
            EXIT_UNRELIABLE,
            StageResult,
            compute_exit_code,
        )

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
        contracts = CollectionRun.start(
            source="pncp_contracts",
            collection_id="c",
            collector_version="t",
        )
        contracts.finish(
            records_obtained=100,
            records_persisted=100,
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
                detail={
                    "excel_ok": True,
                    "pdf_ok": False,
                    "pdf_status": "RESIDUAL_NOT_GENERATED",
                    "checksums_file": "/tmp/x",
                    "product_checksums": {"a": {"sha256": "b"}},
                },
            ),
        ]
        assert compute_exit_code(stages, [run, contracts], strict=True) == EXIT_UNRELIABLE


def test_canonical_n_constant() -> None:
    assert CANONICAL_N == 1093


def test_universe_seed_count() -> None:
    from scripts.ops.multi_source_open_pack.universe import load_universe

    root = Path(__file__).resolve().parents[1]
    entities = load_universe(root / "config" / "target_entities_200km.csv")
    assert len(entities) == 1093
