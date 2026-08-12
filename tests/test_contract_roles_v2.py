"""Canonical contract buyer/supplier role separation (#313)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from scripts.contracts_identity import normalize_supplier_identity
from scripts.opportunity_intel.competitive_intel_validation import (
    _HHI_FALLBACK,
    _HHI_QUERY,
    _MARKET_SHARE_FALLBACK,
    _MARKET_SHARE_QUERY,
    _SUPPLIER_RANKING_FALLBACK,
    _SUPPLIER_RANKING_QUERY,
)

ROOT = Path(__file__).resolve().parents[1]


def _valid_cnpj_for_root(root: str) -> str:
    base = root + "0001"

    def digit(value: str, weights: list[int]) -> str:
        remainder = sum(
            int(number) * weight
            for number, weight in zip(value, weights, strict=True)
        ) % 11
        return str(0 if remainder < 2 else 11 - remainder)

    first = digit(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    partial = base + first
    return partial + digit(partial, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])


def _insert_role_test_entities(cursor, count: int) -> list[dict]:
    entities = []
    for index in range(count):
        root = f"91{index:06d}"
        cursor.execute(
            """
            INSERT INTO sc_public_entities (razao_social, cnpj_8, municipio, is_active)
            VALUES (%s, %s, 'FLORIANOPOLIS', TRUE)
            RETURNING id, cnpj_8
            """,
            (f"Entidade teste de papel {index}", root),
        )
        entities.append(dict(cursor.fetchone()))
    return entities


def test_v2_is_versioned_and_v1_is_explicitly_deprecated() -> None:
    migration = (ROOT / "db/migrations/077_contract_roles_canonical_v2.sql").read_text(
        encoding="utf-8"
    )
    consumer = (
        ROOT / "scripts/opportunity_intel/competitive_intel_validation.py"
    ).read_text(encoding="utf-8")

    assert "CREATE OR REPLACE VIEW public.v_contracts_canonical_v2" in migration
    assert "CREATE OR REPLACE VIEW public.v_value_observations_canonical_v2" in migration
    assert "DEPRECATED v1" in migration
    assert "contract.orgao_cnpj AS buyer_cnpj" in migration
    assert "contract.fornecedor_cnpj AS supplier_cnpj" in migration
    assert "supplier_identity_id" in migration
    assert "v_contracts_canonical_v2" in consumer
    assert not re.search(r"v_contracts_canonical(?!_v2)\b", consumer)


def test_match_ledger_has_run_reasons_confidence_and_query_indexes() -> None:
    migration = (ROOT / "db/migrations/077_contract_roles_canonical_v2.sql").read_text(
        encoding="utf-8"
    )

    for field in (
        "buyer_match_method",
        "buyer_match_confidence",
        "buyer_reason_codes",
        "supplier_match_method",
        "supplier_match_confidence",
        "supplier_reason_codes",
        "match_run_id",
        "snapshot_id",
    ):
        assert field in migration
    for index in (
        "idx_contract_roles_buyer",
        "idx_contract_roles_supplier",
        "idx_contract_roles_snapshot",
    ):
        assert index in migration
    assert "contract_id                 TEXT PRIMARY KEY" in migration


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("REQUIRE_TEST_DB") != "1",
    reason="Set REQUIRE_TEST_DB=1 to run adversarial role test",
)
def test_adversarial_supplier_root_cannot_become_buyer() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv(
        "TEST_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cursor:
            entities = _insert_role_test_entities(cursor, 2)
            buyer, supplier_root_entity = entities
            buyer_cnpj = _valid_cnpj_for_root(str(buyer["cnpj_8"]))
            supplier_cnpj = _valid_cnpj_for_root(str(supplier_root_entity["cnpj_8"]))
            supplier = normalize_supplier_identity(supplier_cnpj, declared_type="PJ")
            record = {
                "contrato_id": "test-313-adversarial-role",
                "orgao_cnpj": buyer_cnpj,
                "orgao_nome": "Comprador adversarial",
                "fornecedor_cnpj": supplier_cnpj,
                "fornecedor_nome": "Fornecedor adversarial",
                **supplier.to_record_fields(),
                "data_publicacao": "2026-08-12",
                "source": "pncp",
                "source_id": "test-313-adversarial-source",
            }
            cursor.execute(
                "SELECT set_config('extra.contract_role_run_id', %s, true)",
                ("test-313-role-run",),
            )
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([record]),),
            )
            cursor.execute(
                """
                SELECT * FROM v_contracts_canonical_v2
                WHERE contrato_id = %s
                """,
                (record["contrato_id"],),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["buyer_entity_id"] == buyer["id"]
            assert row["buyer_entity_id"] != supplier_root_entity["id"]
            assert row["buyer_entity_cnpj_8"] == buyer["cnpj_8"]
            assert row["supplier_cnpj"] == supplier_cnpj
            assert row["supplier_identity_id"].startswith("supplier:cnpj:")
            assert row["buyer_match_method"] == "orgao_cnpj8_exact"
            assert row["supplier_match_method"] == "typed_identifier_sha256"
            assert row["match_run_id"] == "test-313-role-run"
            assert row["buyer_reason_codes"] == ["BUYER_ORGAO_CNPJ8_EXACT"]

            unknown_record = {
                "contrato_id": "test-313-unknown-supplier",
                "orgao_cnpj": buyer_cnpj,
                "fornecedor_cnpj": "11111111111",
                "supplier_id_type": "UNKNOWN",
                "supplier_identifier": "UNKNOWN:BR:11111111111",
                "source": "pncp",
            }
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([unknown_record]),),
            )
            cursor.execute(
                """
                SELECT supplier_match_method, supplier_match_confidence,
                       supplier_reason_codes
                FROM contract_role_links
                WHERE contract_id = %s
                """,
                (unknown_record["contrato_id"],),
            )
            unknown_role = cursor.fetchone()
            assert unknown_role["supplier_match_method"] == "typed_identifier_sha256_unknown_type"
            assert unknown_role["supplier_match_confidence"] == 0.5
            assert unknown_role["supplier_reason_codes"] == ["SUPPLIER_IDENTITY_UNTYPED"]

            explain_cases = {
                "idx_contract_roles_buyer": (
                    "SELECT contract_id FROM contract_role_links "
                    "WHERE buyer_entity_id = %s ORDER BY contract_id LIMIT 20",
                    (buyer["id"],),
                ),
                "idx_contract_roles_supplier": (
                    "SELECT contract_id FROM contract_role_links "
                    "WHERE supplier_identity_id = %s ORDER BY contract_id LIMIT 20",
                    (row["supplier_identity_id"],),
                ),
                "contract_role_links_pkey": (
                    "SELECT * FROM contract_role_links WHERE contract_id = %s",
                    (record["contrato_id"],),
                ),
                "idx_contract_roles_snapshot": (
                    "SELECT contract_id FROM contract_role_links "
                    "WHERE snapshot_id = %s ORDER BY contract_id LIMIT 20",
                    (row["snapshot_id"],),
                ),
            }
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'contract_role_links'
                """
            )
            present_indexes = {item["indexname"] for item in cursor.fetchall()}
            assert set(explain_cases) <= present_indexes
            cursor.execute("SET LOCAL enable_seqscan = off")
            for expected_index, (query, params) in explain_cases.items():
                if params[0] is None:
                    continue
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + query, params)
                plan = "\n".join(plan_row["QUERY PLAN"] for plan_row in cursor.fetchall())
                assert expected_index in plan
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("REQUIRE_TEST_DB") != "1",
    reason="Set REQUIRE_TEST_DB=1 to run supplier analytics population test",
)
def test_company_analytics_exclude_non_cnpj_and_match_fallback_population() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv(
        "TEST_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cursor:
            entities = _insert_role_test_entities(cursor, 3)
            buyer, supplier_entity_a, supplier_entity_b = entities
            buyer_cnpj = _valid_cnpj_for_root(str(buyer["cnpj_8"]))
            cnpj_a = _valid_cnpj_for_root(str(supplier_entity_a["cnpj_8"]))
            cnpj_b = _valid_cnpj_for_root(str(supplier_entity_b["cnpj_8"]))
            identities = [
                normalize_supplier_identity(cnpj_a, declared_type="PJ"),
                normalize_supplier_identity(cnpj_b, declared_type="PJ"),
                normalize_supplier_identity("52998224725", declared_type="PF"),
                normalize_supplier_identity(
                    "AB-123/xy", declared_type="FOREIGN", country="US"
                ),
                normalize_supplier_identity("11111111111", declared_type="PF"),
            ]
            assert [identity.supplier_id_type for identity in identities] == [
                "CNPJ",
                "CNPJ",
                "CPF",
                "FOREIGN",
                "UNKNOWN",
            ]

            # Isolate the disposable test transaction from any pre-existing contracts.
            cursor.execute("DELETE FROM public.pncp_supplier_contracts")
            cursor.execute(
                "SELECT set_config('extra.contract_role_run_id', %s, true)",
                ("test-company-analytics-population",),
            )
            values = [100, 300, 900, 800, 700]
            records = []
            for index, (identity, value) in enumerate(
                zip(identities, values, strict=True)
            ):
                records.append(
                    {
                        "contrato_id": f"test-company-population-{index}",
                        "orgao_cnpj": buyer_cnpj,
                        "orgao_nome": "Comprador analitico",
                        "fornecedor_nome": f"Fornecedor {index}",
                        **identity.to_record_fields(),
                        "objeto_contrato": "Servico de engenharia",
                        "valor_total": value,
                        "data_publicacao": "2026-08-12",
                        "source": "pncp",
                        "source_id": f"test-company-source-{index}",
                    }
                )
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps(records),),
            )
            assert len(cursor.fetchall()) == 5

            cursor.execute(
                """
                SELECT supplier_id_type, supplier_cnpj, buyer_entity_id,
                       supplier_identity_id
                FROM v_contracts_canonical_v2
                ORDER BY contrato_id
                """
            )
            typed_rows = list(cursor.fetchall())
            assert [row["supplier_id_type"] for row in typed_rows] == [
                "CNPJ",
                "CNPJ",
                "CPF",
                "FOREIGN",
                "UNKNOWN",
            ]
            assert [row["supplier_cnpj"] for row in typed_rows] == [
                cnpj_a,
                cnpj_b,
                None,
                None,
                None,
            ]
            assert {row["buyer_entity_id"] for row in typed_rows} == {buyer["id"]}
            assert buyer["id"] not in {
                supplier_entity_a["id"],
                supplier_entity_b["id"],
            }

            cursor.execute(_MARKET_SHARE_QUERY)
            primary_market = list(cursor.fetchall())
            cursor.execute(_MARKET_SHARE_FALLBACK)
            fallback_market = list(cursor.fetchall())
            primary_market_population = [
                (row["supplier_cnpj"], float(row["total"]), row["contratos"])
                for row in primary_market
            ]
            fallback_market_population = [
                (row["supplier_cnpj"], float(row["total"]), row["contratos"])
                for row in fallback_market
            ]
            assert primary_market_population == fallback_market_population
            assert primary_market_population == [(cnpj_b, 300.0, 1), (cnpj_a, 100.0, 1)]
            assert all(row["supplier_cnpj"] is not None for row in primary_market)

            cursor.execute(_HHI_QUERY)
            primary_hhi = float(cursor.fetchone()["hhi"])
            cursor.execute(_HHI_FALLBACK)
            fallback_hhi = float(cursor.fetchone()["hhi"])
            assert primary_hhi == pytest.approx(6250.0)
            assert fallback_hhi == pytest.approx(primary_hhi)

            cursor.execute(_SUPPLIER_RANKING_QUERY)
            primary_ranking = list(cursor.fetchall())
            cursor.execute(_SUPPLIER_RANKING_FALLBACK)
            fallback_ranking = list(cursor.fetchall())
            primary_ranking_population = [
                (
                    row["buyer_entity_id"],
                    row["supplier_cnpj"],
                    float(row["total"]),
                    row["ranking"],
                )
                for row in primary_ranking
            ]
            fallback_ranking_population = [
                (
                    row["buyer_entity_id"],
                    row["supplier_cnpj"],
                    float(row["total"]),
                    row["ranking"],
                )
                for row in fallback_ranking
            ]
            assert primary_ranking_population == fallback_ranking_population
            assert primary_ranking_population == [
                (buyer["id"], cnpj_b, 300.0, 1),
                (buyer["id"], cnpj_a, 100.0, 2),
            ]
    finally:
        conn.rollback()
        conn.close()
