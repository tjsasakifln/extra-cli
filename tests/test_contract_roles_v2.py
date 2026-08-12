"""Canonical contract buyer/supplier role separation (#313)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts_identity import normalize_supplier_identity

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
    assert "FROM v_contracts_canonical\n" not in consumer


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
        "contract_role_links_pkey",
        "idx_contract_roles_snapshot",
    ):
        assert index in migration or index == "contract_role_links_pkey"


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
            cursor.execute(
                """
                SELECT id, cnpj_8
                FROM sc_public_entities
                WHERE cnpj_8 IS NOT NULL AND length(cnpj_8) = 8
                ORDER BY id LIMIT 2
                """
            )
            entities = list(cursor.fetchall())
            assert len(entities) == 2
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
            for expected_index, (query, params) in explain_cases.items():
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + query, params)
                plan = "\n".join(plan_row["QUERY PLAN"] for plan_row in cursor.fetchall())
                assert expected_index in plan
    finally:
        conn.rollback()
        conn.close()
