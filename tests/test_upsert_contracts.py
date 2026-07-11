"""Unit tests for the upsert_pncp_supplier_contracts SQL RPC behavior.

These tests validate that the JSON records produced by contracts_crawler.transform()
are compatible with the set-based upsert_pncp_supplier_contracts() function
defined in db/migrations/006_upsert_rpcs.sql.

The actual SQL function is tested in integration tests (requires a running DB).
Here we verify the Python side: record schema, field types, and compatibilidade.
"""

import json

from scripts.crawl import contracts_crawler as cc

# ---------------------------------------------------------------------------
# Record schema validation
# ---------------------------------------------------------------------------


class TestUpsertRecordSchema:
    """Validate that transform output matches the upsert RPC schema.

    The ``upsert_pncp_supplier_contracts`` SQL function expects these columns:
        contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj,
        fornecedor_nome, objeto_contrato, valor_total, data_inicio,
        data_fim, data_publicacao, uf, municipio, source, source_id
    """

    MOCK_CONTRACT = {
        "numeroControlePNCP": "12345678901234567890",
        "orgaoEntidade": {
            "cnpj": "12345678000199",
            "razaoSocial": "Prefeitura Municipal de Florianopolis",
        },
        "unidadeOrgao": {
            "cnpj": "12345678000199",
            "nomeUnidade": "Secretaria Municipal de Administracao",
            "ufSigla": "SC",
            "municipioNome": "Florianopolis",
        },
        "niFornecedor": "00999999000199",
        "nomeRazaoSocialFornecedor": "Empresa Exemplo Ltda",
        "valorGlobal": 150000.00,
        "dataAssinatura": "2025-06-15T10:00:00Z",
        "dataVigenciaInicio": "2025-07-01T00:00:00Z",
        "dataVigenciaFim": "2026-06-30T23:59:59Z",
        "objetoContrato": "Prestacao de servicos de limpeza predial",
    }

    def test_record_is_json_serializable(self):
        """Transform output must be JSON-serializable for the RPC call."""
        result = cc.transform([self.MOCK_CONTRACT])
        assert len(result) == 1
        record = result[0]
        # Should not raise
        serialized = json.dumps(record, default=str)
        assert isinstance(serialized, str)
        assert "contrato_id" in serialized

    def test_required_fields_present(self):
        """Every upsert record must have the required fields."""
        result = cc.transform([self.MOCK_CONTRACT])
        record = result[0]
        required = {
            "contrato_id", "orgao_cnpj", "fornecedor_cnpj",
            "fornecedor_nome", "valor_total", "uf",
        }
        missing = required - set(record.keys())
        assert not missing, f"Missing required fields: {missing}"

    def test_field_types_are_compatible(self):
        """Field types must be compatible with PostgreSQL NUMERIC/DATE/TEXT."""
        result = cc.transform([self.MOCK_CONTRACT])
        record = result[0]

        # contrato_id must be string
        assert isinstance(record["contrato_id"], str)

        # valor_total must be numeric (int, float, or None)
        assert record["valor_total"] is None or isinstance(record["valor_total"], (int, float))

        # Dates must be ISO strings or None
        for date_field in ("data_inicio", "data_fim", "data_publicacao"):
            val = record.get(date_field)
            assert val is None or isinstance(val, str), (
                f"{date_field} should be str or None, got {type(val)}"
            )

    def test_contrato_id_is_unique_key(self):
        """contrato_id must be non-empty for the ON CONFLICT clause."""
        result = cc.transform([self.MOCK_CONTRACT])
        record = result[0]
        assert record["contrato_id"], "contrato_id must not be empty"
        assert record["contrato_id"] == "12345678901234567890"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestUpsertEdgeCases:
    """Edge cases for the upsert contract records."""

    def test_empty_record_list(self):
        """transform([]) returns empty list."""
        result = cc.transform([])
        assert result == []

    def test_record_without_fornecedor_cnpj_is_skipped(self):
        """Records without supplier CNPJ are filtered out."""
        rec = {
            "numeroControlePNCP": "99999999999999999999",
            "orgaoEntidade": {"cnpj": "12345678000199"},
            "objetoContrato": "Teste sem fornecedor",
        }
        result = cc.transform([rec])
        assert len(result) == 0

    def test_null_valor_total_is_valid(self):
        """valor_total can be None for contracts without financial value."""
        rec = dict(TestUpsertRecordSchema.MOCK_CONTRACT)
        rec["valorGlobal"] = None
        result = cc.transform([rec])
        assert len(result) == 1
        assert result[0]["valor_total"] is None
