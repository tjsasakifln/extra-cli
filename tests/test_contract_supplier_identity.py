"""Typed contract supplier identity regressions (#311)."""

from __future__ import annotations

import json
from pathlib import Path

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
