"""Typed contract supplier identity regressions (#311)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts_identity import (
    cpf_export_mask,
    normalize_cnpj_supplier,
    normalize_supplier_identity,
)
from scripts.crawl.contracts_crawler import transform


def test_valid_cnpj_is_the_only_legacy_cnpj_join_key() -> None:
    identity = normalize_supplier_identity(
        "11.222.333/0001-81", declared_type="Pessoa Jurídica", country="BRA"
    )

    assert identity.supplier_id_type == "CNPJ"
    assert identity.supplier_identifier == "11222333000181"
    assert identity.fornecedor_cnpj == "11222333000181"
    assert identity.supplier_country == "BR"
    assert len(identity.supplier_identifier_hash or "") == 64


def test_cpf_is_validated_masked_and_never_padded_or_joined_as_cnpj() -> None:
    identity = normalize_supplier_identity(
        "529.982.247-25", declared_type="PF", country="BR"
    )

    assert identity.supplier_id_type == "CPF"
    assert identity.supplier_identifier == "52998224725"
    assert identity.supplier_identifier_export == cpf_export_mask()
    assert identity.fornecedor_cnpj is None
    assert normalize_cnpj_supplier("52998224725") is None
    assert "52998224725" not in identity.supplier_identifier_export


def test_foreign_identifier_preserves_original_value_in_country_namespace() -> None:
    identity = normalize_supplier_identity(
        "AB-123/xy", declared_type="Pessoa Estrangeira", country="US"
    )

    assert identity.supplier_id_type == "FOREIGN"
    assert identity.supplier_identifier == "FOREIGN:US:AB-123/xy"
    assert identity.supplier_country == "US"
    assert identity.fornecedor_cnpj is None


def test_invalid_declared_identifiers_remain_unknown_and_mask_eleven_digits() -> None:
    invalid_cnpj = normalize_supplier_identity("11111111111111", declared_type="PJ")
    invalid_cpf = normalize_supplier_identity("11111111111", declared_type="PF")

    assert invalid_cnpj.supplier_id_type == "UNKNOWN"
    assert invalid_cnpj.fornecedor_cnpj is None
    assert invalid_cnpj.supplier_identity_reason == "declared_cnpj_invalid"
    assert invalid_cpf.supplier_id_type == "UNKNOWN"
    assert invalid_cpf.supplier_identifier_export == "UNKNOWN:MASKED"


def test_contract_without_cnpj_is_not_dropped_and_cpf_export_is_safe() -> None:
    rows = transform(
        [
            {
                "numeroControlePNCP": "contract-cpf-1",
                "niFornecedor": "52998224725",
                "tipoPessoa": "PF",
                "nomeRazaoSocialFornecedor": "Pessoa Teste",
                "objetoContrato": "Serviço técnico",
            },
            {
                "numeroControlePNCP": "contract-unknown-1",
                "nomeRazaoSocialFornecedor": "Identidade incompleta",
            },
        ]
    )

    assert len(rows) == 2
    assert rows[0]["fornecedor_cnpj"] is None
    assert rows[0]["supplier_identifier_export"] == cpf_export_mask()
    assert rows[1]["supplier_id_type"] == "UNKNOWN"
    export_payload = json.dumps(
        [
            {
                "supplier_id_type": row["supplier_id_type"],
                "supplier_identifier": row["supplier_identifier_export"],
            }
            for row in rows
        ]
    )
    assert "52998224725" not in export_payload


def test_migration_enforces_typed_identity_and_cnpj_only_compatibility_key() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "db/migrations/076_contract_supplier_identity.sql").read_text(
        encoding="utf-8"
    )
    assert "supplier_id_type IN ('CNPJ', 'CPF', 'FOREIGN', 'UNKNOWN')" in migration
    assert "fn_contract_valid_cpf" in migration
    assert "fn_contract_valid_cnpj" in migration
    assert "fornecedor_cnpj IS NULL" in migration
    assert "fornecedor_cnpj = supplier_identifier" in migration
    assert "WHERE supplier_id_type = 'CNPJ'" in migration
    assert "zfill(14)" not in migration
    assert "lpad(" not in migration.lower()
    assert "rec->>'supplier_identifier_hash' AS supplier_identifier_hash" not in migration
    assert "rec->>'supplier_identifier_export'" not in migration


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("REQUIRE_TEST_DB") != "1",
    reason="Set REQUIRE_TEST_DB=1 to run supplier identity RPC test",
)
def test_rpc_derives_identity_security_fields_and_rejects_missing_typed_id() -> None:
    import psycopg2

    dsn = os.getenv(
        "TEST_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    conn = psycopg2.connect(dsn)
    try:
        valid_cnpj = "11222333000181"
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (
                    json.dumps(
                        [
                            {
                                "contrato_id": "test-311-server-derived",
                                "supplier_id_type": "CNPJ",
                                "supplier_identifier": valid_cnpj,
                                "fornecedor_cnpj": valid_cnpj,
                                "supplier_identifier_hash": "0" * 64,
                                "supplier_identifier_export": "attacker-controlled",
                            }
                        ]
                    ),
                ),
            )
            cursor.execute(
                """
                SELECT supplier_identifier_hash, supplier_identifier_export
                FROM pncp_supplier_contracts
                WHERE contrato_id = 'test-311-server-derived'
                """
            )
            derived_hash, safe_export = cursor.fetchone()
            assert derived_hash != "0" * 64
            assert len(derived_hash) == 64
            assert safe_export == valid_cnpj

            cursor.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (
                    json.dumps(
                        [
                            {
                                "contrato_id": "test-311-invalid-declared",
                                "supplier_id_type": "CNPJ",
                                "supplier_identifier": "11111111111111",
                                "supplier_country": "BR",
                            }
                        ]
                    ),
                ),
            )
            cursor.execute(
                """
                SELECT supplier_id_type, supplier_identifier, fornecedor_cnpj
                FROM pncp_supplier_contracts
                WHERE contrato_id = 'test-311-invalid-declared'
                """
            )
            invalid_type, invalid_identifier, invalid_cnpj = cursor.fetchone()
            assert invalid_type == "UNKNOWN"
            assert invalid_identifier == "UNKNOWN:BR:11111111111111"
            assert invalid_cnpj is None

            cursor.execute("SAVEPOINT before_missing_typed_id")
            with pytest.raises(psycopg2.errors.CheckViolation):
                cursor.execute(
                    "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                    (json.dumps([{"contrato_id": "test-311-missing", "supplier_id_type": "CNPJ"}]),),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT before_missing_typed_id")
    finally:
        conn.rollback()
        conn.close()
