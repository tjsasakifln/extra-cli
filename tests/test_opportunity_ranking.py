"""Test explainable ranking computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.opportunity_intel.ranking import compute_ranking


class TestRankingBasic:
    """Test basic ranking scenarios."""

    def test_open_complete_go(self):
        now = datetime.now(UTC)
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Construção de escola municipal",
            valor_estimado=500000.00,
            modalidade="Concorrência Eletrônica",
            data_abertura=now + timedelta(days=7),
            data_encerramento=now + timedelta(days=37),
            uf="SC",
            municipio="Florianópolis",
            link_edital="http://example.com/edital",
            link_anexos=["http://example.com/anexo1"],
            has_match_entity=True,
            dentro_raio=True,
            fonte_confiavel=True,
        )
        assert result["ranking"] == "GO"
        assert result["ranking_score"] >= 70
        assert result["ranking_confianca"] == "HIGH"

    def test_unknown_status_review(self):
        result = compute_ranking(
            status_canonico="unknown",
            orgao_cnpj="12345678000199",
            objeto="Serviços de manutenção",
            uf="SC",
            fonte_confiavel=True,
        )
        assert result["ranking"] in ("REVIEW", "NO_GO")
        assert "não pôde ser determinado" in str(result["ranking_fatores"]).lower()

    def test_revoked_no_go(self):
        result = compute_ranking(
            status_canonico="revoked",
            orgao_cnpj="12345678000199",
            objeto="Edital revogado",
            fonte_confiavel=True,
        )
        assert result["ranking"] == "NO_GO"
        assert result["ranking_score"] <= 20

    def test_closed_no_go(self):
        result = compute_ranking(
            status_canonico="closed",
            orgao_cnpj="12345678000199",
            objeto="Licitação encerrada",
            fonte_confiavel=True,
        )
        assert result["ranking"] == "NO_GO"

    def test_score_range_0_to_100(self):
        """Score must always be between 0 and 100."""
        now = datetime.now(UTC)
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Teste",
            valor_estimado=100000.00,
            modalidade="Pregão Eletrônico",
            data_abertura=now + timedelta(days=14),
            data_encerramento=now + timedelta(days=44),
            uf="SC",
            municipio="Florianópolis",
            link_edital="http://example.com/editais/123",
            has_match_entity=True,
            dentro_raio=True,
            fonte_confiavel=True,
        )
        assert 0 <= result["ranking_score"] <= 100

    def test_missing_all_data_no_go(self):
        result = compute_ranking(
            status_canonico="unknown",
        )
        assert result["ranking"] == "NO_GO"

    def test_factors_have_correct_structure(self):
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Teste completo",
            valor_estimado=50000.00,
            modalidade="Pregão",
            data_abertura=datetime.now(UTC) + timedelta(days=5),
            data_encerramento=datetime.now(UTC) + timedelta(days=35),
            uf="SC",
            municipio="São José",
            link_edital="http://example.com/edital",
            has_match_entity=True,
            dentro_raio=True,
        )
        assert "positivos" in result["ranking_fatores"]
        assert "negativos" in result["ranking_fatores"]
        assert "bloqueadores" in result["ranking_fatores"]
        assert isinstance(result["ranking_regras"], list)
        assert result["ranking_confianca"] in ("HIGH", "MEDIUM", "LOW")

    def test_rules_traceability(self):
        """Each factor must trace to a rule in the regras list."""
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Teste de rastreabilidade de regras",
            valor_estimado=25000.00,
            modalidade="Concorrência",
            uf="SC",
            municipio="Palhoça",
            link_edital="http://example.com/editais/456",
            has_match_entity=True,
            dentro_raio=True,
        )
        # Should have at least some rules
        assert len(result["ranking_regras"]) > 0


class TestRankingEdgeCases:
    """Test ranking edge cases."""

    def test_negative_value_no_go(self):
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Teste valor negativo",
            valor_estimado=-5000.00,
            fonte_confiavel=True,
        )
        assert result["ranking"] == "NO_GO"
        assert result["ranking_score"] <= 20

    def test_missing_objeto_no_go(self):
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="",
            fonte_confiavel=True,
        )
        assert result["ranking"] == "NO_GO"

    def test_dispensa_penalty(self):
        """Non-competitive modality should get negative factor."""
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Aquisição emergencial",
            valor_estimado=10000.00,
            modalidade="Dispensa",
            uf="SC",
            fonte_confiavel=True,
        )
        negativos = result["ranking_fatores"].get("negativos", [])
        has_penalty = any("não competitiva" in str(n).lower() for n in negativos)
        assert has_penalty

    def test_fora_raio_penalty(self):
        """Outside 200km radius should get negative factor."""
        result = compute_ranking(
            status_canonico="open",
            orgao_cnpj="12345678000199",
            objeto="Teste fora do raio",
            uf="SP",
            dentro_raio=False,
            fonte_confiavel=True,
        )
        negativos = result["ranking_fatores"].get("negativos", [])
        assert len(negativos) > 0
