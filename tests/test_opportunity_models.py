"""Test OpportunityRecord dataclass and model validation."""

from __future__ import annotations

from scripts.opportunity_intel.models import (
    CANONICAL_STATUSES,
    CONFIDENCE_LEVELS,
    RANKING_TIERS,
    CrawlRequest,
    FetchResult,
    OpportunityRecord,
)


class TestOpportunityRecord:
    """Test OpportunityRecord creation and serialization."""

    def test_minimal_record(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="test-123",
            content_hash="abc123",
            objeto="Construção de ponte",
        )
        assert record.source == "pncp"
        assert record.source_id == "test-123"
        assert record.status_canonico == "unknown"
        assert record.ranking == "REVIEW"
        assert record.ranking_score == 0
        assert record.is_active is True

    def test_full_record(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="pncpid123",
            content_hash="hash123",
            orgao_cnpj="12345678000199",
            orgao_nome="Prefeitura Municipal de Teste",
            uf="SC",
            municipio="Florianópolis",
            codigo_ibge="4205407",
            numero_processo="001/2026",
            numero_edital="001/2026",
            modalidade="Pregão Eletrônico",
            objeto="Aquisição de equipamentos",
            valor_estimado=150000.00,
            valor_semantica="estimado",
            ranking="GO",
            ranking_score=85,
            ranking_confianca="HIGH",
            status_canonico="open",
        )
        assert record.uf == "SC"
        assert record.valor_estimado == 150000.00
        assert record.ranking_score == 85

    def test_to_db_dict(self):
        record = OpportunityRecord(
            source="pncp",
            source_id="test-1",
            content_hash="hash1",
            objeto="Teste",
            orgao_cnpj="00123456000199",
            uf="SC",
            valor_estimado=50000.00,
        )
        d = record.to_db_dict()
        assert d["source"] == "pncp"
        assert d["valor_estimado"] == "50000.0"
        assert d["content_hash"] == "hash1"
        assert d["status_canonico"] == "unknown"
        assert d["ranking"] == "REVIEW"

    def test_to_db_dict_null_fields(self):
        record = OpportunityRecord(
            source="test",
            source_id="id",
            content_hash="h",
            objeto="o",
        )
        d = record.to_db_dict()
        assert d["orgao_cnpj"] is None
        assert d["valor_estimado"] is None
        assert d["data_abertura"] is None
        assert d["link_edital"] is None

    def test_constants(self):
        assert "open" in CANONICAL_STATUSES
        assert "unknown" in CANONICAL_STATUSES
        assert "revoked" in CANONICAL_STATUSES
        assert "GO" in RANKING_TIERS
        assert "REVIEW" in RANKING_TIERS
        assert "NO_GO" in RANKING_TIERS
        assert "HIGH" in CONFIDENCE_LEVELS


class TestFetchResult:
    """Test FetchResult wrapper."""

    def test_success(self):
        r = FetchResult(status=200, raw_data=[{"id": 1}])
        assert r.success is True
        assert r.empty is False

    def test_empty_200(self):
        r = FetchResult(status=200, raw_data=[])
        assert r.success is True
        assert r.empty is True

    def test_204(self):
        r = FetchResult(status=204)
        assert r.success is True
        assert r.empty is True

    def test_error(self):
        r = FetchResult(status=500, error="Server error")
        assert r.success is False
        assert r.empty is False

    def test_is_last_page_with_total(self):
        r = FetchResult(status=200, page=5, total_pages=5)
        assert r.is_last_page is True

    def test_is_last_page_empty(self):
        r = FetchResult(status=204)
        assert r.is_last_page is True


class TestCrawlRequest:
    """Test CrawlRequest parameters."""

    def test_defaults(self):
        r = CrawlRequest(source="pncp")
        assert r.mode == "full"
        assert r.page_size == 500
        assert r.limit is None


class TestStatusConstants:
    """Test status value lists."""

    def test_canonical_statuses_count(self):
        assert len(CANONICAL_STATUSES) == 8

    def test_no_overlap_ranking_tiers(self):
        # RANKING_TIERS should be exactly 3 distinct values
        assert len(set(RANKING_TIERS)) == 3
