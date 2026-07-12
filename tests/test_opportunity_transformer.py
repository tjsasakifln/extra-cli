"""Test record normalization from raw source data."""

from __future__ import annotations

from scripts.opportunity_intel.transformer import (
    normalize_dom_sc,
    normalize_generic,
    normalize_pncp,
    normalize_record,
)


class TestNormalizePncp:
    """Test PNCP API record normalization."""

    def test_basic_pncp_record(self):
        raw = {
            "numeroControlePNCP": "123456-1-001/2026",
            "orgaoCNPJ": "12345678000199",
            "orgaoRazaoSocial": "Prefeitura Municipal de Teste",
            "objeto": "Aquisição de material de escritório",
            "valorTotalEstimado": 15000.00,
            "modalidadeNome": "Pregão Eletrônico",
            "codigoModalidade": 7,
            "uf": "SC",
            "municipio": "Florianópolis",
            "codigoMunicipioIbge": "4205407",
            "situacaoCompra": "recebendo proposta",
            "dataPublicacao": "2026-07-01T10:00:00",
            "dataAbertura": "2026-07-15T09:00:00",
            "dataEncerramento": "2026-07-30T17:00:00",
            "linkSistemaOrigem": "http://example.com/edital",
        }
        record = normalize_pncp(raw)
        assert record.source == "pncp"
        assert record.source_id == "123456-1-001/2026"
        assert record.orgao_cnpj == "12345678000199"
        assert record.objeto == "Aquisição de material de escritório"
        assert record.valor_estimado == 15000.00
        assert record.modalidade == "Pregão Eletrônico"
        assert record.uf == "SC"
        assert record.municipio == "Florianópolis"
        assert record.status_canonico == "open"

    def test_pncp_alternative_field_names(self):
        raw = {
            "id": 999,
            "orgaoCnpj": "98765432000199",
            "objeto": "Serviços de limpeza",
            "valorEstimado": 50000.00,
            "uf": "SC",
        }
        record = normalize_pncp(raw)
        assert record.orgao_cnpj == "98765432000199"
        assert record.objeto == "Serviços de limpeza"
        assert record.valor_estimado == 50000.00

    def test_pncp_minimal_record(self):
        raw = {"id": 1, "objeto": "Teste mínimo", "uf": "SC"}
        record = normalize_pncp(raw)
        assert record.source == "pncp"
        assert record.objeto == "Teste mínimo"
        assert record.uf == "SC"

    def test_pncp_content_hash_generated(self):
        raw = {"id": "test-1", "objeto": "Teste hash", "uf": "SC"}
        record = normalize_pncp(raw)
        assert record.content_hash
        assert len(record.content_hash) == 32

    def test_pncp_status_and_ranking_computed(self):
        raw = {
            "id": "test-status",
            "objeto": "Serviços de engenharia",
            "uf": "SC",
            "valorTotalEstimado": 250000.00,
            "modalidadeNome": "Concorrência Eletrônica",
            "situacaoCompra": "recebendo proposta",
        }
        record = normalize_pncp(raw)
        assert record.status_canonico in ("open", "upcoming", "closed", "unknown")
        assert record.status_motivo
        assert record.ranking in ("GO", "REVIEW", "NO_GO")


class TestNormalizeDomSc:
    """Test DOM-SC publication normalization."""

    def test_basic_dom_sc(self):
        raw = {
            "id": 8472191,
            "titulo": "PREGÃO ELETRÔNICO 2212/2026 - Contratação de empresa de engenharia",
            "cod_categoria": "6",
            "status": "Autopublicação Publicada",
            "data_publicacao": "01/07/2026",
            "url": "https://diariomunicipal.sc.gov.br/atos/8472191",
            "entidade": "Prefeitura Municipal de Santo Amaro da Imperatriz",
        }
        record = normalize_dom_sc(raw)
        assert record.source == "dom_sc"
        assert record.source_id == "8472191"
        assert "engenharia" in record.objeto.lower()
        assert record.uf == "SC"

    def test_dom_sc_extract_edital(self):
        raw = {
            "id": 123,
            "titulo": "EDITAL DE LICITAÇÃO Nº 001/2026 - PREGÃO",
            "status": "Publicado",
            "data_publicacao": "01/01/2026",
        }
        record = normalize_dom_sc(raw)
        assert record.numero_edital == "001/2026"

    def test_dom_sc_minimal(self):
        raw = {"id": 1, "titulo": "Publicação teste"}
        record = normalize_dom_sc(raw)
        assert record.source == "dom_sc"
        assert record.uf == "SC"
        assert record.content_hash


class TestNormalizeGeneric:
    """Test generic normalization fallback."""

    def test_generic_with_known_fields(self):
        raw = {
            "id": "abc",
            "objeto": "Teste genérico",
            "orgao_cnpj": "11111111000199",
            "uf": "PR",
            "municipio": "Curitiba",
            "valor": 100000.00,
            "modalidade": "Concorrência",
            "data_abertura": "2026-08-01T10:00:00",
        }
        record = normalize_generic(raw, "test_source")
        assert record.source == "test_source"
        assert record.objeto == "Teste genérico"
        assert record.orgao_cnpj == "11111111000199"
        assert record.uf == "PR"
        assert record.municipio == "Curitiba"
        assert record.valor_estimado == 100000.00

    def test_generic_empty_input(self):
        raw = {}
        record = normalize_generic(raw, "unknown")
        assert record.source == "unknown"
        assert record.status_canonico == "unknown"


class TestNormalizeRecordDispatch:
    """Test normalizer dispatch."""

    def test_dispatches_to_pncp(self):
        raw = {"id": "test", "objeto": "Teste PNCP", "uf": "SC"}
        record = normalize_record(raw, "pncp")
        assert record.source == "pncp"

    def test_dispatches_to_dom_sc(self):
        raw = {"id": 1, "titulo": "Teste DOM"}
        record = normalize_record(raw, "dom_sc")
        assert record.source == "dom_sc"

    def test_falls_back_to_generic(self):
        raw = {"id": "test", "objeto": "Teste fallback"}
        record = normalize_record(raw, "unknown_source")
        assert record.source == "unknown_source"
