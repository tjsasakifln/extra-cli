"""Test deduplication logic."""

from __future__ import annotations

from scripts.opportunity_intel.dedup import (
    compute_content_hash,
    compute_dedup_keys,
    find_duplicate,
    merge_sources,
)
from scripts.opportunity_intel.models import OpportunityRecord


class TestComputeContentHash:
    """Test content hash generation."""

    def test_same_record_same_hash(self):
        r1 = {
            "source": "pncp",
            "source_id": "1",
            "orgao_cnpj": "123",
            "numero_edital": "001",
            "numero_processo": "001",
            "objeto": "test",
            "modalidade": "pregao",
        }
        r2 = {
            "source": "pncp",
            "source_id": "1",
            "orgao_cnpj": "123",
            "numero_edital": "001",
            "numero_processo": "001",
            "objeto": "test",
            "modalidade": "pregao",
        }
        assert compute_content_hash(r1) == compute_content_hash(r2)

    def test_different_record_different_hash(self):
        r1 = {
            "source": "pncp",
            "source_id": "1",
            "orgao_cnpj": "123",
            "numero_edital": "001",
            "numero_processo": "001",
            "objeto": "test-A",
            "modalidade": "pregao",
        }
        r2 = {
            "source": "pncp",
            "source_id": "2",
            "orgao_cnpj": "123",
            "numero_edital": "002",
            "numero_processo": "002",
            "objeto": "test-B",
            "modalidade": "concorrencia",
        }
        assert compute_content_hash(r1) != compute_content_hash(r2)

    def test_hash_is_deterministic(self):
        r = {
            "source": "pncp",
            "source_id": "abc",
            "orgao_cnpj": "",
            "numero_edital": "",
            "numero_processo": "",
            "objeto": "",
            "modalidade": "",
        }
        h1 = compute_content_hash(r)
        h2 = compute_content_hash(r)
        assert h1 == h2
        assert len(h1) == 32  # MD5


class TestDedupKeys:
    """Test dedup key generation from OpportunityRecord."""

    def test_pncp_id_key(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h",
            objeto="test",
            numero_controle_pncp="PNCP-123",
        )
        keys = compute_dedup_keys(record)
        assert keys["pncp_id"] == "PNCP-123"

    def test_source_compound_key(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="ABC-456",
            content_hash="h",
            objeto="test",
        )
        keys = compute_dedup_keys(record)
        assert keys["source_compound"] == "pncp:ABC-456"

    def test_org_processo_edital_key(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h",
            objeto="test",
            orgao_cnpj="12345678000199",
            numero_processo="001/2026",
            numero_edital="001/2026",
        )
        keys = compute_dedup_keys(record)
        assert keys["org_processo_edital"] == "12345678000199|001/2026|001/2026"

    def test_org_processo_edital_none_when_missing(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h",
            objeto="test",
        )
        keys = compute_dedup_keys(record)
        assert keys["org_processo_edital"] is None


class TestFindDuplicate:
    """Test duplicate detection."""

    def test_duplicate_by_pncp_id(self):
        r1 = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h1",
            objeto="test",
            numero_controle_pncp="PNCP-001",
        )
        r2 = OpportunityRecord(
            source="dom_sc",
            source_id="2",
            content_hash="h2",
            objeto="test",
            numero_controle_pncp="PNCP-001",
        )
        result = find_duplicate(r1, [r2])
        assert result is r2

    def test_duplicate_by_org_processo_edital(self):
        r1 = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h1",
            objeto="test",
            orgao_cnpj="123",
            numero_processo="P1",
            numero_edital="E1",
        )
        r2 = OpportunityRecord(
            source="dom_sc",
            source_id="2",
            content_hash="h2",
            objeto="test",
            orgao_cnpj="123",
            numero_processo="P1",
            numero_edital="E1",
        )
        result = find_duplicate(r1, [r2])
        assert result is r2

    def test_not_duplicate_different_everything(self):
        r1 = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h1",
            objeto="test A",
            orgao_cnpj="111",
        )
        r2 = OpportunityRecord(
            source="dom_sc",
            source_id="2",
            content_hash="h2",
            objeto="test B",
            orgao_cnpj="222",
        )
        result = find_duplicate(r1, [r2])
        assert result is None

    def test_no_false_match_by_text_similarity(self):
        """Conservative: never match on textual similarity alone."""
        r1 = OpportunityRecord(
            source="pncp",
            source_id="1",
            content_hash="h1",
            objeto="Construção de ponte sobre o rio X",
            orgao_cnpj="111",
        )
        r2 = OpportunityRecord(
            source="dom_sc",
            source_id="2",
            content_hash="h2",
            objeto="Construção de ponte sobre o rio Y",
            orgao_cnpj="222",
        )
        result = find_duplicate(r1, [r2])
        assert result is None  # Different CNPJ, different source_id, different hash


class TestMergeSources:
    """Test source merging."""

    def test_merge_preserves_primary(self):
        primary = OpportunityRecord(
            source="pncp",
            source_id="p1",
            content_hash="h1",
            objeto="Construção de ponte",
            orgao_cnpj="111",
            orgao_nome="Pref A",
            valor_estimado=100000.00,
        )
        secondary = OpportunityRecord(
            source="dom_sc",
            source_id="s1",
            content_hash="h2",
            objeto="Construção de ponte reformada",
            orgao_cnpj="222",
            orgao_nome="Pref B",
            link_edital="http://example.com/edital",
        )
        merged = merge_sources(primary, secondary)
        assert merged.source == "pncp+dom_sc"
        assert merged.objeto == "Construção de ponte"  # primary wins
        assert merged.orgao_cnpj == "111"  # primary wins
        assert merged.valor_estimado == 100000.00  # primary wins
        assert merged.link_edital == "http://example.com/edital"  # secondary fills gap

    def test_merge_fills_gaps(self):
        primary = OpportunityRecord(
            source="pncp",
            source_id="p1",
            content_hash="h1",
            objeto="Teste",
            uf="SC",
        )
        secondary = OpportunityRecord(
            source="dom_sc",
            source_id="s1",
            content_hash="h2",
            objeto="Teste detalhado",
            uf="SC",
            municipio="Florianópolis",
            codigo_ibge="4205407",
        )
        merged = merge_sources(primary, secondary)
        assert merged.municipio == "Florianópolis"  # filled from secondary
        assert merged.codigo_ibge == "4205407"  # filled from secondary
        assert merged.uf == "SC"
